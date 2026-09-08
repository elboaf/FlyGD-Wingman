"""Lane E: real rows/controller, with only scanning and worker timing controlled."""

import datetime
import json
import os
import queue
import threading
import zipfile
from contextlib import contextmanager
from dataclasses import replace

import pytest

from tests import fakes
from wingman import combatlog, discord, durations, library, links, uploader
from wingman.ui.rows import RowSnapshot
from wingman.upload.controller import UploadJob


class DeferredWorker:
    def __init__(self, target, **kwargs):
        self.target = target

    def start(self):
        pass


class ManualScheduler:
    def __init__(self, interval, callback, **kwargs):
        self.callback = callback
        self.running = False
        self.starts = 0

    def start(self):
        self.starts += 1
        self.running = True

    def stop(self):
        self.running = False


@contextmanager
def running(target):
    errors = []

    def invoke():
        try:
            target()
        except BaseException as exc:  # noqa: BLE001 — re-raised on the test thread below.
            errors.append(exc)

    thread = threading.Thread(target=invoke, daemon=True)
    thread.start()
    try:
        yield thread
    finally:
        thread.join(5)
        assert not thread.is_alive(), "test worker did not finish"
        if errors:
            raise errors[0]


@pytest.fixture
def rig(tmp_path):
    folder = tmp_path / "recordings"
    folder.mkdir()
    (folder / "old.mkv").write_bytes(b"old recording")
    rows = RowSnapshot()
    api, _ = fakes.build_api(tmp_path, rows=rows)
    api._state.recording_dir = folder
    controller = api._uploader
    loops = []
    workers = []

    def scheduler(*args, **kwargs):
        loop = ManualScheduler(*args, **kwargs)
        loops.append(loop)
        return loop

    def spawn(**kwargs):
        worker = DeferredWorker(**kwargs)
        workers.append(worker)
        return worker

    controller._scheduler = scheduler
    controller._ports = replace(controller._ports, spawn=spawn)
    controller._probe = lambda *args: (12.5, True)
    sent = fakes.record_pushes(api)
    return api, controller, rows, folder, loops, workers, sent


def pause_stat(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    real_stat = library.stat_info
    first = True

    def stat(path):
        nonlocal first
        info = real_stat(path)
        if first:
            first = False
            entered.set()
            assert release.wait(5)
        return info

    monkeypatch.setattr(library, "stat_info", stat)
    return entered, release


def test_old_scan_cannot_replace_successful_folder_switch(rig, tmp_path, monkeypatch):
    api, _controller, rows, _folder, loops, _workers, sent = rig
    new = tmp_path / "new"
    new.mkdir()
    (new / "current.mkv").write_bytes(b"current recording")
    entered, release = pause_stat(monkeypatch)
    with running(api.list_rows):
        assert entered.wait(5)
        try:
            result = api.set_folder("recording", str(new))
            assert result["applied"]
            current = rows.rows()
        finally:
            release.set()
    assert api._state.recording_dir == new
    assert rows.rows() == current
    assert [row["name"] for row in current] == ["current.mkv"]
    assert fakes.payloads(sent, "onRows") == [{"rows": current}]
    assert len(loops) == 1 and loops[0].running


def test_same_folder_refresh_keeps_newest_selection_and_coherent_ids(rig, monkeypatch):
    api, _controller, rows, folder, _loops, _workers, _sent = rig
    entered, release = pause_stat(monkeypatch)
    with running(api.list_rows):
        assert entered.wait(5)
        try:
            api.list_rows(preselect={folder / "old.mkv"})
            current = rows.rows()
        finally:
            release.set()
    assert rows.rows() == current
    assert current[0]["preselected"]
    ids = [row["id"] for row in current]
    assert len(ids) == len(set(ids))
    assert [info.path.name for info in rows.resolve_many(ids)] == [
        row["name"] for row in current
    ]
    api.list_rows()
    assert not set(ids) & {row["id"] for row in rows.rows()}
    assert all(rows.resolve(rid) is None for rid in ids)


def test_stale_callback_cannot_stop_replacement(rig):
    api, controller, rows, folder, loops, workers, _sent = rig
    api.list_rows()
    old = loops[-1]
    api.list_rows()
    current = loops[-1]
    old.callback()  # Timer.stop cannot join an already-entered callback.
    assert current.running
    workers[-1].target()
    current.callback()
    assert not current.running
    assert rows.rows()[0]["duration"] == library.format_duration(12.5)
    assert (
        durations.load(controller._durations_file)[str(folder / "old.mkv")].duration
        == 12.5
    )


@pytest.mark.parametrize("already_dequeued", [False, True])
def test_entered_old_drain_cannot_steal_replacement_results(
    rig, monkeypatch, already_dequeued
):
    api, controller, rows, _folder, loops, workers, sent = rig
    api.list_rows()
    old = loops[-1]
    if already_dequeued:
        workers[-1].target()
    entered, release = threading.Event(), threading.Event()
    real_get = queue.Queue.get_nowait
    first = True

    def get(q):
        nonlocal first
        if first:
            first = False
            result = real_get(q) if already_dequeued else None
            entered.set()
            assert release.wait(5)
            if already_dequeued:
                return result
        return real_get(q)

    monkeypatch.setattr(queue.Queue, "get_nowait", get)
    with running(old.callback):
        assert entered.wait(5)
        try:
            api.list_rows()
            current = loops[-1]
            workers[-1].target()
        finally:
            release.set()
    assert current.running
    assert not fakes.payloads(sent, "onDuration")
    assert durations.load(controller._durations_file) == {}
    current.callback()
    assert not current.running
    assert rows.rows()[0]["duration"] == library.format_duration(12.5)


def test_pre_rename_scan_cannot_restore_old_name(rig, monkeypatch):
    api, _controller, rows, folder, _loops, _workers, sent = rig
    api.list_rows()
    rid = rows.rows()[0]["id"]
    entered, release = pause_stat(monkeypatch)
    with running(api.list_rows):
        assert entered.wait(5)
        try:
            assert api.rename_recording(rid, "renamed")["ok"]
            assert rows.resolve(rid).path == folder / "renamed.mkv"
        finally:
            release.set()
    assert [row["name"] for row in rows.rows()] == ["renamed.mkv"]
    assert rows.resolve_many([row["id"] for row in rows.rows()])[0].path.exists()
    assert fakes.payloads(sent, "onRows")[-1]["rows"] == rows.rows()


def test_link_is_durable_when_its_original_row_is_stale(rig):
    api, controller, rows, _folder, _loops, _workers, _sent = rig
    api.list_rows()
    rid = rows.rows()[0]["id"]
    uploaded = rows.resolve(rid)
    api.list_rows()
    controller._link(rid, "uploaded", uploaded)
    stored = links.load(controller._links_file)
    url = uploader.watch_url("uploaded")
    assert links.lookup(stored, uploaded.path, uploaded.size, uploaded.mtime) == url
    api.list_rows()
    assert rows.rows()[0]["link"] == url
    assert api.copy_path(rows.rows()[0]["id"]) == url


@pytest.mark.parametrize("update", ["duration", "link"])
def test_scan_hydrates_answers_committed_after_its_stat(rig, monkeypatch, update):
    api, controller, rows, _folder, _loops, _workers, sent = rig
    api.list_rows()
    rid = rows.rows()[0]["id"]
    info = rows.resolve(rid)
    entered, release = pause_stat(monkeypatch)
    with running(api.list_rows):
        assert entered.wait(5)
        try:
            if update == "duration":
                monkeypatch.setattr(library, "probe", lambda *args: (90.0, True))
                controller._probe_now([(rid, info)])
            else:
                controller._link(rid, "uploaded", info)
        finally:
            release.set()
    current = rows.rows()[0]
    if update == "duration":
        assert current["duration"] == "1:30"
    else:
        assert current["link"] == uploader.watch_url("uploaded")
        assert api.copy_path(current["id"]) == current["link"]
    assert fakes.payloads(sent, "onRows")[-1]["rows"] == [current]


class ObservedGate:
    """Expose contention without sleeping or changing lock semantics."""

    def __init__(self):
        self.lock = threading.Lock()
        self.contended = threading.Event()

    def __enter__(self):
        if not self.lock.acquire(blocking=False):
            self.contended.set()
            self.lock.acquire()

    def __exit__(self, *args):
        self.lock.release()


@pytest.mark.parametrize("event", ["rows", "duration", "link", "rename"])
def test_acceptance_mutation_and_delivery_are_one_ordered_operation(
    rig, event, monkeypatch
):
    api, controller, rows, _folder, _loops, _workers, sent = rig
    api.list_rows()
    rid = rows.rows()[0]["id"]
    info = rows.resolve(rid)
    gate = ObservedGate()
    controller._publication_lock = gate
    entered, release = threading.Event(), threading.Event()
    port_name = {
        "rows": "publish_rows",
        "duration": "publish_duration",
        "link": "publish_link",
        "rename": "publish_row_renamed",
    }[event]
    publish = getattr(controller._ports, port_name)
    first = True

    def blocked(payload):
        nonlocal first
        if first:
            first = False
            entered.set()
            assert release.wait(5)
        publish(payload)

    controller._ports = replace(controller._ports, **{port_name: blocked})
    monkeypatch.setattr(library, "probe", lambda *args: (90.0, True))
    action = {
        "rows": api.list_rows,
        "duration": lambda: controller._probe_now([(rid, info)]),
        "link": lambda: controller._link(rid, "uploaded", info),
        "rename": lambda: api.rename_recording(rid, "renamed"),
    }[event]
    with running(action):
        assert entered.wait(5)
        before = rows.rows()  # Row reads must not wait for blocked WebView.
        with running(api.list_rows):
            try:
                assert gate.contended.wait(5)  # The next scan already finished.
                assert rows.rows() == before, "installed newer rows before old delivery"
                # State access must not wait for WebView either.
                assert controller._state_lock.acquire(timeout=1)
                controller._state_lock.release()
            finally:
                release.set()
    # Replay the actual payloads: no late whole-row or incremental event may
    # regress the final backend view (a lock around push alone would fail).
    page = {}
    for name, payload in sent:
        if name == "onRows":
            page = {row["id"]: dict(row) for row in payload["rows"]}
        elif name == "onDuration" and payload["id"] in page:
            page[payload["id"]]["duration"] = payload["duration"]
        elif name == "onLink" and payload["id"] in page:
            page[payload["id"]]["link"] = payload["url"]
        elif name == "onRowRenamed" and payload["id"] in page:
            page[payload["id"]]["name"] = payload["name"]
    assert list(page.values()) == rows.rows()
    if event == "link":
        assert rows.rows()[0]["link"] == uploader.watch_url("uploaded")
    if event == "rename":
        assert rows.rows()[0]["name"] == "renamed.mkv"


@pytest.mark.parametrize(
    "failure", ["spawn", "worker_start", "scheduler_create", "scheduler_start"]
)
def test_startup_failure_leaves_no_owner_or_running_loop(rig, failure):
    api, controller, rows, _folder, loops, workers, sent = rig
    spawn = controller._ports.spawn
    scheduler = controller._scheduler

    def fail():
        raise RuntimeError("injected startup failure")

    def bad_spawn(**kwargs):
        if failure == "spawn":
            fail()
        worker = spawn(**kwargs)
        worker.start = fail
        return worker

    def bad_scheduler(*args, **kwargs):
        if failure == "scheduler_create":
            fail()
        loop = scheduler(*args, **kwargs)

        def start():
            loop.running = True  # Also exercise a partially armed scheduler.
            fail()

        loop.start = start
        return loop

    if failure in {"spawn", "worker_start"}:
        controller._ports = replace(controller._ports, spawn=bad_spawn)
    else:
        controller._scheduler = bad_scheduler
    with pytest.raises(RuntimeError, match="injected startup failure"):
        api.list_rows()
    assert controller._probe_run is None
    assert not any(loop.running for loop in loops)
    for loop in loops:
        loop.callback()  # Even a partial start's late callback is harmless.
    assert not fakes.payloads(sent, "onDuration")
    controller._ports = replace(controller._ports, spawn=spawn)
    controller._scheduler = scheduler
    api.list_rows()
    workers[-1].target()
    loops[-1].callback()
    assert rows.rows()[0]["duration"] == library.format_duration(12.5)


def test_supersession_during_synchronous_worker_start_cannot_rearm_old_loop(rig):
    api, controller, _rows, _folder, loops, _workers, sent = rig
    entered, release = threading.Event(), threading.Event()
    first = True
    spawn = controller._ports.spawn

    def blocking_probe(*args):
        nonlocal first
        if first:
            first = False
            entered.set()
            assert release.wait(5)
        return 12.5, True

    def inline_spawn(**kwargs):
        worker = spawn(**kwargs)
        worker.start = worker.target
        return worker

    controller._probe = blocking_probe
    controller._ports = replace(controller._ports, spawn=inline_spawn)
    with running(api.list_rows):
        assert entered.wait(5)
        try:
            api.list_rows()
            old, current = loops
            assert current.running
        finally:
            release.set()
    assert old.starts == 0 and not old.running
    old.callback()
    assert current.running
    current.callback()
    assert not current.running
    assert len(fakes.payloads(sent, "onDuration")) == 1


def test_probe_failure_still_completes_its_own_drain(rig):
    api, controller, _rows, _folder, loops, workers, sent = rig

    def fail(*args):
        raise RuntimeError("unexpected probe failure")

    controller._probe = fail
    api.list_rows()
    workers[-1].target()
    loops[-1].callback()
    assert controller._probe_run is None
    assert not loops[-1].running
    assert not fakes.payloads(sent, "onDuration")


def test_late_background_verdict_cannot_overwrite_definitive_cache(rig, monkeypatch):
    api, controller, rows, _folder, loops, workers, _sent = rig
    api.list_rows()
    rid = rows.rows()[0]["id"]
    info = rows.resolve(rid)
    workers[-1].target()  # Background 12.5 queued, but not applied yet.
    monkeypatch.setattr(library, "probe", lambda *args: (90.0, True))
    controller._probe_now([(rid, info)])
    loops[-1].callback()
    assert rows.rows()[0]["duration"] == library.format_duration(90.0)
    assert durations.load(controller._durations_file)[str(info.path)].duration == 90.0
    api.list_rows()
    assert rows.rows()[0]["duration"] == library.format_duration(90.0)


def log_posts(rig, monkeypatch):
    """Real log/archive pipeline, with only the final network effect replaced."""
    api, _controller, _rows, folder, _loops, _workers, _sent = rig
    end = datetime.datetime(2026, 9, 8, 12, 0, tzinfo=datetime.UTC)
    os.utime(folder / "old.mkv", (end.timestamp(), end.timestamp()))
    logs = folder.parent / "Gamelogs"
    logs.mkdir()
    log = logs / "20260908_115800_123.txt"
    log.write_bytes(
        b"  Gamelog\r\n  Listener: Pilot\r\n"
        b"  Session Started: 2026.09.08 11:58:00\r\n"
        b"[ 2026.09.08 11:59:55 ] (combat) hit\r\n"
    )
    os.utime(log, (end.timestamp(), end.timestamp()))
    api._state.settings.update(
        discord_webhook="https://discord.com/api/webhooks/123/test-token",
        gamelogs_dir=str(logs),
    )
    posts = []

    def post(hook, path, content):
        # Observe the real archive at the network boundary, before success
        # removes it. No log-selection or archive-building stubs hide failures.
        with zipfile.ZipFile(path) as archive:
            posts.append(json.loads(archive.read(combatlog.MANIFEST_NAME)))
        return discord.PostResult(ok=True, message="Posted combat logs.")

    monkeypatch.setattr(discord, "post_archive", post)
    return end, posts


@pytest.mark.parametrize(
    "refresh,first,background,foreground,changed,want_capture,want_current,want_cell,want_start",
    [
        pytest.param(
            False,
            "background",
            (12.5, True),
            (90.0, True),
            None,
            12.5,
            12.5,
            "0:12",
            "11:59:47.500000",
            id="same-row-control",
        ),
        pytest.param(
            True,
            "background",
            (12.5, True),
            (90.0, True),
            None,
            12.5,
            12.5,
            "0:12",
            "11:59:47.500000",
            id="replacement-background-first",
        ),
        pytest.param(
            True,
            "foreground",
            (12.5, True),
            (90.0, True),
            None,
            90.0,
            90.0,
            "1:30",
            "11:58:30",
            id="replacement-foreground-first",
        ),
        pytest.param(
            True,
            "background",
            (None, True),
            (90.0, True),
            None,
            None,
            None,
            "?",
            None,
            id="replacement-definitive-none",
        ),
        pytest.param(
            True,
            "background",
            (None, False),
            (90.0, True),
            None,
            90.0,
            90.0,
            "1:30",
            "11:58:30",
            id="replacement-no-verdict",
        ),
        pytest.param(
            True,
            "background",
            (12.5, True),
            (None, False),
            None,
            12.5,
            12.5,
            "0:12",
            "11:59:47.500000",
            id="replacement-late-no-verdict",
        ),
        pytest.param(
            True,
            "background",
            (12.5, True),
            (90.0, True),
            "size",
            90.0,
            12.5,
            "0:12",
            "11:58:30",
            id="reused-path-changed-size",
        ),
        pytest.param(
            True,
            "background",
            (12.5, True),
            (90.0, True),
            "mtime",
            90.0,
            12.5,
            "0:12",
            "11:58:30",
            id="reused-path-changed-mtime",
        ),
    ],
)
def test_captured_log_duration_agrees_with_replacement_and_disk(
    rig,
    monkeypatch,
    refresh,
    first,
    background,
    foreground,
    changed,
    want_capture,
    want_current,
    want_cell,
    want_start,
):
    """First definitive answer wins for the SAME recording, not a reused path."""
    api, controller, rows, folder, loops, workers, sent = rig
    end, posts = log_posts(rig, monkeypatch)
    recording = folder / "old.mkv"
    controller._probe = lambda *args: background
    api.list_rows()
    rid = rows.rows()[0]["id"]
    captured = rows.resolve(rid)
    job = UploadJob(
        items=[captured],
        ids=[rid],
        title="Fight",
        description="",
        stitch=False,
        privacy="unlisted",
        category="20",
        logs=True,
    )
    entered, release = threading.Event(), threading.Event()

    def foreground_probe(path, binary):
        # Model a probe of the captured file whose completion is delayed,
        # not a probe of the replacement bytes written below.
        stat = path.stat()
        assert (path, stat.st_size, stat.st_mtime) == (
            captured.path,
            captured.size,
            captured.mtime,
        )
        entered.set()
        assert release.wait(5)
        return foreground

    monkeypatch.setattr(library, "probe", foreground_probe)
    with running(
        lambda: controller._post_combat_logs(job, 'Uploaded "Fight" to YouTube')
    ):
        try:
            assert entered.wait(5)
            if changed == "size":
                recording.write_bytes(b"replacement recording with a different size")
                os.utime(recording, (end.timestamp(), end.timestamp()))
            elif changed == "mtime":
                os.utime(recording, (end.timestamp() + 60, end.timestamp() + 60))
            if refresh:
                api.list_rows()
                assert rows.resolve(rid) is None
                assert rows.resolve(rows.rows()[0]["id"]) is not captured
            # Queue the background result before either order is accepted;
            # the real drain decides whether it may supersede the foreground.
            workers[-1].target()
            if first == "background":
                loops[-1].callback()
        finally:
            release.set()
    if first == "foreground":
        loops[-1].callback()

    current_row = rows.rows()[0]
    current = rows.resolve(current_row["id"])
    stored = durations.load(controller._durations_file)
    statuses = fakes.payloads(sent, "onStatus")
    observed = {
        "captured": (captured.duration, captured.probed, captured.answered),
        "current": (current.duration, current.probed, current.answered),
        "rendered": current_row["duration"],
        "disk_captured": durations.lookup(
            stored, captured.path, captured.size, captured.mtime
        ),
        "disk_current": durations.lookup(
            stored, current.path, current.size, current.mtime
        ),
        "post_count": len(posts),
        "post_windows": [(p["window_start"], p["window_end"]) for p in posts],
        "posted_files": [p["files"] for p in posts],
        "skipped": any("Combat logs skipped" in p["text"] for p in statuses),
    }
    expected = {
        "captured": (want_capture, True, True),
        "current": (want_current, True, True),
        "rendered": want_cell,
        # One cache slot per path: an old job may resolve itself, but must
        # not evict the accepted verdict for a replacement file's identity.
        "disk_captured": (False, None) if changed else (True, want_capture),
        "disk_current": (True, want_current),
        "post_count": 0 if want_start is None else 1,
        "post_windows": []
        if want_start is None
        else [(f"2026-09-08T{want_start}+00:00", "2026-09-08T12:00:00+00:00")],
        "posted_files": [] if want_start is None else [["20260908_115800_123.txt"]],
        "skipped": want_start is None,
    }
    assert observed == expected, f"Joint duration outcome: {observed!r}"


def pause_foreground(monkeypatch, verdict=(90.0, True)):
    entered, release = threading.Event(), threading.Event()

    def probe(path, binary):
        entered.set()
        assert release.wait(5)
        return verdict

    monkeypatch.setattr(library, "probe", probe)
    return entered, release


def duration_state(info):
    return info.duration, info.probed, info.answered


def disk_duration(controller, info):
    return durations.lookup(
        durations.load(controller._durations_file), info.path, info.size, info.mtime
    )


@pytest.mark.parametrize("changed", ["size", "mtime"])
def test_old_duration_cannot_fill_unmeasured_replacement_slot(
    rig, monkeypatch, changed
):
    api, controller, rows, folder, loops, workers, _sent = rig
    api.list_rows()
    rid = rows.rows()[0]["id"]
    captured = rows.resolve(rid)
    entered, release = pause_foreground(monkeypatch)
    with running(lambda: controller._probe_now([(rid, captured)])):
        try:
            assert entered.wait(5)
            path = folder / "old.mkv"
            if changed == "size":
                path.write_bytes(b"replacement with a different size")
                os.utime(path, (captured.mtime, captured.mtime))
            else:
                os.utime(path, (captured.mtime + 60, captured.mtime + 60))
            api.list_rows()
        finally:
            release.set()
    current = rows.resolve(rows.rows()[0]["id"])
    before = (
        duration_state(captured),
        duration_state(current),
        rows.rows()[0]["duration"],
        disk_duration(controller, captured),
        disk_duration(controller, current),
    )
    workers[-1].target()
    loops[-1].callback()
    after = (
        duration_state(captured),
        duration_state(current),
        rows.rows()[0]["duration"],
        disk_duration(controller, captured),
        disk_duration(controller, current),
    )
    assert (before, after) == (
        ((90.0, True, True), (None, False, True), "…", (False, None), (False, None)),
        ((90.0, True, True), (12.5, True, True), "0:12", (False, None), (True, 12.5)),
    )


@pytest.mark.parametrize("first", ["background", "foreground"])
def test_duration_follows_rename_without_inheriting_reused_path(
    rig, monkeypatch, first
):
    api, controller, rows, folder, loops, workers, sent = rig
    api.list_rows()
    old_id = rows.rows()[0]["id"]
    captured = rows.resolve(old_id)
    entered, release = pause_foreground(monkeypatch)
    with running(lambda: controller._probe_now([(old_id, captured)])):
        try:
            assert entered.wait(5)
            api.list_rows()
            assert api.rename_recording(rows.rows()[0]["id"], "renamed")["ok"]
            # Identical metadata at the old name must not undo the real rename
            # transition that has already repointed the retained capture.
            reused = folder / "old.mkv"
            reused.write_bytes(b"x" * captured.size)
            os.utime(reused, (captured.mtime, captured.mtime))
            controller._probe = lambda path, binary: (
                30.0 if path == reused else 12.5,
                True,
            )
            api.list_rows()
            workers[-1].target()
            if first == "background":
                loops[-1].callback()
        finally:
            release.set()
    if first == "foreground":
        loops[-1].callback()
    wanted = 12.5 if first == "background" else 90.0
    cells = {row["name"]: row["duration"] for row in rows.rows()}
    infos = {
        info.path.name: info
        for info in rows.resolve_many([r["id"] for r in rows.rows()])
    }
    assert {
        "capture": (captured.path.name, duration_state(captured)),
        "current": {name: duration_state(info) for name, info in infos.items()},
        "cells": cells,
        "disk": {name: disk_duration(controller, info) for name, info in infos.items()},
        "stale_event": any(
            p["id"] == old_id for p in fakes.payloads(sent, "onDuration")
        ),
    } == {
        "capture": ("renamed.mkv", (wanted, True, True)),
        "current": {"renamed.mkv": (wanted, True, True), "old.mkv": (30.0, True, True)},
        "cells": {
            "renamed.mkv": "0:12" if first == "background" else "1:30",
            "old.mkv": "0:30",
        },
        "disk": {"renamed.mkv": (True, wanted), "old.mkv": (True, 30.0)},
        "stale_event": False,
    }


@pytest.mark.parametrize("conflicting_slot", [False, True])
@pytest.mark.parametrize("verdict", [(90.0, True), (None, True), (None, False)])
def test_detached_duration_resolves_without_evicting_conflicting_slot(
    rig, monkeypatch, tmp_path, conflicting_slot, verdict
):
    api, controller, rows, _folder, loops, workers, sent = rig
    api.list_rows()
    rid = rows.rows()[0]["id"]
    captured = rows.resolve(rid)
    entered, release = pause_foreground(monkeypatch, verdict)
    with running(lambda: controller._probe_now([(rid, captured)])):
        try:
            assert entered.wait(5)
            if conflicting_slot:
                captured.path.write_bytes(b"a different recording")
                api.list_rows()
                replacement = rows.resolve(rows.rows()[0]["id"])
                workers[-1].target()
                loops[-1].callback()
            other = tmp_path / "other"
            other.mkdir()
            assert api.set_folder("recording", str(other))["applied"]
            sent.clear()
        finally:
            release.set()
    duration, definitive = verdict
    assert {
        "capture": duration_state(captured),
        "rows": rows.rows(),
        "disk_old": disk_duration(controller, captured),
        "disk_replacement": disk_duration(controller, replacement)
        if conflicting_slot
        else None,
        "events": fakes.payloads(sent, "onDuration"),
    } == {
        "capture": (duration, True, definitive),
        "rows": [],
        "disk_old": (True, duration)
        if definitive and not conflicting_slot
        else (False, None),
        "disk_replacement": (True, 12.5) if conflicting_slot else None,
        "events": [],
    }


@pytest.mark.parametrize("verdict,cell", [((90.0, True), "1:30"), ((None, True), "?")])
def test_uncached_retained_duration_hydrates_new_scan(rig, monkeypatch, verdict, cell):
    api, controller, rows, folder, loops, workers, _sent = rig
    original = (folder / "old.mkv").read_bytes()
    api.list_rows()
    rid = rows.rows()[0]["id"]
    captured = rows.resolve(rid)
    entered, release = pause_foreground(monkeypatch, verdict)
    with running(lambda: controller._probe_now([(rid, captured)])):
        try:
            assert entered.wait(5)
            captured.path.write_bytes(b"a different recording")
            api.list_rows()
            replacement = rows.resolve(rows.rows()[0]["id"])
            workers[-1].target()
            loops[-1].callback()
        finally:
            release.set()
    before = (
        duration_state(captured),
        disk_duration(controller, captured),
        disk_duration(controller, replacement),
    )
    # Restore the original version in the real temporary tree. Its still-held
    # upload capture is the only place its refused-cache winner can survive.
    captured.path.write_bytes(original)
    os.utime(captured.path, (captured.mtime, captured.mtime))
    worker_count = len(workers)
    api.list_rows()
    current = rows.resolve(rows.rows()[0]["id"])
    after = (
        duration_state(current),
        rows.rows()[0]["duration"],
        disk_duration(controller, current),
        len(workers) - worker_count,
        current is captured,
    )
    assert (before, after) == (
        ((verdict[0], True, True), (False, None), (True, 12.5)),
        ((verdict[0], True, True), cell, (True, verdict[0]), 0, False),
    )


def test_full_upload_refresh_keeps_duration_url_and_work_gate(rig, monkeypatch):
    api, controller, rows, _folder, loops, workers, sent = rig
    _end, posts = log_posts(rig, monkeypatch)
    fakes.stub_auth(monkeypatch)
    fakes.install_google(monkeypatch, fakes.FakeYouTube())
    monkeypatch.setattr(uploader, "upload", lambda *args, **kwargs: "uploaded")
    api._confirm = fakes.Answers(True)
    api.list_rows()
    rid = rows.rows()[0]["id"]
    captured = rows.resolve(rid)
    entered, release = pause_foreground(monkeypatch)
    api.start_upload("Fight", "", False, [rid])
    try:
        assert entered.wait(5)
        during = (
            controller.busy(),
            links.lookup(
                links.load(controller._links_file),
                captured.path,
                captured.size,
                captured.mtime,
            ),
        )
        api.list_rows()
        workers[-1].target()
        loops[-1].callback()
    finally:
        release.set()
        controller._upload_thread.join(5)
        assert not controller._upload_thread.is_alive()
    current = rows.resolve(rows.rows()[0]["id"])
    assert {
        "during": during,
        "busy_after": controller.busy(),
        "capture": duration_state(captured),
        "current": duration_state(current),
        "cell": rows.rows()[0]["duration"],
        "disk": disk_duration(controller, captured),
        "url": links.lookup(
            links.load(controller._links_file),
            captured.path,
            captured.size,
            captured.mtime,
        ),
        "shown_url": rows.rows()[0]["link"],
        "post_windows": [(p["window_start"], p["window_end"]) for p in posts],
        "skipped": any(
            "Combat logs skipped" in p["text"] for p in fakes.payloads(sent, "onStatus")
        ),
    } == {
        "during": (True, uploader.watch_url("uploaded")),
        "busy_after": False,
        "capture": (12.5, True, True),
        "current": (12.5, True, True),
        "cell": "0:12",
        "disk": (True, 12.5),
        "url": uploader.watch_url("uploaded"),
        "shown_url": uploader.watch_url("uploaded"),
        "post_windows": [
            ("2026-09-08T11:59:47.500000+00:00", "2026-09-08T12:00:00+00:00")
        ],
        "skipped": False,
    }


def test_row_installations_keep_mappings_coherent_during_concurrent_reads(rig):
    _api, _controller, rows, folder, _loops, _workers, _sent = rig
    infos = rows.scan(folder)
    seen = set()
    barrier = threading.Barrier(3)

    def install():
        barrier.wait(5)
        for _ in range(100):
            result = rows.install(infos)
            ids = {row["id"] for row in result}
            # Capture each installation's returned payload, not rows() from
            # a possibly newer installation. IDs can never be reissued.
            with seen_lock:
                assert not ids & seen
                seen.update(ids)

    seen_lock = threading.Lock()
    with running(install), running(install):
        barrier.wait(5)
        for _ in range(100):
            rendered = rows.rows()
            resolved = rows.resolve_many([row["id"] for row in rendered])
            assert all(info.path == folder / "old.mkv" for info in resolved)
    assert len(seen) == 200


@pytest.mark.parametrize("stale", [False, True])
def test_completed_link_is_durable_before_unrelated_publication_unblocks(rig, stale):
    api, controller, rows, _folder, loops, workers, sent = rig
    api.list_rows()
    workers[-1].target()
    loops[-1].callback()  # Warm cache: the blocked refresh needs no probe worker.
    rid = rows.rows()[0]["id"]
    captured = rows.resolve(rid)
    gate = ObservedGate()
    controller._publication_lock = gate
    entered, release = threading.Event(), threading.Event()
    publish = controller._ports.publish_rows

    def blocked(payload):
        entered.set()
        assert release.wait(5)
        publish(payload)

    controller._ports = replace(controller._ports, publish_rows=blocked)
    with running(api.list_rows):
        assert entered.wait(5)
        if not stale:
            rid = rows.rows()[0]["id"]
            captured = rows.resolve(rid)
        with running(lambda: controller._link(rid, "uploaded", captured)):
            try:
                assert gate.contended.wait(5)
                assert links.lookup(
                    links.load(controller._links_file),
                    captured.path,
                    captured.size,
                    captured.mtime,
                ) == uploader.watch_url("uploaded")
                assert not fakes.payloads(sent, "onLink")
            finally:
                release.set()
    assert bool(fakes.payloads(sent, "onLink")) is not stale
    assert links.lookup(
        links.load(controller._links_file), captured.path, captured.size, captured.mtime
    ) == uploader.watch_url("uploaded")


@pytest.mark.parametrize(
    "names", [("renamed",), ("renamed", "final"), ("renamed", "old")]
)
def test_late_link_follows_renames_of_a_replacement_snapshot(rig, names):
    api, controller, rows, folder, _loops, _workers, sent = rig
    api.list_rows()
    stale_id = rows.rows()[0]["id"]
    captured = rows.resolve(stale_id)
    api.list_rows()
    current_id = rows.rows()[0]["id"]
    for name in names:
        assert api.rename_recording(current_id, name)["ok"]
    controller._link(stale_id, "uploaded", captured)
    destination = folder / (names[-1] + ".mkv")
    stored = links.load(controller._links_file)
    assert links.lookup(
        stored, destination, captured.size, captured.mtime
    ) == uploader.watch_url("uploaded")
    assert set(stored) == {str(destination)}
    assert not fakes.payloads(sent, "onLink"), (
        "a stale ID must not repaint a replacement"
    )
    api.list_rows()
    assert rows.rows()[0]["link"] == uploader.watch_url("uploaded")


def test_rename_tracking_distinguishes_recordings_reusing_the_source_path(rig):
    api, controller, rows, folder, _loops, _workers, _sent = rig
    api.list_rows()
    first_id = rows.rows()[0]["id"]
    first = rows.resolve(first_id)
    api.list_rows()
    assert api.rename_recording(rows.rows()[0]["id"], "first")["ok"]
    (folder / "old.mkv").write_bytes(b"a different recording at the reused path")
    api.list_rows()
    second_id = next(row["id"] for row in rows.rows() if row["name"] == "old.mkv")
    second = rows.resolve(second_id)
    api.list_rows()
    current_id = next(row["id"] for row in rows.rows() if row["name"] == "old.mkv")
    assert api.rename_recording(current_id, "second")["ok"]
    controller._link(first_id, "first-video", first)
    controller._link(second_id, "second-video", second)
    stored = links.load(controller._links_file)
    assert set(stored) == {str(folder / "first.mkv"), str(folder / "second.mkv")}
    assert links.lookup(
        stored, folder / "first.mkv", first.size, first.mtime
    ) == uploader.watch_url("first-video")
    assert links.lookup(
        stored, folder / "second.mkv", second.size, second.mtime
    ) == uploader.watch_url("second-video")


def test_rename_destination_reuse_keeps_equal_metadata_captures_distinct(rig):
    api, controller, rows, folder, _loops, _workers, _sent = rig
    old_path, second_path = folder / "old.mkv", folder / "second.mkv"
    second_path.write_bytes(old_path.read_bytes())
    for path in (old_path, second_path):
        os.utime(path, (1700000000, 1700000000))
    api.list_rows()
    ids = {row["name"]: row["id"] for row in rows.rows()}
    first, second = rows.resolve(ids["old.mkv"]), rows.resolve(ids["second.mkv"])
    assert (first.size, first.mtime) == (second.size, second.mtime)
    api.list_rows()
    current = {row["name"]: row["id"] for row in rows.rows()}
    assert api.rename_recording(current["old.mkv"], "renamed")["ok"]
    assert api.rename_recording(current["second.mkv"], "old")["ok"]
    controller._link(ids["old.mkv"], "first", first)
    controller._link(ids["second.mkv"], "second", second)
    stored = links.load(controller._links_file)
    assert set(stored) == {str(folder / "renamed.mkv"), str(old_path)}
    assert links.lookup(
        stored, folder / "renamed.mkv", first.size, first.mtime
    ) == uploader.watch_url("first")
    assert links.lookup(
        stored, old_path, second.size, second.mtime
    ) == uploader.watch_url("second")


def test_new_capture_at_a_reused_name_does_not_inherit_its_former_identity(rig):
    api, controller, rows, folder, _loops, _workers, _sent = rig
    old_path = folder / "old.mkv"
    os.utime(old_path, (1700000000, 1700000000))
    api.list_rows()
    old_id = rows.rows()[0]["id"]
    old_capture = rows.resolve(old_id)
    api.list_rows()
    assert api.rename_recording(rows.rows()[0]["id"], "renamed")["ok"]
    old_path.write_bytes((folder / "renamed.mkv").read_bytes())
    os.utime(old_path, (1700000000, 1700000000))
    api.list_rows()
    new_id = next(row["id"] for row in rows.rows() if row["name"] == "old.mkv")
    new_capture = rows.resolve(new_id)
    assert (old_capture.size, old_capture.mtime) == (
        new_capture.size,
        new_capture.mtime,
    )
    controller._link(old_id, "original", old_capture)
    controller._link(new_id, "new", new_capture)
    stored = links.load(controller._links_file)
    assert links.lookup(
        stored, folder / "renamed.mkv", old_capture.size, old_capture.mtime
    ) == uploader.watch_url("original")
    assert links.lookup(
        stored, old_path, new_capture.size, new_capture.mtime
    ) == uploader.watch_url("new")
    assert api.copy_path(new_id) == uploader.watch_url("new")


@pytest.mark.parametrize("stale", [False, True])
@pytest.mark.parametrize("pause_at", ["filesystem", "store_save", "row_repoint"])
def test_rename_identity_transition_excludes_link_but_its_publication_does_not(
    rig, monkeypatch, stale, pause_at
):
    api, controller, rows, folder, _loops, _workers, sent = rig
    api.list_rows()
    rid = rows.rows()[0]["id"]
    captured = rows.resolve(rid)
    if stale:
        api.list_rows()
    current_id = rows.rows()[0]["id"]
    old_path, new_path = folder / "old.mkv", folder / "renamed.mkv"
    store_gate, publication_gate = ObservedGate(), ObservedGate()
    controller._link_store_lock = store_gate
    controller._publication_lock = publication_gate
    transition, finish_transition = threading.Event(), threading.Event()
    publishing, finish_publication = threading.Event(), threading.Event()

    def paused(original, *args, **kwargs):
        result = original(*args, **kwargs)
        if not transition.is_set():
            transition.set()
            assert finish_transition.wait(5)
        return result

    if pause_at == "filesystem":
        original = type(old_path).rename
        monkeypatch.setattr(
            type(old_path), "rename", lambda *a, **k: paused(original, *a, **k)
        )
    elif pause_at == "store_save":
        original = links.save
        monkeypatch.setattr(links, "save", lambda *a, **k: paused(original, *a, **k))
    else:
        original = rows.rename

        def before_repoint(*args):
            transition.set()
            assert finish_transition.wait(5)
            original(*args)

        monkeypatch.setattr(rows, "rename", before_repoint)
    publish = controller._ports.publish_row_renamed

    def blocked_publication(payload):
        publishing.set()
        assert finish_publication.wait(5)
        publish(payload)

    controller._ports = replace(
        controller._ports, publish_row_renamed=blocked_publication
    )
    with running(lambda: api.rename_recording(current_id, "renamed")):
        assert transition.wait(5)
        with running(lambda: controller._link(rid, "uploaded", captured)):
            try:
                assert store_gate.contended.wait(5)
                finish_transition.set()
                assert publishing.wait(5)
                assert publication_gate.contended.wait(5)
                # The entire rename has committed, but its WebView call has
                # NOT returned. Link evidence must already use the new key.
                stored = links.load(controller._links_file)
                assert set(stored) == {str(new_path)}
                assert links.lookup(
                    stored, new_path, captured.size, captured.mtime
                ) == uploader.watch_url("uploaded")
            finally:
                finish_transition.set()
                finish_publication.set()
    assert bool(fakes.payloads(sent, "onLink")) is not stale


@pytest.mark.parametrize("next_operation", ["upload", "scan"])
def test_link_store_save_is_serialized_with_writers_and_scan_reads(
    rig, monkeypatch, next_operation
):
    api, controller, rows, folder, _loops, _workers, _sent = rig
    (folder / "second.mkv").write_bytes(b"second recording")
    api.list_rows()
    ids = {row["name"]: row["id"] for row in rows.rows()}
    first, second = rows.resolve(ids["old.mkv"]), rows.resolve(ids["second.mkv"])
    gate = ObservedGate()
    controller._link_store_lock = gate
    entered, release = threading.Event(), threading.Event()
    save = links.save
    first_save = True

    def delayed_save(path, store):
        nonlocal first_save
        snapshot = dict(store)
        if first_save:
            first_save = False
            entered.set()
            assert release.wait(5)
        save(path, snapshot)

    monkeypatch.setattr(links, "save", delayed_save)
    with running(lambda: controller._link(ids["old.mkv"], "first", first)):
        assert entered.wait(5)
        action = (
            api.list_rows
            if next_operation == "scan"
            else lambda: controller._link(ids["second.mkv"], "second", second)
        )
        with running(action):
            try:
                assert gate.contended.wait(5)
            finally:
                release.set()
    stored = links.load(controller._links_file)
    assert links.lookup(
        stored, first.path, first.size, first.mtime
    ) == uploader.watch_url("first")
    if next_operation == "upload":
        assert links.lookup(
            stored, second.path, second.size, second.mtime
        ) == uploader.watch_url("second")
    else:
        row = next(row for row in rows.rows() if row["name"] == "old.mkv")
        assert row["link"] == uploader.watch_url("first")


def test_delayed_link_presentation_cannot_regress_a_newer_durable_url(rig):
    api, controller, rows, _folder, _loops, _workers, sent = rig
    api.list_rows()
    rid = rows.rows()[0]["id"]
    info = rows.resolve(rid)
    entered, release = threading.Event(), threading.Event()

    class PauseFirstGate:
        def __init__(self):
            self.first = True
            self.lock = threading.Lock()

        def __enter__(self):
            if self.first:
                self.first = False
                entered.set()
                assert release.wait(5)
            self.lock.acquire()

        def __exit__(self, *args):
            self.lock.release()

    controller._publication_lock = PauseFirstGate()
    with running(lambda: controller._link(rid, "earlier", info)):
        assert entered.wait(5)
        try:
            assert links.lookup(
                links.load(controller._links_file), info.path, info.size, info.mtime
            ) == uploader.watch_url("earlier")
            controller._link(rid, "later", info)
        finally:
            release.set()
    assert links.lookup(
        links.load(controller._links_file), info.path, info.size, info.mtime
    ) == uploader.watch_url("later")
    assert rows.rows()[0]["link"] == uploader.watch_url("later")
    assert fakes.payloads(sent, "onLink") == [
        {"id": rid, "url": uploader.watch_url("later")}
    ]
