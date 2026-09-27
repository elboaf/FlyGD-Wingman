"""Production controller payloads and production page ordering, not rendered UI."""

import gc
import json
import os
import subprocess
import threading
import weakref
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from tests.html_tree import PageTree, TextPageTree
from tests.test_api import Api, FakeWindow, make_state, pushes
from wingman import paths, settings
from wingman.preview.geometry import Rect
from wingman.preview.layout import Entry
from wingman.preview.savedlayouts import PrimaryLayoutLiveResult


@dataclass(frozen=True)
class SavedLayoutReceiptEvidence:
    receipt_json: str
    durable_json: str
    keys: tuple[str, ...]
    fsync_calls: int
    created_id: str
    created_revision: str
    updated_revision: str
    renamed_revision: str
    pending_action: str
    pending_was_true: bool


_SAVED_LAYOUT_RECEIPT_LOCK = threading.Lock()
_SAVED_LAYOUT_RECEIPT: SavedLayoutReceiptEvidence | None = None
_RECEIPT_MUTATION_SENTINELS = {
    "durable": "stage-b mutation receipt-durable-readback",
    "fsync": "stage-b mutation receipt-atomic-writer-fsync",
    "writer": "stage-b mutation receipt-writer-restoration",
    "environment": "stage-b mutation receipt-environment-restoration",
    "reader": "stage-b mutation receipt-reader-release",
    "pending": "stage-b mutation receipt-pending-first-apply",
}


def _saved_layout_receipt_once(
    tmp_path_factory: pytest.TempPathFactory,
) -> SavedLayoutReceiptEvidence:
    global _SAVED_LAYOUT_RECEIPT
    with _SAVED_LAYOUT_RECEIPT_LOCK:
        if _SAVED_LAYOUT_RECEIPT is not None:
            return _SAVED_LAYOUT_RECEIPT
        _SAVED_LAYOUT_RECEIPT = _build_saved_layout_receipt(tmp_path_factory)
        return _SAVED_LAYOUT_RECEIPT


def _construct_saved_layout_receipt(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[
    SavedLayoutReceiptEvidence,
    tuple[weakref.ReferenceType[object], ...],
    frozenset[int],
    object | None,
]:
    state_root = tmp_path_factory.mktemp("saved-layout-receipt")
    had_localappdata = "LOCALAPPDATA" in os.environ
    original_localappdata = os.environ.get("LOCALAPPDATA")
    original_use_legacy = paths._use_legacy
    original_save_locked = settings._save_locked
    original_fsync = os.fsync
    baseline_readers = {
        key: weakref.ref(value) for key, value in settings._COMMITTED_PREVIEWS.items()
    }
    fsync_calls = 0
    delegated_fsync_calls = 0
    api = None
    empty_api = None
    owned_refs: list[weakref.ReferenceType[object]] = []
    reader_keys: set[int] = set()
    evidence = None

    def counting_fsync(fd: int) -> None:
        nonlocal fsync_calls, delegated_fsync_calls
        fsync_calls += 1
        original_fsync(fd)
        delegated_fsync_calls += 1

    try:
        with pytest.MonkeyPatch.context() as patch:
            patch.setenv("LOCALAPPDATA", str(state_root))
            patch.setattr(paths, "_use_legacy", False)
            patch.setattr(os, "fsync", counting_fsync)
            try:
                state = make_state(state_root)
                with settings.update(state.settings) as doc:
                    doc.setdefault("preview", {}).update(seen=["Alice", "Bob"])
                api = Api(state)
                api._window = FakeWindow()
                reader_keys.add(id(state.settings))
                owned_refs.extend(
                    weakref.ref(value)
                    for value in (
                        state,
                        api,
                        api._preview_config,
                        api._preview_layouts,
                    )
                )

                api._preview_layout_store.replace("Alice", Entry(Rect(1, 2, 500, 300)))
                initial = api.get_preview_hotkey_state()
                hidden = api.set_preview_excluded("Alice", True)
                both = api.set_preview_excluded("Bob", True)
                created = api.create_preview_layout("Hidden")
                record = created["state"]["layouts"][0]
                api.set_preview_excluded("Bob", False)
                visible = api.set_preview_excluded("Alice", False)
                # A blocked native boundary lets the real shared presentation owner
                # sample pending state before the native completion is published.
                pending_states = []
                original_apply = api._apply_preview_layout

                def apply_pending(*args):
                    api._fleet_worker.iterate_once()
                    pending_states.extend(
                        payload
                        for handler, payload in pushes(api._window)
                        if handler == "onPreviewLayouts"
                        and payload["operation"]["pending"]
                    )
                    return original_apply(*args)

                api._preview_layouts._ports = replace(
                    api._preview_layouts._ports, apply=apply_pending
                )
                bulk = api.apply_preview_layout(record["id"], record["revision"])
                pending_receipt = pending_states[-1]
                lease = api._preview_layout_admission.try_begin(exclusive=True)
                refused = api.set_preview_excluded("Alice", False)
                api._preview_layout_admission.finish(lease)
                retry = api.set_preview_excluded("Alice", False)
                size_ack = api.set_preview_size("Alice", 600, 400)
                geometry_apply = api.apply_preview_layout(
                    record["id"], record["revision"]
                )
                api.set_preview_size("Alice", 700, 450)
                newer_geometry = api._sample_preview_geometry()
                api._preview_layout_store.replace("Bob", Entry(Rect(5, 6, 640, 480)))
                api.copy_preview_layout("Alice", "Bob")
                newer_copy = api._sample_preview_geometry()
                api.reset_preview_layouts()
                newer_reset = api._sample_preview_geometry()
                duplicate = api.create_preview_layout("HIDDEN")
                stale = api.apply_preview_layout(record["id"], "stale")
                updated = api.update_preview_layout(record["id"], record["revision"])
                updated_record = updated["state"]["layouts"][0]
                renamed = api.rename_preview_layout(
                    updated_record["id"], updated_record["revision"], "__proto__"
                )
                renamed_record = renamed["state"]["layouts"][0]
                removed = api.remove_preview_layout(
                    renamed_record["id"], renamed_record["revision"]
                )
                with pytest.MonkeyPatch.context() as failed_save_patch:

                    def fail_save(*args, **kwargs):
                        raise OSError("Disk unavailable")

                    failed_save_patch.setattr(settings, "_save_locked", fail_save)
                    failed_save = api.create_preview_layout("Refused")
                if settings._save_locked is not original_save_locked:
                    raise AssertionError(_RECEIPT_MUTATION_SENTINELS["writer"])
                api._preview_layouts._ports = replace(
                    api._preview_layouts._ports,
                    refresh_visibility=lambda lease: api._settled_preview_layout(
                        PrimaryLayoutLiveResult(
                            "incomplete",
                            "Saved, but one preview could not be shown.",
                        )
                    ),
                )
                incomplete = api.set_preview_excluded("Alice", False)
                empty_state = make_state(state_root)
                empty_api = Api(empty_state)
                reader_keys.add(id(empty_state.settings))
                owned_refs.extend(
                    weakref.ref(value)
                    for value in (
                        empty_state,
                        empty_api,
                        empty_api._preview_config,
                        empty_api._preview_layouts,
                    )
                )
                unavailable = empty_api.get_preview_hotkey_state()

                receipt = {
                    "initial": initial,
                    "hidden": hidden,
                    "both": both,
                    "visible": visible,
                    "bulk": bulk,
                    "pending": pending_receipt,
                    "refused": refused,
                    "retry": retry,
                    "created": created,
                    "duplicate": duplicate,
                    "stale": stale,
                    "updated": updated,
                    "renamed": renamed,
                    "removed": removed,
                    "size_ack": size_ack,
                    "geometry_apply": geometry_apply,
                    "newer_geometry": newer_geometry,
                    "newer_copy": newer_copy,
                    "newer_reset": newer_reset,
                    "failed_save": failed_save,
                    "incomplete": incomplete,
                    "unavailable": unavailable,
                }
                receipt_json = json.dumps(
                    receipt,
                    ensure_ascii=False,
                    allow_nan=False,
                    separators=(",", ":"),
                )
                # fmt: off
                durable_json = settings.paths.settings_file().read_text(encoding="utf-8")
                # fmt: on
                durable = json.loads(durable_json)
                committed = api._preview_config.snapshot()
                durable_preview = (
                    durable.get("preview") if isinstance(durable, dict) else None
                )
                assert (
                    isinstance(durable_preview, dict) and committed == durable_preview
                ), _RECEIPT_MUTATION_SENTINELS["durable"]
                pending_operation = pending_receipt.get("operation", {})
                assert pending_operation.get("action") == "apply", (
                    _RECEIPT_MUTATION_SENTINELS["pending"]
                )
                assert pending_operation.get("pending") is True, (
                    _RECEIPT_MUTATION_SENTINELS["pending"]
                )
                assert geometry_apply["persisted"] is True
                assert fsync_calls == 19, _RECEIPT_MUTATION_SENTINELS["fsync"]
                assert delegated_fsync_calls == 19, _RECEIPT_MUTATION_SENTINELS["fsync"]
                evidence = SavedLayoutReceiptEvidence(
                    receipt_json=receipt_json,
                    durable_json=durable_json,
                    keys=tuple(receipt),
                    fsync_calls=fsync_calls,
                    created_id=record["id"],
                    created_revision=record["revision"],
                    updated_revision=updated_record["revision"],
                    renamed_revision=renamed_record["revision"],
                    pending_action=pending_operation["action"],
                    pending_was_true=pending_operation["pending"],
                )
                retained_stage_b_owner = None
            finally:
                if api is not None:
                    api.shutdown_previews()
                    vars(api).clear()
                if empty_api is not None:
                    empty_api.shutdown_previews()
                    vars(empty_api).clear()
                if "apply_pending" in locals():
                    del apply_pending
                if "original_apply" in locals():
                    del original_apply
                if "committed" in locals():
                    del committed
                if "doc" in locals():
                    del doc
                if "state" in locals():
                    del state
                if "empty_state" in locals():
                    del empty_state
                api = None
                empty_api = None
                gc.collect()
    finally:
        paths._use_legacy = original_use_legacy

    assert ("LOCALAPPDATA" in os.environ) is had_localappdata
    assert os.environ.get("LOCALAPPDATA") == original_localappdata, (
        _RECEIPT_MUTATION_SENTINELS["environment"]
    )
    assert paths._use_legacy is original_use_legacy
    assert settings._save_locked is original_save_locked, _RECEIPT_MUTATION_SENTINELS[
        "writer"
    ]
    assert os.fsync is original_fsync
    assert not {
        key: value
        for key, reference in baseline_readers.items()
        if (value := reference()) is not None
        and settings._COMMITTED_PREVIEWS.get(key) is not value
    }
    assert evidence is not None
    return (
        evidence,
        tuple(owned_refs),
        frozenset(reader_keys),
        retained_stage_b_owner,
    )


def _build_saved_layout_receipt(
    tmp_path_factory: pytest.TempPathFactory,
) -> SavedLayoutReceiptEvidence:
    evidence, owned_refs, reader_keys, retained_stage_b_owner = (
        _construct_saved_layout_receipt(tmp_path_factory)
    )
    gc.collect()
    retained_stage_b_readers = {
        key: settings._COMMITTED_PREVIEWS.get(key)
        for key in reader_keys
        if settings._COMMITTED_PREVIEWS.get(key) is not None
    }
    assert not retained_stage_b_readers, _RECEIPT_MUTATION_SENTINELS["reader"]
    assert retained_stage_b_owner is None, _RECEIPT_MUTATION_SENTINELS["reader"]
    assert all(reference() is None for reference in owned_refs), (
        _RECEIPT_MUTATION_SENTINELS["reader"]
    )
    return evidence


@pytest.mark.parametrize(
    "scenario",
    [
        "reversed",
        "bulk",
        "keybind",
        "retry",
        "draft",
        "early",
        "named",
        "staging",
        "staging-roundtrip",
        "copy-dialog-navigation",
        "copy-dialog-subpage",
        "copy-dialog-staging",
        "copy-dialog-configure",
        "copy-dialog-attempt",
        "copy-dialog-capture",
        "copy-admitted-subpage",
        "copy-detail-fit",
        "copy-detail-truncated",
        "copy-detail-clipped",
        "copy-detail-legacy",
        "copy-detail-unmeasurable",
        "copy-detail-resize",
        "copy-detail-typography",
        "copy-detail-default",
        "dialog-focus-history",
        "dialog-owned-cancel",
        "geometry-detail-focus",
        "geometry-detail-dialog",
        "geometry-ack",
        "geometry-getter",
        "geometry-keybind",
        "geometry-staging",
        "geometry-dialog-navigation",
        "geometry-dialog-capture",
        "controls-empty",
        "controls-select",
        "controls-save",
        "controls-apply",
        "controls-update",
        "controls-rename",
        "controls-remove",
        "controls-cancel",
        "controls-errors",
        "controls-pending",
        "controls-staging",
        "controls-capture",
        "controls-busy",
        "row-feedback",
        "row-rejected",
        "controls-unhydrated",
        "controls-unavailable",
        "controls-failed-save",
        "controls-incomplete",
        "controls-reopen",
        "controls-staged-receipt",
    ],
)
def test_saved_layout_page_ordering(tmp_path, scenario, monkeypatch):
    state = make_state(tmp_path)
    with settings.update(state.settings) as doc:
        doc.setdefault("preview", {}).update(seen=["Alice", "Bob"])
    api = Api(state)
    api._window = FakeWindow()
    from wingman.preview.geometry import Rect
    from wingman.preview.layout import Entry

    api._preview_layout_store.replace("Alice", Entry(Rect(1, 2, 500, 300)))
    initial = api.get_preview_hotkey_state()
    hidden = api.set_preview_excluded("Alice", True)
    both = api.set_preview_excluded("Bob", True)
    created = api.create_preview_layout("Hidden")
    record = created["state"]["layouts"][0]
    api.set_preview_excluded("Bob", False)
    visible = api.set_preview_excluded("Alice", False)
    # A blocked native boundary lets the real shared presentation owner sample
    # pending state deterministically; coalescing need not replay every transition.
    pending_states = []
    original = api._apply_preview_layout
    from dataclasses import replace

    def apply_pending(*args):
        api._fleet_worker.iterate_once()
        pending_states.extend(
            payload
            for handler, payload in pushes(api._window)
            if handler == "onPreviewLayouts" and payload["operation"]["pending"]
        )
        return original(*args)

    api._preview_layouts._ports = replace(
        api._preview_layouts._ports, apply=apply_pending
    )
    bulk = api.apply_preview_layout(record["id"], record["revision"])
    pending = pending_states[-1]
    lease = api._preview_layout_admission.try_begin(exclusive=True)
    refused = api.set_preview_excluded("Alice", False)
    api._preview_layout_admission.finish(lease)
    retry = api.set_preview_excluded("Alice", False)
    size_ack = api.set_preview_size("Alice", 600, 400)
    geometry_apply = api.apply_preview_layout(record["id"], record["revision"])
    api.set_preview_size("Alice", 700, 450)
    newer_geometry = api._sample_preview_geometry()
    api._preview_layout_store.replace("Bob", Entry(Rect(5, 6, 640, 480)))
    api.copy_preview_layout("Alice", "Bob")
    newer_copy = api._sample_preview_geometry()
    api.reset_preview_layouts()
    newer_reset = api._sample_preview_geometry()
    duplicate = api.create_preview_layout("HIDDEN")
    stale = api.apply_preview_layout(record["id"], "stale")
    updated = api.update_preview_layout(record["id"], record["revision"])
    updated_record = updated["state"]["layouts"][0]
    renamed = api.rename_preview_layout(
        updated_record["id"], updated_record["revision"], "__proto__"
    )
    renamed_record = renamed["state"]["layouts"][0]
    removed = api.remove_preview_layout(
        renamed_record["id"], renamed_record["revision"]
    )
    with monkeypatch.context() as patch:

        def fail_save(*args, **kwargs):
            raise OSError("Disk unavailable")

        patch.setattr(settings, "_save_locked", fail_save)
        failed_save = api.create_preview_layout("Refused")
    from wingman.preview.savedlayouts import PrimaryLayoutLiveResult

    api._preview_layouts._ports = replace(
        api._preview_layouts._ports,
        refresh_visibility=lambda lease: api._settled_preview_layout(
            PrimaryLayoutLiveResult(
                "incomplete", "Saved, but one preview could not be shown."
            )
        ),
    )
    incomplete = api.set_preview_excluded("Alice", False)
    empty_api = Api(make_state(tmp_path))
    unavailable = empty_api.get_preview_hotkey_state()
    web = Path(__file__).parents[1] / "wingman/web"
    data = tmp_path / "page.json"
    tree = TextPageTree()
    tree.feed((web / "index.html").read_text(encoding="utf-8"))
    data.write_text(
        json.dumps(
            {
                "scenario": scenario,
                "page": tree.root,
                "initial": initial,
                "hidden": hidden,
                "both": both,
                "visible": visible,
                "bulk": bulk,
                "pending": pending,
                "refused": refused,
                "retry": retry,
                "created": created,
                "duplicate": duplicate,
                "stale": stale,
                "updated": updated,
                "renamed": renamed,
                "removed": removed,
                "size_ack": size_ack,
                "geometry_apply": geometry_apply,
                "newer_geometry": newer_geometry,
                "newer_copy": newer_copy,
                "newer_reset": newer_reset,
                "failed_save": failed_save,
                "incomplete": incomplete,
                "unavailable": unavailable,
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            "node",
            str(Path(__file__).parent / "fixtures/preview_savedlayouts.cjs"),
            str(data),
            str(web),
        ],
        capture_output=True,
        text=True,
        timeout=25,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS " + scenario in result.stdout


@pytest.mark.parametrize("source", ["saved", "retained", "excluded"])
def test_displayed_owner_controls_use_real_api_receipts(tmp_path, source):
    from tests.test_preview_owner_eligibility import owner_api

    api = owner_api(tmp_path, source)
    initial = api.get_preview_hotkey_state()
    marker = api.set_preview_character_marker("Target", "cyan")
    visible = api.set_preview_excluded("Target", False)
    copied = api.copy_preview_layout("Target", "Source")
    web = Path(__file__).parents[1] / "wingman/web"
    tree = TextPageTree()
    tree.feed((web / "index.html").read_text(encoding="utf-8"))
    data = tmp_path / "owners.json"
    data.write_text(
        json.dumps(
            {
                "page": tree.root,
                "scenario": "owner-controls",
                "initial": initial,
                "marker": marker,
                "visible": visible,
                "copied": copied,
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            "node",
            str(Path(__file__).parent / "fixtures/preview_savedlayouts.cjs"),
            str(data),
            str(web),
        ],
        capture_output=True,
        text=True,
        timeout=25,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS owner-controls" in result.stdout


@pytest.mark.parametrize("scenario", ["reversed", "local", "boundary", "dev"])
def test_capture_session_page_ordering(tmp_path, scenario):
    state = make_state(tmp_path)
    with settings.update(state.settings) as doc:
        doc.setdefault("preview", {}).update(seen=["Alice", "Bob"])
    api = Api(state)
    web = Path(__file__).parents[1] / "wingman/web"
    tree = PageTree()
    tree.feed((web / "index.html").read_text(encoding="utf-8"))
    data = tmp_path / "capture.json"
    data.write_text(
        json.dumps(
            {
                "scenario": scenario,
                "page": tree.root,
                "initial": api.get_preview_hotkey_state(),
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            "node",
            str(
                Path(__file__).parent
                / "fixtures"
                / (
                    "preview_dev_capture.cjs"
                    if scenario == "dev"
                    else "preview_capture_sessions.cjs"
                )
            ),
            str(data),
            str(web),
        ],
        capture_output=True,
        text=True,
        timeout=25,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS " + scenario in result.stdout
