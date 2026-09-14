"""Displayed Preview owners and mutations use real committed Api state."""

import copy
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace

import pytest

from tests.test_api import Api, make_state
from tests.test_preview_layoutcontroller import setup_controller
from wingman import settings
from wingman.preview import crops, savedlayouts
from wingman.preview.geometry import Rect
from wingman.preview.host import PreviewHost
from wingman.preview.layout import Entry


def owner_api(tmp_path, source):
    state = make_state(tmp_path)
    with settings.update(state.settings) as doc:
        preview = doc.setdefault("preview", {})
        preview["layouts"] = {"Source": {"x": 1, "y": 2, "w": 500, "h": 300}}
        if source == "saved":
            preview["saved_layouts"] = savedlayouts.serialize(
                (
                    savedlayouts.SavedLayout(
                        "saved",
                        "Offline",
                        (savedlayouts.SavedCharacter("Target", True, None),),
                    ),
                )
            )
        elif source == "excluded":
            preview["excluded"] = ["Target"]
        elif source == "working":
            preview["layouts"]["Target"] = {"x": 3, "y": 4, "w": 320, "h": 210}
    api = Api(state)
    if source == "retained":
        host = PreviewHost(on_layout_changed=lambda *args: None)
        host._saved = {
            "Source": Entry(Rect(1, 2, 500, 300)),
            "Target": Entry(Rect(3, 4, 320, 210)),
        }
        host._replace_layout = api._preview_layout_store.replace
        host._layout_admission = api._preview_layout_admission
        api._preview_host = host
    return api


@pytest.mark.parametrize("source", ["saved", "retained", "excluded", "working"])
@pytest.mark.parametrize("action", ["marker", "copy"])
def test_displayed_offline_owner_is_eligible_for_marker_and_copy(
    tmp_path, source, action
):
    api = owner_api(tmp_path, source)
    payload = api.get_preview_hotkey_state()
    assert "Target" not in payload["roster"]
    assert "Target" in payload["layout_state"]["owners"]
    before = copy.deepcopy(api._preview_config.snapshot())
    result = (
        api.set_preview_character_marker("Target", "cyan")
        if action == "marker"
        else api.copy_preview_layout("Target", "Source")
    )
    assert result["applied"] and result["persisted"], result
    after = settings.load()["preview"]
    changed = "label_markers" if action == "marker" else "layouts"
    assert {k: v for k, v in after.items() if k != changed} == {
        k: v for k, v in before.items() if k != changed
    }
    if action == "marker":
        assert after[changed] == {"Target": "cyan"}
    else:
        assert after[changed]["Target"] == {
            "x": 1,
            "y": 2,
            "w": 500,
            "h": 300,
            "locked": False,
        }


@pytest.mark.parametrize("source", ["marker", "crop", "working", "history"])
@pytest.mark.parametrize("accepted_commit", [False, True])
def test_current_sources_do_not_keep_obsolete_startup_owners(
    tmp_path, source, accepted_commit
):
    section = {}
    if source == "marker":
        section["label_markers"] = {"Retired": "cyan"}
    elif source == "crop":
        section["crops"] = crops.serialize(
            {
                "Retired": crops.CropDefinition(
                    crops.source_from_pixels(Rect(0, 0, 160, 90), (1280, 720)),
                    Rect(0, 0, 320, 180),
                )
            }
        )
    elif source == "working":
        section["layouts"] = {"Retired": {"x": 1, "y": 2, "w": 320, "h": 210}}
    else:
        section["seen"] = ["Retired"]
    controller, doc, path, _, _ = setup_controller(tmp_path, section=section)
    assert controller.state()["owners"] == ["Retired"]
    if accepted_commit:
        assert controller.set_excluded("Protected", True)["persisted"]
    with settings.update(doc, path) as live:
        key = {
            "marker": "label_markers",
            "crop": "crops",
            "working": "layouts",
            "history": "seen",
        }[source]
        live["preview"][key] = (
            [f"Recent {i}" for i in range(65)] if source == "history" else {}
        )
    state = controller.state()
    assert "Retired" not in state["owners"]
    assert ("Protected" in state["owners"]) == accepted_commit
    if source == "history":
        assert len(doc["preview"]["seen"]) == 64
        assert len(state["owners"]) == 64 + accepted_commit
    elif not accepted_commit:
        assert state["owners"] == []
        assert not controller.save_current("Empty")["persisted"]


@pytest.mark.parametrize("source", ["saved", "excluded"])
def test_stale_sample_cannot_resurrect_removed_protected_owner(tmp_path, source):
    saved = savedlayouts.SavedLayout(
        "saved", "Offline", (savedlayouts.SavedCharacter("Retired", True, None),)
    )
    controller, _, _, _, _ = setup_controller(
        tmp_path,
        records=(saved,) if source == "saved" else (),
        section={"excluded": ["Retired"]} if source == "excluded" else {},
    )
    reader = controller._ports.read_preview
    entered, proceed = threading.Event(), threading.Event()

    def sample():
        value = reader()
        if threading.current_thread().name.startswith("stale-owner"):
            entered.set()
            assert proceed.wait(5)
        return value

    controller._ports = replace(controller._ports, read_preview=sample)
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="stale-owner") as pool:
        pending = pool.submit(controller.state)
        try:
            assert entered.wait(5)
            receipt = (
                controller.remove(saved.id, savedlayouts.record_revision(saved))
                if source == "saved"
                else controller.set_excluded("Retired", False)
            )
            assert receipt["persisted"]
        finally:
            proceed.set()
        assert pending.result(5)["owners"] == []
    assert controller.state()["owners"] == []


def test_last_marker_removal_repairs_real_api_owner_state(tmp_path):
    state = make_state(tmp_path)
    with settings.update(state.settings) as doc:
        doc.setdefault("preview", {})["label_markers"] = {"Retired": "cyan"}
    api = Api(state)
    assert api.set_preview_character_marker("Retired", "")["persisted"]
    payload = api.get_preview_hotkey_state()
    assert payload["label_markers"] == {}
    assert payload["roster"] == payload["layout_state"]["owners"] == []


def test_marker_rechecks_current_transaction_without_sampling_readers(
    tmp_path, monkeypatch
):
    api = owner_api(tmp_path, "saved")
    original = settings.update
    reader = api._preview_config
    writing = False

    def snapshot():
        assert not writing, "no committed-reader sampling inside settings.update"
        return reader.snapshot()

    api._preview_config = SimpleNamespace(snapshot=snapshot, get=reader.get)

    @contextmanager
    def remove_before_transaction(doc, *args, **kwargs):
        nonlocal writing
        with original(doc, *args, **kwargs) as live:
            live["preview"]["saved_layouts"] = {"version": 1, "items": []}
        with original(doc, *args, **kwargs) as live:
            writing = True
            try:
                yield live
            finally:
                writing = False

    monkeypatch.setattr(settings, "update", remove_before_transaction)
    result = api.set_preview_character_marker("Target", "cyan")
    assert not result["persisted"] and "no longer available" in result["error"]
    assert settings.load()["preview"]["label_markers"] == {}


def test_retained_owner_removal_is_visible_without_retaining_old_samples(tmp_path):
    api = owner_api(tmp_path, "retained")
    assert "Target" in api._preview_layouts.state()["owners"]
    api._preview_host._saved = {}
    assert "Target" not in api._preview_layouts.state()["owners"]
    assert not api.set_preview_character_marker("Target", "cyan")["persisted"]
    assert not api.copy_preview_layout("Target", "Source")["persisted"]
