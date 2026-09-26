"""Ordered working geometry through production Api/store/controller seams."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Event

import pytest

from tests.test_api import make_api
from tests.test_preview_cropcontroller import client
from tests.test_preview_host import crop_pump as crop_pump
from tests.test_preview_layout_batch import batch_host as batch_host
from tests.test_preview_layout_batch import roster
from tests.test_preview_layout_batch import writer as writer
from tests.test_preview_presentation import main_api
from tests.test_preview_runtime_review import runtime_pump as runtime_pump
from tests.test_preview_runtime_review import trigger_and_wait_state
from wingman import settings
from wingman.preview.geometry import Rect
from wingman.preview.layout import Entry


def test_every_fresh_sample_advances_even_without_a_value_change(tmp_path):
    api = make_api(tmp_path)
    with settings.update(api._state.settings) as doc:
        doc.setdefault("preview", {}).update(seen=["Alice"], width=500, height=300)
    first = api._sample_preview_geometry()
    second = api._sample_preview_geometry()
    assert first["sizes"] == second["sizes"] == {"Alice": [500, 300]}
    assert second["geometry_revision"] == first["geometry_revision"] + 1
    first["sizes"]["Alice"][0] = 99
    assert api._sample_preview_geometry()["sizes"] == {"Alice": [500, 300]}


def test_full_getter_takes_one_geometry_sample(tmp_path, monkeypatch):
    api = make_api(tmp_path)
    sample = api._sample_preview_geometry
    calls = []

    def observed():
        value = sample()
        calls.append(value)
        return value

    monkeypatch.setattr(api, "_sample_preview_geometry", observed)
    full = api.get_preview_hotkey_state()
    assert len(calls) == 1
    assert {k: full[k] for k in calls[0]} == calls[0]


@pytest.mark.parametrize("method", ["replace", "clear", "transact", "flush"])
def test_store_notifies_only_after_writer_and_settings_release(writer, method):
    store, doc, path, reader = writer
    seen = []

    def committed():
        assert store._write_lock.acquire(False), "callback held writer lock"
        store._write_lock.release()
        with ThreadPoolExecutor(1) as pool:
            # Acquiring the actual settings transaction on another thread proves
            # publication cannot deadlock behind the writer's settings lock.
            def check():
                with settings.update(doc, path):
                    return reader.snapshot()

            seen.append(pool.submit(check).result(3))
        raise RuntimeError("notification failed after durable success")

    store.set_commit_callback(committed)
    entry = Entry(Rect(1, 2, 500, 300))
    if method == "replace":
        assert store.replace("Alice", entry)
    elif method == "clear":
        assert store.clear()
    elif method == "transact":
        assert store.transact(lambda section: section["excluded"].append("Alice"))
    else:
        store.record("Alice", entry)
        store.flush()
    assert len(seen) == 1
    assert settings.load(path)["preview"] == reader.snapshot()


def test_failed_store_save_does_not_notify(writer, monkeypatch):
    store, _, _, _ = writer
    calls = []
    store.set_commit_callback(lambda: calls.append(True))
    monkeypatch.setattr(
        settings, "_save_locked", lambda *a: (_ for _ in ()).throw(OSError("disk"))
    )
    assert not store.replace("Alice", Entry(Rect(1, 2, 500, 300)))
    assert not calls


def test_apply_samples_unchanged_offline_geometry_before_release(tmp_path):
    api = make_api(tmp_path)
    assert api._preview_layout_store.replace("Alice", Entry(Rect(1, 2, 500, 300)))
    saved = api.create_preview_layout("Fleet")
    record = saved["state"]["layouts"][0]
    before = api._sample_preview_geometry()
    observed = []
    release = api._preview_layouts._ports.release

    def check_release(lease):
        observed.append(api._preview_geometry_cache["geometry_revision"])
        release(lease)

    api._preview_layouts._ports = replace(
        api._preview_layouts._ports, release=check_release
    )
    result = api.apply_preview_layout(record["id"], record["revision"])
    assert result["persisted"] and result["live"] == "deferred"
    assert result["geometry"]["sizes"] == {"Alice": [500, 300]}
    assert result["geometry"]["geometry_revision"] > before["geometry_revision"]
    assert observed == [result["geometry"]["geometry_revision"]]


@pytest.mark.parametrize("cached", [False, True])
def test_failed_receipt_sample_retains_cache_without_downgrading_save(
    tmp_path, monkeypatch, cached
):
    api = make_api(tmp_path)
    with settings.update(api._state.settings) as doc:
        doc.setdefault("preview", {})["seen"] = ["Alice"]
    expected = api._sample_preview_geometry() if cached else None
    monkeypatch.setattr(
        api,
        "_sample_preview_geometry",
        lambda: (_ for _ in ()).throw(RuntimeError("sampling failed")),
    )
    result = api.create_preview_layout("Fleet")
    assert result["applied"] and result["persisted"]
    assert result["geometry"] == expected
    assert "sampling failed" in result["warning"]


def test_geometry_ingress_and_writer_do_not_wait_for_sampling_or_page(tmp_path):
    api = make_api(tmp_path)
    entered, release = Event(), Event()
    calls = []

    def page(script):
        calls.append(script)
        entered.set()
        assert release.wait(5)

    api._window.evaluate_js = page
    try:
        with api._preview_geometry_lock, ThreadPoolExecutor(1) as pool:
            pool.submit(api._request_preview_geometry_refresh).result(3)
        assert api._start_presentation()
        assert entered.wait(3)
        with ThreadPoolExecutor(1) as pool:
            assert pool.submit(
                api._preview_layout_store.replace, "Alice", Entry(Rect(1, 2, 600, 300))
            ).result(3)
        assert api._preview_geometry_dirty
        api._close_preview_presentation()
        api._request_preview_geometry_refresh()
        assert not api._preview_geometry_dirty
    finally:
        release.set()
        assert api._stop_fleet_presentation(5)
    assert len(calls) == 1


def test_retained_drag_and_commit_notify_distinct_authorities(
    batch_host, tmp_path, monkeypatch
):
    r = batch_host
    api = main_api(r, tmp_path, monkeypatch)
    trigger_and_wait_state(
        r,
        lambda state: state.eve == "active",
        lambda: r.runtime.set_eve(True, 1),
    )
    roster(r, 1, client())
    r.layouts.replace("Alice", Entry(Rect(1, 2, 500, 300)))
    r.host.sync_layout("Alice", Entry(Rect(1, 2, 500, 300)))
    api._fleet_worker.iterate_once()
    r.call(lambda: r.host._layout_changed("Alice", Rect(4, 5, 600, 400), False))
    assert api._preview_geometry_dirty, "a second drag must notify before debounce"
    sample = api._sample_preview_geometry()
    assert sample["sizes"]["Alice"] == [500, 300]
    assert sample["layout_sources"][0]["geometry"] == {
        "x": 4,
        "y": 5,
        "w": 600,
        "h": 400,
    }
    api._fleet_worker.iterate_once()
    r.layouts.flush()
    assert api._preview_geometry_dirty, (
        "debounce commits change Size's separate authority"
    )
    assert api._sample_preview_geometry()["sizes"]["Alice"] == [600, 400]
    api._fleet_worker.iterate_once()
    r.host.clear_layout_entries()
    assert api._preview_geometry_dirty
    assert api._sample_preview_geometry()["layout_sources"] == []


@pytest.mark.parametrize("companions", [False, True])
def test_off_apply_refreshes_retained_geometry_without_eve_start(
    batch_host, tmp_path, monkeypatch, companions
):
    r = batch_host
    api = main_api(r, tmp_path, monkeypatch)
    if companions:
        trigger_and_wait_state(
            r,
            lambda state: state.companions == "active",
            lambda: r.runtime.set_companions(True, 1),
        )
    api._preview_layout_store.replace("Alice", Entry(Rect(1, 2, 500, 300)))
    r.host.sync_layout("Alice", Entry(Rect(1, 2, 500, 300)))
    saved = api.create_preview_layout("Off")
    record = saved["state"]["layouts"][0]
    r.host.replace_layout("Alice", Entry(Rect(3, 4, 600, 400)))
    before = api._sample_preview_geometry()
    applied = api.apply_preview_layout(record["id"], record["revision"])
    geometry = applied["geometry"]
    assert applied["persisted"] and applied["live"] == "deferred"
    assert not r.host.runtime_enabled
    assert geometry["geometry_revision"] > before["geometry_revision"]
    assert geometry["sizes"] == {"Alice": [500, 300]}
    assert geometry["layout_sources"] == [
        {
            "name": "Alice",
            "online": None,
            "geometry": {"x": 1, "y": 2, "w": 500, "h": 300},
        }
    ]
    assert geometry["client_sizes"] == {}
    assert not r.host._windows


def test_sampling_lock_orders_fresh_reads_not_caller_supplied_snapshots(tmp_path):
    from types import SimpleNamespace

    api = make_api(tmp_path)
    entered, release, second_started = Event(), Event(), Event()
    with settings.update(api._state.settings) as doc:
        doc.setdefault("preview", {}).update(seen=["Alice"], width=500, height=300)
    reader = api._preview_config
    calls = []

    def snapshot():
        value = reader.snapshot()
        calls.append(value)
        if len(calls) == 1:
            entered.set()
            assert release.wait(5)
        return value

    api._preview_config = SimpleNamespace(snapshot=snapshot)
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(api._sample_preview_geometry)
        assert entered.wait(3)
        try:
            with settings.update(api._state.settings) as doc:
                doc["preview"]["width"] = 600

            def sample():
                second_started.set()
                return api._sample_preview_geometry()

            second = pool.submit(sample)
            assert second_started.wait(3)
            assert len(calls) == 1, "later reader entered before revision allocation"
        finally:
            release.set()
        older, newer = first.result(3), second.result(3)
    assert older["sizes"] == {"Alice": [500, 300]}
    assert newer["sizes"] == {"Alice": [600, 300]}
    assert newer["geometry_revision"] == older["geometry_revision"] + 1


def test_ordinary_reset_publishes_geometry_without_replacing_keybind_table(tmp_path):
    from tests.test_api import pushes

    api = make_api(tmp_path)
    api._preview_layout_store.replace("Alice", Entry(Rect(1, 2, 500, 300)))
    api._fleet_worker.iterate_once()
    api._window.evaluated.clear()
    assert api.reset_preview_layouts()["applied"]
    api._fleet_worker.iterate_once()
    events = pushes(api._window)
    assert [handler for handler, _ in events] == ["onPreviewGeometry"]
    assert events[0][1]["layout_sources"] == []


def test_default_size_only_success_notifies(tmp_path, monkeypatch):
    api = make_api(tmp_path)
    assert api.set_preview_default_size(500, 300)["persisted"]
    assert api._preview_geometry_dirty
    api._fleet_worker.iterate_once()
    monkeypatch.setattr(
        settings, "_save_locked", lambda *a: (_ for _ in ()).throw(OSError("disk"))
    )
    assert not api.set_preview_default_size(600, 400)["persisted"]
    assert not api._preview_geometry_dirty
