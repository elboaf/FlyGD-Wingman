"""Settings acknowledgements must follow serialized, durable decisions."""

import contextlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from tests import fakes
from wingman import paths, settings


def test_scalar_retry_does_not_acknowledge_another_writers_tentative_value(
    monkeypatch, tmp_path
):
    api, _ = fakes.build_api(tmp_path)
    api._state.settings["privacy"] = "public"
    settings.save(api._state.settings)
    entered_save = threading.Event()
    release_save = threading.Event()
    retry_observed = threading.Event()
    real_save = settings._save_locked
    real_lock = settings._SAVE_LOCK
    attempts = []

    class ObservedLock:
        def __enter__(self):
            if threading.current_thread().name.startswith("retry"):
                retry_observed.set()
            return real_lock.__enter__()

        def __exit__(self, *args):
            return real_lock.__exit__(*args)

    def save(data, path=None):
        attempts.append(data["privacy"])
        if len(attempts) == 1:
            entered_save.set()
            assert release_save.wait(10)
            raise OSError("injected write failure")
        real_save(data, path)

    def retry():
        try:
            return api.set_privacy("private")
        finally:
            # The broken no-op path returns without even entering the lock.
            retry_observed.set()

    monkeypatch.setattr(settings, "_SAVE_LOCK", ObservedLock())
    monkeypatch.setattr(settings, "_save_locked", save)
    with (
        ThreadPoolExecutor(max_workers=1) as first_pool,
        ThreadPoolExecutor(max_workers=1, thread_name_prefix="retry") as retry_pool,
    ):
        first = first_pool.submit(api.set_privacy, "private")
        try:
            assert entered_save.wait(10)
            second = retry_pool.submit(retry)
            assert retry_observed.wait(10)
        finally:
            release_save.set()
        first_result = first.result(timeout=10)
        second_result = second.result(timeout=10)

    assert first_result["applied"] is False
    assert second_result == {"applied": True, "persisted": True, "error": None}
    assert attempts == ["private", "private"]
    assert api._state.settings["privacy"] == "private"
    assert json.loads(paths.settings_file().read_text())["privacy"] == "private"


@pytest.mark.parametrize("member", [True, False])
@pytest.mark.parametrize(
    "method, key",
    [
        ("set_never_minimize", "never_minimize"),
        ("set_preview_excluded", "excluded"),
        ("set_preview_locked", "locked"),
    ],
)
def test_concurrent_roster_changes_keep_both_accepted_choices(
    monkeypatch, tmp_path, member, method, key
):
    api, _ = fakes.build_api(tmp_path)
    api._state.settings["preview"][key] = [] if member else ["Alice", "Bob"]
    rendezvous = threading.Barrier(2)
    real_update = settings.update

    @contextlib.contextmanager
    def synchronized_update(data, path=None):
        # Pause both callers immediately before serialization. On the old
        # code each has already built its replacement from the same roster.
        rendezvous.wait(timeout=10)
        with real_update(data, path) as doc:
            yield doc

    monkeypatch.setattr(settings, "update", synchronized_update)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(getattr(api, method), "Alice", member)
        second = pool.submit(getattr(api, method), "Bob", member)
        assert first.result(timeout=10)["persisted"] is True
        assert second.result(timeout=10)["persisted"] is True

    expected = {"Alice", "Bob"} if member else set()
    assert set(api._state.settings["preview"][key]) == expected
    assert (
        set(json.loads(paths.settings_file().read_text())["preview"][key]) == expected
    )


@pytest.mark.parametrize(
    "method, args, expected",
    [
        ("set_minimize_inactive_clients", (True,), {"minimize_inactive_clients": True}),
        ("set_preview_default_size", (640, 360), {"width": 640, "height": 360}),
        (
            "set_restore_preview_positions",
            (False,),
            {"restore_preview_positions": False},
        ),
        (
            "set_preview_locked",
            ("Alice", True),
            {"lock_default": False, "locked": ["Alice"]},
        ),
    ],
)
def test_preview_decisions_ignore_a_rolled_back_concurrent_candidate(
    monkeypatch, tmp_path, method, args, expected
):
    api, _ = fakes.build_api(tmp_path)
    settings.save(api._state.settings)
    entered_save = threading.Event()
    release_save = threading.Event()
    retry_observed = threading.Event()
    real_save = settings._save_locked
    real_lock = settings._SAVE_LOCK
    attempts = []

    class ObservedLock:
        def __enter__(self):
            if threading.current_thread().name.startswith("retry"):
                retry_observed.set()
            return real_lock.__enter__()

        def __exit__(self, *exc):
            return real_lock.__exit__(*exc)

    def save(data, path=None):
        attempts.append(1)
        if len(attempts) == 1:
            entered_save.set()
            assert release_save.wait(10)
            raise OSError("injected write failure")
        real_save(data, path)

    def retry():
        try:
            return getattr(api, method)(*args)
        finally:
            retry_observed.set()

    # For Lock, hold a tentative default change rather than an identical
    # write: effective membership must be computed after that rollback.
    first_method = (
        "set_preview_lock_default" if method == "set_preview_locked" else method
    )
    first_args = (True,) if method == "set_preview_locked" else args
    monkeypatch.setattr(settings, "_SAVE_LOCK", ObservedLock())
    monkeypatch.setattr(settings, "_save_locked", save)
    with (
        ThreadPoolExecutor(max_workers=1) as first_pool,
        ThreadPoolExecutor(max_workers=1, thread_name_prefix="retry") as retry_pool,
    ):
        first = first_pool.submit(getattr(api, first_method), *first_args)
        try:
            assert entered_save.wait(10)
            second = retry_pool.submit(retry)
            assert retry_observed.wait(10)
        finally:
            release_save.set()
        first_result = first.result(timeout=10)
        second_result = second.result(timeout=10)

    assert first_result["applied"] is False
    assert second_result["persisted"] is True
    assert len(attempts) == 2
    persisted = json.loads(paths.settings_file().read_text())["preview"]
    for key, value in expected.items():
        assert api._state.settings["preview"][key] == value
        assert persisted[key] == value
