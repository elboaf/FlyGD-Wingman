"""Preview configuration must never act on a settings candidate still saving."""

import copy
import gc
import json
import weakref
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace

import pytest

from wingman import __main__ as main_mod
from wingman import settings
from wingman.preview import crops, layout
from wingman.preview.cropstore import CropStore
from wingman.preview.geometry import Rect
from wingman.preview.store import LayoutStore


def _host_config(monkeypatch, document):
    """Run the real wiring, but capture callbacks without any native actions."""
    monkeypatch.setattr(main_mod.sys, "platform", "win32")
    monkeypatch.setattr(
        "wingman.preview.host.PreviewHost", lambda **kwargs: SimpleNamespace(**kwargs)
    )
    host = main_mod.build_preview_host(SimpleNamespace(settings=document), {})
    assert host is not None
    return host


@pytest.mark.parametrize("save_fails", [False, True], ids=["commit", "rollback"])
@pytest.mark.parametrize(
    "callback,values,before,after",
    [
        ("restore_positions", {"restore_preview_positions": False}, True, False),
        ("show_labels", {"show_labels": False}, True, False),
        ("opacity", {"opacity": 100}, 255, 100),
        ("minimize_inactive_clients", {"minimize_inactive_clients": True}, False, True),
        ("hide_on_lost_focus", {"hide_on_lost_focus": True}, False, True),
        ("never_minimize", {"never_minimize": ["Alice"]}, [], ["Alice"]),
        ("locked", {"locked": ["Alice"]}, [], ["Alice"]),
        ("excluded", {"excluded": ["Alice"]}, [], ["Alice"]),
        ("snap", {"snap": False}, True, False),
        ("lock_aspect", {"lock_aspect": False}, True, False),
        ("selection_color", {"selection_color": "#abcdef"}, "#00c8dc", "#abcdef"),
        ("lock_default", {"lock_default": True}, False, True),
        ("size", {"width": 400, "height": 300}, (320, 210), (400, 300)),
    ],
)
def test_host_callbacks_keep_committed_values_during_save(
    monkeypatch, tmp_path, save_fails, callback, values, before, after
):
    path = tmp_path / "settings.json"
    document = settings.load(path)
    settings.save(document, path)
    original_file = path.read_bytes()
    read = getattr(_host_config(monkeypatch, document), callback)
    assert read() == before
    entered, release = Event(), Event()
    original_save = settings._save_locked
    candidates = []

    def save(data, path=None):
        candidates.append(copy.deepcopy(data))
        entered.set()
        assert release.wait(5)
        if save_fails:
            raise OSError("settings are read-only")
        original_save(data, path)

    def change():
        with settings.update(document, path) as live:
            assert live is document
            live["preview"].update(values)

    monkeypatch.setattr(settings, "_save_locked", save)
    with ThreadPoolExecutor(max_workers=2) as pool:
        writer = pool.submit(change)
        try:
            assert entered.wait(5)
            # Reader must finish while persistence is blocked, not wait for
            # the save lock and only then return a correctly committed value.
            assert pool.submit(read).result(timeout=1) == before
            assert path.read_bytes() == original_file
            for key, value in values.items():
                assert candidates[0]["preview"][key] == value
        finally:
            release.set()
        if save_fails:
            with pytest.raises(OSError, match="read-only"):
                writer.result(timeout=5)
        else:
            writer.result(timeout=5)

    assert read() == (before if save_fails else after)
    assert json.loads(path.read_text()) == document


@pytest.mark.parametrize("save_fails", [False, True], ids=["commit", "rollback"])
def test_registration_waits_for_inflight_writer(monkeypatch, tmp_path, save_fails):
    """Registering from a tentative document would make rollback the baseline."""
    path = tmp_path / "settings.json"
    document = settings.load(path)
    entered, release, registering = Event(), Event(), Event()
    original_save, original_lock = settings._save_locked, settings._SAVE_LOCK

    def save(data, path=None):
        entered.set()
        assert release.wait(5)
        if save_fails:
            raise OSError("settings are read-only")
        original_save(data, path)

    def change():
        with settings.update(document, path) as live:
            live["preview"]["minimize_inactive_clients"] = True

    class RegistrationLock:
        def __enter__(self):
            registering.set()
            return original_lock.__enter__()

        def __exit__(self, *args):
            return original_lock.__exit__(*args)

    monkeypatch.setattr(settings, "_save_locked", save)
    with ThreadPoolExecutor(max_workers=2) as pool:
        writer = pool.submit(change)
        try:
            assert entered.wait(5)
            # Observe the attempted acquisition, not an arbitrary sleep that
            # might just mean the registration worker has not run yet.
            monkeypatch.setattr(settings, "_SAVE_LOCK", RegistrationLock())
            registration = pool.submit(settings.committed_preview, document)
            assert registering.wait(5)
            assert not registration.done()
        finally:
            release.set()
        if save_fails:
            with pytest.raises(OSError, match="read-only"):
                writer.result(timeout=5)
        else:
            writer.result(timeout=5)
        reader = registration.result(timeout=5)
    assert reader.get("minimize_inactive_clients") is (not save_fails)


def test_preparation_failure_rolls_back_before_persistence(monkeypatch, tmp_path):
    path = tmp_path / "settings.json"
    document = settings.load(path)
    settings.save(document, path)
    original_file, before = path.read_bytes(), copy.deepcopy(document)
    reader = settings.committed_preview(document)
    attempts = []

    def cannot_prepare(data):
        attempts.append(copy.deepcopy(data["preview"]))
        assert settings._SAVE_LOCK.locked()
        assert data["preview"]["width"] == 120  # normalized BEFORE preparation
        assert reader.get("minimize_inactive_clients") is False
        raise MemoryError("cannot detach preview snapshot")

    def must_not_save(*args):
        pytest.fail("snapshot preparation must complete before the durable write")

    with monkeypatch.context() as patch:
        patch.setattr(settings, "_prepare_preview_snapshot", cannot_prepare)
        patch.setattr(settings, "_save_locked", must_not_save)
        with (
            pytest.raises(MemoryError, match="cannot detach"),
            settings.update(document, path) as live,
        ):
            live["preview"]["minimize_inactive_clients"] = True
            live["preview"]["width"] = 1

    assert len(attempts) == 1
    assert document == before
    assert path.read_bytes() == original_file
    assert reader.get("minimize_inactive_clients") is False
    with settings.update(document, path) as live:
        live["preview"]["minimize_inactive_clients"] = True
    assert reader.get("minimize_inactive_clients") is True


def test_initial_preparation_is_locked_and_failure_does_not_register(monkeypatch):
    document = settings.load()
    original = copy.deepcopy(document)

    def fail(data):
        assert settings._SAVE_LOCK.locked()
        assert data is document
        raise MemoryError("cannot initialize preview snapshot")

    with monkeypatch.context() as patch:
        patch.setattr(settings, "_prepare_preview_snapshot", fail)
        with pytest.raises(MemoryError, match="cannot initialize"):
            settings.committed_preview(document)
    assert id(document) not in settings._COMMITTED_PREVIEWS
    assert document == original
    reader = settings.committed_preview(document)
    assert reader.snapshot() == original["preview"]


def test_publication_does_not_copy_or_validate_after_durable_save(
    monkeypatch, tmp_path
):
    """Post-save preparation could fail and roll RAM back behind committed disk."""
    path = tmp_path / "settings.json"
    document = settings.load(path)
    reader = settings.committed_preview(document)
    original_save = settings._save_locked

    def forbidden(*args, **kwargs):
        pytest.fail("post-save publication must only swap a prepared reference")

    def save(data, path=None):
        original_save(data, path)
        patch.setattr(settings, "_prepare_preview_snapshot", forbidden)
        patch.setattr(settings, "_prepare_preview_publication", forbidden)
        patch.setattr(settings.alert_custom, "prepare_alert_snapshot", forbidden)
        patch.setattr(settings, "validated_preview", forbidden)
        patch.setattr(settings, "validated_alerts", forbidden)
        patch.setattr(settings, "validated_custom_rules", forbidden)
        patch.setattr(settings.copy, "deepcopy", forbidden)
        patch.setattr(settings, "_normalize", forbidden)

    with monkeypatch.context() as patch:
        patch.setattr(settings, "_save_locked", save)
        with settings.update(document, path) as live:
            live["preview"]["minimize_inactive_clients"] = True
            live["preview"]["alerts"]["custom_rules"] = [
                {"id": "r1", "search": "fleet invite", "enabled": True}
            ]
    assert reader.get("minimize_inactive_clients") is True
    assert reader.alerts_snapshot().custom_rules[0].rule.search == "fleet invite"
    assert json.loads(path.read_text()) == document


def test_readers_are_document_scoped_and_share_commits(monkeypatch, tmp_path):
    first, second = settings.load(), settings.load()
    second["preview"]["opacity"] = 90
    one = _host_config(monkeypatch, first)
    another = _host_config(monkeypatch, first)
    two = _host_config(monkeypatch, second)
    with settings.update(first, tmp_path / "first.json") as live:
        live["preview"]["opacity"] = 100
    assert one.opacity() == another.opacity() == 100
    assert two.opacity() == 90
    with settings.update(second, tmp_path / "second.json") as live:
        live["preview"]["opacity"] = 200
    assert two.opacity() == 200
    assert one.opacity() == another.opacity() == 100


def test_host_callback_keeps_reader_and_document_alive_without_registry_leak(
    monkeypatch,
):
    class Document(dict):
        pass  # A weak-referenceable dict only to observe document lifetime.

    document = Document(settings.load())
    key, document_ref = id(document), weakref.ref(document)
    reader = settings.committed_preview(document)
    reader_ref = weakref.ref(reader)
    callback = _host_config(monkeypatch, document).minimize_inactive_clients
    alert_callback = reader.alerts_snapshot
    del document, reader
    gc.collect()
    assert document_ref() is not None  # prevents reuse of the registry's id key
    assert reader_ref() is not None
    assert callback() is False
    del callback
    gc.collect()
    assert reader_ref() is not None
    assert alert_callback().custom_rules == ()
    del alert_callback
    gc.collect()
    assert reader_ref() is None
    assert document_ref() is None
    assert key not in settings._COMMITTED_PREVIEWS


def test_nested_values_cannot_mutate_committed_storage(monkeypatch, tmp_path):
    document = settings.load()
    document["preview"]["never_minimize"] = ["Alice"]
    document["preview"]["hotkeys"]["groups"] = [
        {"id": "g1", "name": "Group", "cycle": "Ctrl+F1"}
    ]
    reader = settings.committed_preview(document)
    host = _host_config(monkeypatch, document)
    for committed in (False, True):
        if committed:
            with settings.update(document, tmp_path / "settings.json"):
                pass
        reader.get("hotkeys")["groups"][0]["name"] = "escaped get"
        reader.snapshot()["hotkeys"]["groups"][0]["name"] = "escaped snapshot"
        host.never_minimize().append("escaped callback")
        document["preview"]["hotkeys"]["groups"][0]["name"] = "tentative"
        assert reader.get("hotkeys")["groups"][0]["name"] == "Group"
        assert host.never_minimize() == ["Alice"]
        document["preview"]["hotkeys"]["groups"][0]["name"] = "Group"


def test_unrelated_update_publishes_normalized_preview_without_schema_change(tmp_path):
    document = settings.load()
    # A pre-migration section: even an unrelated save normalizes it.
    document["preview"].update(opacity=235, defaults_version=1)
    reader = settings.committed_preview(document)
    with settings.update(document, tmp_path / "settings.json") as live:
        assert live is document
        live["category"] = "22"
    assert reader.get("opacity") == 255
    assert reader.get("defaults_version") == 2
    saved = json.loads((tmp_path / "settings.json").read_text())
    assert saved["category"] == "22"
    assert saved == document
    assert saved["preview"] == reader.snapshot()
    assert saved.keys() == settings.DEFAULTS.keys()


def test_direct_save_keeps_its_existing_persistence_only_semantics(tmp_path):
    document = settings.load()
    reader = settings.committed_preview(document)
    alerts = reader.alerts_snapshot()
    document["preview"]["opacity"] = 100
    document["preview"]["alerts"]["custom_rules"] = [
        {"id": "r1", "search": "fleet invite", "enabled": True}
    ]
    settings.save(document, tmp_path / "settings.json")
    saved = settings.load(tmp_path / "settings.json")["preview"]
    assert saved["opacity"] == 100
    assert saved["alerts"]["custom_rules"][0]["id"] == "r1"
    assert reader.get("opacity") == 255
    assert reader.alerts_snapshot() is alerts


def test_layout_and_crop_writers_advance_the_registered_reader(tmp_path):
    document = settings.load()
    path = tmp_path / "settings.json"
    document["preview"]["alerts"]["custom_rules"] = [
        {"id": "r1", "search": "fleet invite", "enabled": True}
    ]
    reader = settings.committed_preview(document)
    alerts = reader.alerts_snapshot()

    def update():
        return settings.update(document, path)

    layouts = LayoutStore(update_settings=update)
    store = CropStore(
        update_settings=update,
        initial={},
        executor_factory=lambda: ThreadPoolExecutor(max_workers=1),
    )
    try:
        entry = layout.Entry(Rect(1, 2, 320, 210), False)
        assert layouts.replace("Alice", entry)
        assert reader.get("layouts")["Alice"]["x"] == 1
        assert reader.alerts_snapshot() == alerts
        assert reader.alerts_snapshot() is not alerts
        alerts = reader.alerts_snapshot()
        definition = crops.CropDefinition(
            crops.source_from_pixels(Rect(0, 0, 320, 180), (1280, 720)),
            Rect(40, 50, 320, 180),
        )
        token = store.begin("Alice", epoch=0, session=None)
        assert store.put(token, definition).result(timeout=5).persisted
        assert reader.get("crops")["Alice"]["window"]["x"] == 40
        assert reader.alerts_snapshot() == alerts
        assert reader.alerts_snapshot() is not alerts
        alerts = reader.alerts_snapshot()
        token = store.begin("Alice", epoch=0, session=None)
        assert store.set_enabled(token, False).result(timeout=5).persisted
        assert reader.get("crops")["Alice"]["enabled"] is False
        assert reader.alerts_snapshot() == alerts
        assert reader.alerts_snapshot() is not alerts
        assert reader.get("layouts")["Alice"]["x"] == 1
        assert json.loads(path.read_text())["preview"] == reader.snapshot()
    finally:
        assert store.close().result(timeout=5)


@pytest.mark.parametrize("save_fails", [False, True], ids=["commit", "rollback"])
def test_alert_readers_share_one_composite_while_save_is_blocked(
    monkeypatch, tmp_path, save_fails
):
    path = tmp_path / "settings.json"
    document = settings.load(path)
    document["preview"]["alerts"]["custom_rules"] = [
        {"id": "r1", "search": "fleet invite", "enabled": True}
    ]
    with settings.update(document, path):
        pass
    original_file, original_doc = path.read_bytes(), copy.deepcopy(document)
    reader = settings.committed_preview(document)
    sibling = settings.committed_preview(document)
    other = settings.committed_preview(settings.load())
    old_other = other.alerts_snapshot()
    old_composite, old_alerts = reader._snapshot, reader.alerts_snapshot()
    entered, release = Event(), Event()
    original_save = settings._save_locked

    def save(data, path=None):
        entered.set()
        assert release.wait(5)
        if save_fails:
            raise OSError("read-only")
        original_save(data, path)

    def change():
        with settings.update(document, path):
            document["preview"]["enabled"] = True
            alerts = document["preview"]["alerts"]
            alerts.update(
                enabled=True, pve_filter=False, persist_until_selected=False, volume=23
            )
            alerts["events"]["combat"].update(
                color="#abcdef", cooldown_s=7, sound="obey"
            )
            alerts["custom_rules"][0]["search"] = "new fleet invite"

    monkeypatch.setattr(settings, "_save_locked", save)
    with ThreadPoolExecutor(max_workers=2) as pool:
        writer = pool.submit(change)
        try:
            assert entered.wait(5)
            for current in (reader, sibling):
                assert (
                    pool.submit(current.alerts_snapshot).result(timeout=1) is old_alerts
                )
                assert current._snapshot is old_composite
                assert (
                    pool.submit(current.snapshot).result(timeout=1)
                    == original_doc["preview"]
                )
                assert pool.submit(current.get, "enabled").result(timeout=1) is False
            assert path.read_bytes() == original_file
        finally:
            release.set()
        if save_fails:
            with pytest.raises(OSError, match="read-only"):
                writer.result(timeout=5)
        else:
            writer.result(timeout=5)

    assert reader is sibling
    assert other.alerts_snapshot() is old_other
    assert json.loads(path.read_text()) == document
    if save_fails:
        assert document == original_doc
        assert path.read_bytes() == original_file
        assert reader._snapshot is old_composite
        assert reader.alerts_snapshot() is old_alerts
    else:
        snapshot = reader.alerts_snapshot()
        assert snapshot is sibling.alerts_snapshot()
        assert reader._snapshot is not old_composite
        assert reader.snapshot() == document["preview"]
        assert snapshot.preview_enabled is snapshot.alerts_enabled is True
        assert snapshot.pve_filter is snapshot.persist_until_selected is False
        assert snapshot.volume == 23
        combat = next(row for row in snapshot.builtins if row.event == "combat")
        assert (combat.color, combat.cooldown_s, combat.sound) == ("#abcdef", 7, "obey")
        assert snapshot.custom_rules[0].rule.search == "new fleet invite"
        assert snapshot.custom_rules[0].generation == old_alerts.rules_revision + 1
        assert snapshot.activation_epoch == old_alerts.activation_epoch + 1
        assert len(snapshot.executable) == 1


def test_alert_projection_failure_preserves_document_disk_and_tokens(
    monkeypatch, tmp_path
):
    path = tmp_path / "settings.json"
    document = settings.load(path)
    settings.save(document, path)
    reader = settings.committed_preview(document)
    before, original_file = copy.deepcopy(document), path.read_bytes()
    old_composite, old_alerts = reader._snapshot, reader.alerts_snapshot()

    def fail(preview, previous=None):
        assert settings._SAVE_LOCK.locked()
        assert preview["alerts"]["custom_rules"][0]["color"] == "#ff8c42"
        assert previous is old_alerts
        raise MemoryError("cannot prepare alerts")

    def forbidden(*args, **kwargs):
        pytest.fail("projection must finish before saving")

    with monkeypatch.context() as patch:
        patch.setattr(settings.alert_custom, "prepare_alert_snapshot", fail)
        patch.setattr(settings, "_save_locked", forbidden)
        with (
            pytest.raises(MemoryError, match="cannot prepare"),
            settings.update(document, path),
        ):
            document["preview"]["alerts"]["custom_rules"] = [
                {"id": "r1", "search": "fleet invite", "color": "bad"}
            ]
    assert document == before
    assert path.read_bytes() == original_file
    assert reader._snapshot is old_composite
    assert reader.alerts_snapshot() is old_alerts
    with settings.update(document, path):
        document["preview"]["alerts"]["custom_rules"] = [{"id": "r1"}]
    assert reader.alerts_snapshot().rules_revision == old_alerts.rules_revision + 1


def test_failed_initial_alert_projection_does_not_register(monkeypatch):
    document = settings.load()
    before = copy.deepcopy(document)

    def fail(preview, previous=None):
        assert settings._SAVE_LOCK.locked()
        assert previous is None
        raise MemoryError("cannot initialize alerts")

    with monkeypatch.context() as patch:
        patch.setattr(settings.alert_custom, "prepare_alert_snapshot", fail)
        with pytest.raises(MemoryError, match="cannot initialize"):
            settings.committed_preview(document)
    assert id(document) not in settings._COMMITTED_PREVIEWS
    assert document == before
    reader = settings.committed_preview(document)
    assert reader.alerts_snapshot().rules_revision == 1
