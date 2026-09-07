"""Settings acknowledgements must follow serialized, durable decisions."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor

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
