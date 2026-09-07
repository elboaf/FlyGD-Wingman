"""Lane E: real rows/controller, with only scanning and worker timing controlled."""

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
