"""Lane E: real rows/controller, with only scanning and worker timing controlled."""

import os
import queue
import threading
from contextlib import contextmanager
from dataclasses import replace

import pytest

from tests import fakes
from wingman import durations, library, links, uploader
from wingman.ui.rows import RowSnapshot


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
