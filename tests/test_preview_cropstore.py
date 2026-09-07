"""Crop persistence races exercised at the real settings transaction boundary."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Event, Thread

import pytest

from wingman import paths, settings
from wingman.preview.crops import CropDefinition, serialize, source_from_pixels
from wingman.preview.geometry import Rect
from wingman.telemetry.model import ClientSessionId, RosterClient, RosterSnapshot


def definition(x=40):
    return CropDefinition(
        source_from_pixels(Rect(0, 0, 320, 180), (1280, 720)),
        Rect(x, 50, 320, 180),
    )


@pytest.fixture
def make_store():
    from wingman.preview.cropstore import CropStore

    stores = []

    def make(initial=None, update=None, **kwargs):
        live = settings.load()
        if initial:
            live["preview"]["crops"] = serialize(initial)
            settings.save(live)
        executor_factory = kwargs.pop(
            "executor_factory", lambda: ThreadPoolExecutor(max_workers=1)
        )
        store = CropStore(
            update or (lambda: settings.update(live)),
            initial or {},
            executor_factory=executor_factory,
            **kwargs,
        )
        stores.append(store)
        return store, live

    yield make
    for store in stores:
        store.close().result(timeout=3)


@pytest.fixture(params=["factory", "submission"])
def startup_failure(request, monkeypatch):
    from types import SimpleNamespace

    state = SimpleNamespace(failing=True, executors=[])

    def fail_start(_):
        raise RuntimeError("worker resources exhausted")

    class Executor(ThreadPoolExecutor):
        def submit(self, fn, *args, **kwargs):
            if state.failing:
                # Keep submit's queued job: real thread-start failure occurs
                # after enqueueing, so merely raising from submit misses it.
                with monkeypatch.context() as patch:
                    patch.setattr(Thread, "start", fail_start)
                    return super().submit(fn, *args, **kwargs)
            return super().submit(fn, *args, **kwargs)

    def factory():
        if state.failing and request.param == "factory":
            raise RuntimeError("worker resources exhausted")
        executor = Executor(max_workers=1)
        state.executors.append(executor)
        return executor

    state.factory = factory
    yield state
    for executor in state.executors:
        executor.shutdown(wait=False)


def test_specific_cancellation_reason_does_not_overwrite_terminal_outcome(make_store):
    store, _ = make_store(initial={"Alice": definition()})
    token = store.begin("Alice", epoch=0, session=None)
    assert store.cancel(token, "Crop limit reached")
    assert not store.cancel(token, "Later refusal")
    assert (
        store.snapshot()["operations"][token.operation_id]["error"]
        == "Crop limit reached"
    )
    success = store.begin("Alice", epoch=0, session=None)
    assert store.set_enabled(success, False).result(3).persisted
    before = store.snapshot()
    assert not store.cancel(success, "Too late")
    assert store.snapshot() == before


def test_host_reuses_incomplete_offline_drain_on_repeated_stop(make_store, monkeypatch):
    from wingman.preview.host import PreviewHost

    store, _live = make_store(initial={"Alice": definition()})
    entered, release = Event(), Event()
    original = settings._save_locked

    def delayed(data, path=None):
        entered.set()
        assert release.wait(5)
        original(data, path)

    monkeypatch.setattr(settings, "_save_locked", delayed)
    host = PreviewHost(on_layout_changed=lambda *args: None, crop_store=store)
    try:
        host.request_crop("enabled", "Alice", False)
        assert entered.wait(5)
        assert not host.stop(timeout=0)
        first = host._stop_future
        assert not host.stop(timeout=0)
        assert host._stop_future is first
        assert host.is_stopping
    finally:
        release.set()
        host.stop(final=True)


def test_offline_host_does_not_retain_an_unbounded_native_completion_mailbox(
    make_store,
):
    from wingman.preview.host import PreviewHost

    store, _live = make_store(initial={"Alice": definition()})
    host = PreviewHost(on_layout_changed=lambda *args: None, crop_store=store)
    try:
        for _ in range(40):
            host.request_crop("remove", "Alice")
            store.drain().result(3)
        assert len(store.snapshot()["operations"]) == 32
        assert host._crop_completions.empty()
        assert host.crop_state()["definitions"] == {}
    finally:
        host.stop(final=True)


def test_startup_failure_resolves_token_and_allows_new_submission(
    make_store, startup_failure
):
    store, live = make_store(
        initial={"Alice": definition()}, executor_factory=startup_failure.factory
    )
    token = store.begin("Alice", epoch=1, session=None)
    future = store.put(token, definition(500))
    result = future.result(timeout=3)
    assert not result.applied and not result.persisted
    assert "worker resources exhausted" in result.error
    assert store.put(token, definition(500)) is future
    outcome = store.snapshot()["operations"][token.operation_id]
    assert not outcome["pending"] and outcome["error"] == result.error
    assert outcome["revision"] == result.revision
    assert store.snapshot()["definitions"]["Alice"]["window"]["x"] == 40
    assert store.snapshot()["generations"]["Alice"] == 0
    assert live["preview"]["crops"]["Alice"]["window"]["x"] == 40
    for executor in startup_failure.executors:
        with pytest.raises(RuntimeError, match="shutdown"):
            executor.submit(lambda: None)

    startup_failure.failing = False
    later = store.begin("Alice", epoch=1, session=None)
    assert store.set_enabled(later, False).result(timeout=3).persisted
    assert store.put(token, definition(500)) is future
    assert not settings.load()["preview"]["crops"]["Alice"]["enabled"]
    assert settings.load()["preview"]["crops"]["Alice"]["window"]["x"] == 40
    closing = store.close()
    assert closing.result(timeout=3)
    assert store.close() is closing
    assert store.drain() is closing


@pytest.mark.parametrize("barrier", ["drain", "close"])
def test_first_primary_barrier_startup_failure_completes_false(
    make_store, startup_failure, barrier
):
    flushed = []
    store, _ = make_store(
        executor_factory=startup_failure.factory,
        flush_primary=lambda: flushed.append(True),
    )
    future = getattr(store, barrier)()
    assert not future.result(timeout=3)
    assert not flushed
    startup_failure.failing = False
    if barrier == "drain":
        assert store.drain().result(timeout=3)
        assert flushed == [True]
        closing = store.close()
        assert closing.result(timeout=3)
    else:
        closing = future
        assert not store.close().result(timeout=3)
        assert not flushed
    assert store.close() is closing
    assert store.drain() is closing


@pytest.mark.parametrize("barrier", ["drain", "close"])
def test_geometry_startup_failure_retains_delta_and_reports_failed_barrier(
    make_store, startup_failure, barrier
):
    store, _ = make_store(
        initial={"Alice": definition()},
        executor_factory=startup_failure.factory,
        debounce_s=3600,
    )
    store.record_geometry("Alice", 0, 1, Rect(91, 92, 320, 180))
    assert store.snapshot()["definitions"]["Alice"]["window"]["x"] == 40
    future = getattr(store, barrier)()
    assert not future.result(timeout=3)
    assert settings.load()["preview"]["crops"]["Alice"]["window"]["x"] == 40
    startup_failure.failing = False
    if barrier == "drain":
        assert store.drain().result(timeout=3)
        assert store.snapshot()["definitions"]["Alice"]["window"]["x"] == 91
        assert store.snapshot()["generations"]["Alice"] == 0
        assert settings.load()["preview"]["crops"]["Alice"]["window"]["x"] == 91
    else:
        assert store.close() is future
        assert store.drain() is future
        assert not future.result(timeout=3)


def test_startup_failure_delivers_completion_outside_metadata_lock(make_store):
    checked = Event()
    failures = []
    closes = []

    def callback(future):
        def check():
            try:
                assert not future.result().persisted
                assert not store.snapshot()["operations"][token.operation_id]["pending"]
                with settings.update(live) as document:
                    document["channel_title"] = "still writable"
                closes.append(store.close())
            except Exception as exc:  # noqa: BLE001 -- propagate thread failures to the test's asserting thread.
                failures.append(exc)
            finally:
                checked.set()

        Thread(target=check).start()
        if not checked.wait(3):
            failures.append("startup completion invoked under a lock")

    def factory():
        # Observe the already accepted token before this synchronous startup
        # attempt fails, so callback registration cannot race completion.
        future = store.put(token, definition())
        assert not future.done()
        future.add_done_callback(callback)
        raise RuntimeError("worker resources exhausted")

    store, live = make_store(executor_factory=factory)
    token = store.begin("Alice", epoch=1, session=None)
    assert not store.put(token, definition()).result(timeout=3).persisted
    assert checked.wait(3)
    assert not failures
    assert closes[0].result(timeout=3)


def test_failed_submission_cannot_leave_a_late_dispatcher_running(make_store):
    dispatched = []

    class Executor(ThreadPoolExecutor):
        def submit(self, fn, *args, **kwargs):
            dispatched.append(super().submit(fn, *args, **kwargs))
            raise RuntimeError("submission failed after scheduling")

    store, _ = make_store(executor_factory=lambda: Executor(max_workers=1))
    token = store.begin("Alice", epoch=1, session=None)
    assert not store.put(token, definition()).result(timeout=3).persisted
    assert dispatched[0].result(timeout=3) is None
    assert store.snapshot()["definitions"] == {}
    assert not paths.settings_file().exists()
    assert store.close().result(timeout=3)


def test_success_is_exposed_only_after_transaction_returns(make_store, monkeypatch):
    entered, release = Event(), Event()
    original = settings.atomicio.write_atomic

    def blocked_write(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        return original(*args, **kwargs)

    monkeypatch.setattr(settings.atomicio, "write_atomic", blocked_write)
    store, live = make_store()
    token = store.begin("Alice", epoch=1, session=None)
    future = store.put(token, definition())
    try:
        assert entered.wait(3)
        assert "Alice" in live["preview"]["crops"]  # Tentative, not authority.
        assert store.snapshot()["definitions"] == {}
        assert store.snapshot()["operations"][token.operation_id]["pending"]
        assert not future.done()
    finally:
        release.set()
    result = future.result(timeout=3)
    assert result.applied and result.persisted and result.error is None
    assert store.snapshot()["definitions"]["Alice"]["window"]["x"] == 40
    assert settings.load()["preview"]["crops"]["Alice"]["window"]["x"] == 40


def test_cancel_waiting_for_settings_lock_writes_nothing(make_store):
    attempted = Event()
    live = settings.load()

    @contextmanager
    def update():
        attempted.set()
        with settings.update(live) as document:
            yield document

    store, _ = make_store(update=update)
    with settings._SAVE_LOCK:
        token = store.begin("Alice", epoch=1, session=None)
        future = store.put(token, definition())
        assert attempted.wait(3)
        assert store.cancel(token)
    result = future.result(timeout=3)
    assert not result.applied and not result.persisted and result.error
    assert store.drain().result(timeout=3)
    assert live["preview"]["crops"] == {}
    assert not paths.settings_file().exists()


@contextmanager
def blocked_save(monkeypatch, *, fail=False):
    entered, release = Event(), Event()
    original = settings.atomicio.write_atomic

    def write(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        if fail:
            raise OSError("disk full")
        return original(*args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(settings.atomicio, "write_atomic", write)
        try:
            yield entered
        finally:
            release.set()


def roster(generation=1, session_generation=1):
    session = ClientSessionId(10, 20, "Alice", session_generation)
    return RosterSnapshot(
        generation, (RosterClient(10, 20, "EVE - Alice", "Alice", session),)
    )


def source_token(store):
    store.open_epoch(1)
    snapshot = roster()
    store.observe_roster(1, snapshot)
    return store.begin("Alice", epoch=1, session=snapshot.clients[0].session)


def test_fence_during_admitted_write_keeps_real_success(make_store, monkeypatch):
    store, _ = make_store()
    token = source_token(store)
    with blocked_save(monkeypatch) as entered:
        future = store.put(token, definition())
        assert entered.wait(3)
        store.fence_epoch(1)
        assert not store.cancel(token)
        assert not future.done()
    assert future.result(timeout=3).persisted
    assert "Alice" in store.snapshot()["definitions"]


@pytest.mark.parametrize("fence", ["epoch", "loss", "renew", "new_epoch"])
def test_source_fences_cancel_before_admission(make_store, fence):
    attempted = Event()
    live = settings.load()

    @contextmanager
    def update():
        attempted.set()
        with settings.update(live) as document:
            yield document

    store, _ = make_store(update=update)
    token = source_token(store)
    with settings._SAVE_LOCK:
        future = store.put(token, definition())
        assert attempted.wait(3)
        if fence == "epoch":
            store.fence_epoch(1)
        elif fence == "loss":
            store.observe_roster(1, RosterSnapshot(2))
        elif fence == "renew":
            store.observe_roster(1, roster(2, 2))
        else:
            store.open_epoch(2)
    assert not future.result(timeout=3).persisted
    assert store.drain().result(timeout=3)
    assert not paths.settings_file().exists()


def test_old_roster_and_epoch_cannot_restore_authorization(make_store):
    store, _ = make_store()
    token = source_token(store)
    store.observe_roster(1, roster(3, 2))
    store.observe_roster(1, roster(2, 1))
    store.observe_roster(0, roster(100, 1))
    store.open_epoch(0)
    assert not store.put(token, definition()).result(timeout=3).persisted
    current = store.begin("Alice", epoch=1, session=roster(3, 2).clients[0].session)
    assert store.put(current, definition()).result(timeout=3).persisted
    store.fence_epoch(1)
    store.open_epoch(1)  # The same lifetime cannot be reopened after fencing.
    stale = store.begin("Alice", epoch=1, session=current.session)
    assert not store.put(stale, definition()).result(timeout=3).persisted


def test_master_off_configuration_patches_latest_success(make_store, monkeypatch):
    store, _ = make_store()
    first = source_token(store)
    with blocked_save(monkeypatch) as entered:
        put = store.put(first, definition())
        assert entered.wait(3)
        store.fence_epoch(1)
        second = store.begin("Alice", epoch=1, session=None)
        disable = store.set_enabled(second, False)
    assert put.result(timeout=3).persisted
    assert disable.result(timeout=3).persisted
    assert not store.snapshot()["definitions"]["Alice"]["enabled"]
    assert store.snapshot()["generations"]["Alice"] == second.generation
    assert put.result().revision < disable.result().revision


def test_successful_remove_after_admitted_put_stays_removed(make_store, monkeypatch):
    store, _ = make_store()
    first = store.begin("Alice", epoch=1, session=None)
    with blocked_save(monkeypatch) as entered:
        put = store.put(first, definition())
        assert entered.wait(3)
        second = store.begin("Alice", epoch=1, session=None)
        remove = store.remove(second)
    assert put.result(timeout=3).persisted
    assert remove.result(timeout=3).persisted
    assert store.snapshot()["definitions"] == {}
    assert store.snapshot()["generations"]["Alice"] == second.generation
    assert settings.load()["preview"]["crops"] == {}


def test_failed_remove_keeps_prior_success_and_worker_survives(make_store, monkeypatch):
    store, _ = make_store()
    first = store.begin("Alice", epoch=1, session=None)
    assert store.put(first, definition()).result(timeout=3).persisted
    with blocked_save(monkeypatch, fail=True) as entered:
        second = store.begin("Alice", epoch=1, session=None)
        remove = store.remove(second)
        assert entered.wait(3)
    result = remove.result(timeout=3)
    assert not result.applied and not result.persisted
    assert "disk full" in result.error
    assert store.snapshot()["generations"]["Alice"] == first.generation
    assert store.snapshot()["definitions"]["Alice"]["window"]["x"] == 40
    third = store.begin("Alice", epoch=1, session=None)
    assert store.set_enabled(third, False).result(timeout=3).persisted


def test_callbacks_run_outside_both_locks_and_may_close(make_store):
    store, live = make_store()
    callback_done = Event()
    failures = []
    closes = []

    def callback(_):
        def check():
            try:
                assert "Alice" in store.snapshot()["definitions"]
                with settings.update(live) as document:
                    document["channel_title"] = "still writable"
                closes.append(store.close())
            except Exception as exc:  # noqa: BLE001 -- propagate thread failures to the test's asserting thread.
                failures.append(exc)
            finally:
                callback_done.set()

        Thread(target=check).start()
        if not callback_done.wait(3):
            failures.append("callback invoked under a lock")

    token = store.begin("Alice", epoch=1, session=None)
    store.put(token, definition()).add_done_callback(callback)
    assert callback_done.wait(3)
    assert not failures
    assert closes[0].result(timeout=3)


def test_never_used_close_is_lazy_idempotent_and_refuses_begin(make_store):
    def forbidden():
        pytest.fail("Untouched store must not start a worker")

    store, _ = make_store(executor_factory=forbidden)
    first = store.close()
    assert first.result(timeout=3)
    assert store.close() is first
    with pytest.raises(RuntimeError, match="closed"):
        store.begin("Alice", epoch=1, session=None)


def test_cancel_and_close_resolve_begun_but_unqueued_selection(make_store):
    store, _ = make_store()
    first = store.begin("Alice", epoch=1, session=None)
    second = store.begin("Bob", epoch=1, session=None)
    assert store.cancel(first)
    assert not store.cancel(first)
    assert store.close().result(timeout=3)
    assert not store.put(first, definition()).result(timeout=3).persisted
    assert not store.put(second, definition()).result(timeout=3).persisted
    assert all(not op["pending"] for op in store.snapshot()["operations"].values())


def test_recent_outcome_bound_never_evicts_pending(make_store):
    from wingman.preview.cropstore import RECENT_RESULT_LIMIT

    store, _ = make_store()
    pending = store.begin("Selecting", epoch=1, session=None)
    for i in range(RECENT_RESULT_LIMIT + 2):
        token = store.begin(str(i), epoch=1, session=None)
        assert store.cancel(token)
    snapshot = store.snapshot()
    assert len(snapshot["operations"]) == RECENT_RESULT_LIMIT + 1
    assert snapshot["operations"][pending.operation_id]["pending"]
    snapshot["operations"].clear()
    assert store.snapshot()["operations"]


def test_restored_generation_is_committed_not_a_prospective_reservation(make_store):
    initial = {"Alice": definition()}
    store, _ = make_store(initial=initial, debounce_s=3600)
    generation = store.snapshot()["generations"]["Alice"]
    token = store.begin("Alice", epoch=1, session=None)
    assert token.generation != generation
    initial.clear()
    store.record_geometry("Alice", generation, 1, Rect(91, 92, 320, 180))
    assert store.drain().result(timeout=3)
    state = store.snapshot()
    assert state["definitions"]["Alice"]["window"]["x"] == 91
    assert state["generations"]["Alice"] == generation
    state["definitions"]["Alice"]["window"]["x"] = -500
    state["generations"].clear()
    assert store.snapshot()["definitions"]["Alice"]["window"]["x"] == 91


@pytest.mark.parametrize("action", ["remove", "disable"])
def test_geometry_cannot_create_or_reenable_after_definition_change(make_store, action):
    store, _ = make_store(initial={"Alice": definition()}, debounce_s=3600)
    generation = store.snapshot()["generations"]["Alice"]
    token = store.begin("Alice", epoch=1, session=None)
    store.record_geometry("Nobody", generation, 1, Rect(1, 2, 30, 40))
    store.record_geometry("Alice", generation, 1, Rect(91, 92, 320, 180))
    if action == "remove":
        result = store.remove(token).result(timeout=3)
    else:
        result = store.set_enabled(token, False).result(timeout=3)
    assert result.persisted
    store.record_geometry("Alice", generation, 2, Rect(81, 82, 320, 180))
    store.record_geometry("Alice", token.generation, 3, Rect(71, 72, 320, 180))
    assert store.drain().result(timeout=3)
    definitions = store.snapshot()["definitions"]
    assert "Nobody" not in definitions
    if action == "remove":
        assert "Alice" not in definitions
    else:
        assert not definitions["Alice"]["enabled"]
        assert definitions["Alice"]["window"]["x"] == 91


def test_failed_replacement_keeps_old_generation_and_new_movement(
    make_store, monkeypatch
):
    store, _ = make_store(initial={"Alice": definition()}, debounce_s=3600)
    generation = store.snapshot()["generations"]["Alice"]
    store.record_geometry("Alice", generation, 1, Rect(91, 92, 320, 180))
    with blocked_save(monkeypatch, fail=True) as entered:
        token = store.begin("Alice", epoch=1, session=None)
        future = store.put(token, definition(500))
        assert entered.wait(3)
        store.record_geometry("Alice", generation, 2, Rect(81, 82, 320, 180))
        assert store.snapshot()["definitions"]["Alice"]["window"]["x"] == 40
    assert not future.result(timeout=3).persisted
    assert store.snapshot()["generations"]["Alice"] == generation
    store.drain().result(timeout=3)
    assert store.snapshot()["definitions"]["Alice"]["window"]["x"] == 81
    assert settings.load()["preview"]["crops"]["Alice"]["window"]["x"] == 81


def test_movement_during_save_is_rebased_and_persisted_after_replacement(
    make_store, monkeypatch
):
    store, live = make_store(initial={"Alice": definition()}, debounce_s=3600)
    generation = store.snapshot()["generations"]["Alice"]
    store.record_geometry("Alice", generation, 1, Rect(91, 92, 320, 180))
    replacement = CropDefinition(
        source_from_pixels(Rect(320, 180, 320, 180), (1280, 720)),
        Rect(500, 500, 320, 180),
    )
    with blocked_save(monkeypatch) as entered:
        token = store.begin("Alice", epoch=1, session=None)
        future = store.put(token, replacement)
        assert entered.wait(3)
        assert live["preview"]["crops"]["Alice"]["window"]["x"] == 91
        store.record_geometry("Alice", generation, 2, Rect(81, 82, 320, 180))
        drain = store.drain()  # Barrier queued BEFORE the replacement publishes.
    assert future.result(timeout=3).persisted
    assert drain.result(timeout=3)
    state = store.snapshot()
    assert state["generations"]["Alice"] == token.generation
    assert state["definitions"]["Alice"]["source"]["x"] == 0.25
    assert state["definitions"]["Alice"]["window"]["x"] == 81
    store.record_geometry("Alice", generation, 99, Rect(999, 999, 320, 180))
    store.record_geometry("Alice", token.generation, 1, Rect(777, 777, 320, 180))
    assert store.drain().result(timeout=3)
    assert store.snapshot()["definitions"]["Alice"]["window"]["x"] == 81


def test_failed_remove_retains_pending_geometry(make_store, monkeypatch):
    store, _ = make_store(initial={"Alice": definition()}, debounce_s=3600)
    generation = store.snapshot()["generations"]["Alice"]
    with blocked_save(monkeypatch, fail=True) as entered:
        token = store.begin("Alice", epoch=1, session=None)
        future = store.remove(token)
        assert entered.wait(3)
        store.record_geometry("Alice", generation, 1, Rect(91, 92, 320, 180))
    assert not future.result(timeout=3).persisted
    store.drain().result(timeout=3)
    assert store.snapshot()["definitions"]["Alice"]["window"]["x"] == 91


def test_geometry_is_debounced_coalesced_and_sequence_ordered(make_store, monkeypatch):
    store, _ = make_store(initial={"Alice": definition()}, debounce_s=3600)
    calls = []
    original = settings.atomicio.write_atomic

    def write(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr(settings.atomicio, "write_atomic", write)
    generation = store.snapshot()["generations"]["Alice"]
    store.record_geometry("Alice", generation, 2, Rect(91, 92, 320, 180))
    store.record_geometry("Alice", generation, 1, Rect(81, 82, 320, 180))
    assert not calls
    assert store.drain().result(timeout=3)
    assert len(calls) == 1
    store.record_geometry("Alice", generation, 2, Rect(71, 72, 320, 180))
    assert store.drain().result(timeout=3)
    assert len(calls) == 1
    assert store.snapshot()["definitions"]["Alice"]["window"]["x"] == 91


def test_deadline_dispatcher_wakes_without_drain_and_uses_one_executor_job(
    make_store, monkeypatch
):
    submitted = []

    class Executor(ThreadPoolExecutor):
        def submit(self, fn, *args, **kwargs):
            submitted.append(fn)
            return super().submit(fn, *args, **kwargs)

    store, _ = make_store(
        initial={"Alice": definition()},
        debounce_s=0.01,
        executor_factory=lambda: Executor(max_workers=1),
    )
    generation = store.snapshot()["generations"]["Alice"]
    with blocked_save(monkeypatch) as entered:
        store.record_geometry("Alice", generation, 1, Rect(91, 92, 320, 180))
        assert entered.wait(3)
        store.record_geometry("Alice", generation, 2, Rect(81, 82, 320, 180))
    assert store.drain().result(timeout=3)
    assert len(submitted) == 1
    assert store.snapshot()["definitions"]["Alice"]["window"]["x"] == 81


def test_drain_flushes_primary_after_crop_transaction_and_before_later_writes(
    make_store,
):
    primary_entered, release = Event(), Event()
    seen = []
    live = settings.load()

    def flush_primary():
        with settings.update(live) as document:
            seen.append(document["preview"]["crops"]["Alice"]["enabled"])
        primary_entered.set()
        assert release.wait(3)

    store, _ = make_store(
        update=lambda: settings.update(live), flush_primary=flush_primary
    )
    token = store.begin("Alice", epoch=1, session=None)
    store.put(token, definition())
    drain = store.drain()
    try:
        assert primary_entered.wait(3)
        later = store.begin("Alice", epoch=1, session=None)
        future = store.set_enabled(later, False)
        assert not future.done()
        assert not drain.done()
    finally:
        release.set()
    assert drain.result(timeout=3)
    assert future.result(timeout=3).persisted
    assert seen == [True]


def test_failed_geometry_and_primary_flush_resolve_barriers_and_allow_retry(
    make_store, monkeypatch
):
    fail_primary = True

    def primary():
        if fail_primary:
            raise OSError("primary disk full")

    store, _ = make_store(
        initial={"Alice": definition()}, debounce_s=3600, flush_primary=primary
    )
    generation = store.snapshot()["generations"]["Alice"]
    with blocked_save(monkeypatch, fail=True) as entered:
        store.record_geometry("Alice", generation, 1, Rect(91, 92, 320, 180))
        drain = store.drain()
        assert entered.wait(3)
    assert not drain.result(timeout=3)
    assert store.snapshot()["definitions"]["Alice"]["window"]["x"] == 40
    fail_primary = False
    assert store.drain().result(timeout=3)
    assert store.snapshot()["definitions"]["Alice"]["window"]["x"] == 91


def test_close_drains_accepted_configuration_and_geometry(make_store, monkeypatch):
    store, _ = make_store(initial={"Alice": definition()}, debounce_s=3600)
    generation = store.snapshot()["generations"]["Alice"]
    with blocked_save(monkeypatch) as entered:
        token = store.begin("Bob", epoch=1, session=None)
        first = store.put(token, definition())
        assert entered.wait(3)
        token2 = store.begin("Bob", epoch=1, session=None)
        second = store.set_enabled(token2, False)
        store.record_geometry("Alice", generation, 1, Rect(91, 92, 320, 180))
        closing = store.close()
        assert not closing.done()
        assert store.close() is closing
    assert closing.result(timeout=3)
    assert first.result(timeout=3).persisted and second.result(timeout=3).persisted
    assert not store.snapshot()["definitions"]["Bob"]["enabled"]
    assert store.snapshot()["definitions"]["Alice"]["window"]["x"] == 91
    store.record_geometry("Alice", generation, 2, Rect(81, 82, 320, 180))
    assert store.drain() is closing
    assert store.snapshot()["definitions"]["Alice"]["window"]["x"] == 91


def test_empty_drain_does_not_start_worker(make_store):
    def forbidden():
        pytest.fail("An empty drain has no work to dispatch")

    store, _ = make_store(executor_factory=forbidden)
    assert store.drain().result(timeout=3)


def test_future_cancel_cannot_strand_dispatcher_or_shutdown(make_store, monkeypatch):
    store, _ = make_store()
    with blocked_save(monkeypatch) as entered:
        token = store.begin("Alice", epoch=1, session=None)
        future = store.put(token, definition())
        assert entered.wait(3)
        drain = store.drain()
        closing = store.close()
        assert not future.cancel()
        assert not drain.cancel()
        assert not closing.cancel()
    assert future.result(timeout=3).persisted
    assert drain.result(timeout=3)
    assert closing.result(timeout=3)


def test_close_from_worker_completion_does_not_join_itself(make_store, monkeypatch):
    store, _ = make_store()
    finished = Event()
    closes = []

    def callback(_):
        closing = store.close()
        closes.append(closing)
        closing.add_done_callback(lambda _: finished.set())

    with blocked_save(monkeypatch) as entered:
        token = store.begin("Alice", epoch=1, session=None)
        future = store.put(token, definition())
        assert entered.wait(3)
        future.add_done_callback(callback)
    assert finished.wait(3)
    assert closes[0].result(timeout=3)


def test_geometry_transaction_entry_failure_keeps_worker_and_dirty_delta(make_store):
    live = settings.load()
    live["preview"]["crops"] = serialize({"Alice": definition()})
    fail = True

    @contextmanager
    def update():
        if fail:
            raise OSError("cannot enter settings transaction")
        with settings.update(live) as document:
            yield document

    store, _ = make_store(
        initial={"Alice": definition()}, update=update, debounce_s=3600
    )
    generation = store.snapshot()["generations"]["Alice"]
    store.record_geometry("Alice", generation, 1, Rect(91, 92, 320, 180))
    assert not store.drain().result(timeout=3)
    assert store.snapshot()["definitions"]["Alice"]["window"]["x"] == 40
    fail = False
    assert store.drain().result(timeout=3)
    assert store.snapshot()["definitions"]["Alice"]["window"]["x"] == 91


def test_new_reservations_do_not_cancel_earlier_queued_definitions(
    make_store, monkeypatch
):
    store, live = make_store(initial={"Offline": definition(700)})
    with blocked_save(monkeypatch) as entered:
        first = store.begin("Alice", epoch=1, session=None)
        put = store.put(first, definition())
        assert entered.wait(3)
        second = store.begin("Alice", epoch=1, session=None)
        disable = store.set_enabled(second, False)
        third = store.begin("Alice", epoch=1, session=None)
    assert put.result(timeout=3).persisted
    assert disable.result(timeout=3).persisted
    with settings.update(live) as document:
        document["channel_title"] = "Unrelated writer"
    assert store.remove(third).result(timeout=3).persisted
    assert settings.load()["channel_title"] == "Unrelated writer"
    assert settings.load()["preview"]["crops"]["Offline"]["window"]["x"] == 700


def test_set_enabled_missing_definition_fails_without_creation(make_store):
    store, _ = make_store()
    token = store.begin("Alice", epoch=1, session=None)
    result = store.set_enabled(token, True).result(timeout=3)
    assert not result.persisted and "No saved crop" in result.error
    assert not paths.settings_file().exists()


def test_close_cancels_source_waiting_for_settings_but_keeps_configuration(make_store):
    attempted = Event()
    live = settings.load()

    @contextmanager
    def update():
        attempted.set()
        with settings.update(live) as document:
            yield document

    store, _ = make_store(update=update)
    token = source_token(store)
    with settings._SAVE_LOCK:
        source = store.put(token, definition())
        assert attempted.wait(3)
        config_token = store.begin("Offline", epoch=1, session=None)
        config = store.put(config_token, definition())
        closing = store.close()
        assert not closing.done()
    assert closing.result(timeout=3)
    assert not source.result(timeout=3).persisted
    assert config.result(timeout=3).persisted
    assert set(store.snapshot()["definitions"]) == {"Offline"}


def test_failed_queued_remove_preserves_put_that_was_still_saving(
    make_store, monkeypatch
):
    entered, release = Event(), Event()
    original = settings.atomicio.write_atomic
    count = 0

    def write(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 1:
            entered.set()
            assert release.wait(3)
            return original(*args, **kwargs)
        raise OSError("remove disk full")

    monkeypatch.setattr(settings.atomicio, "write_atomic", write)
    store, _ = make_store()
    first = store.begin("Alice", epoch=1, session=None)
    put = store.put(first, definition())
    try:
        assert entered.wait(3)
        later = store.begin("Alice", epoch=1, session=None)
        remove = store.remove(later)
        assert store.snapshot()["definitions"] == {}
    finally:
        release.set()
    assert put.result(timeout=3).persisted
    assert not remove.result(timeout=3).persisted
    assert store.snapshot()["generations"]["Alice"] == first.generation
    assert store.snapshot()["definitions"]["Alice"]["window"]["x"] == 40
    assert settings.load()["preview"]["crops"]["Alice"]["window"]["x"] == 40


def test_movement_flushed_before_put_admission_still_updates_its_destination(
    make_store, monkeypatch
):
    store, _ = make_store(initial={"Alice": definition()}, debounce_s=0)
    generation = store.snapshot()["generations"]["Alice"]
    token = store.begin("Alice", epoch=1, session=None)
    with blocked_save(monkeypatch) as entered:
        store.record_geometry("Alice", generation, 1, Rect(91, 92, 320, 180))
        assert entered.wait(3)
        future = store.put(token, definition(500))
    assert future.result(timeout=3).persisted
    assert store.snapshot()["definitions"]["Alice"]["window"]["x"] == 91
