"""Production controller payloads and production page ordering, not rendered UI."""

import gc
import json
import os
import shutil
import threading
import weakref
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from tests.html_tree import PageTree, TextPageTree
from tests.node_scenario_worker import NodeScenarioWorker
from tests.test_api import Api, FakeWindow, make_state, pushes
from wingman import paths, settings
from wingman.preview.geometry import Rect
from wingman.preview.layout import Entry
from wingman.preview.savedlayouts import PrimaryLayoutLiveResult

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "wingman/web"
ZERO_CLEANUP = {
    "host_timer_handles": 0,
    "host_callbacks": 0,
    "active_rejection_listeners": 0,
    "pending_rejection_records": 0,
    "retained_realms": 0,
}
SAVED_DIRECT_FSYNC_BY_CASE = {
    ("owner", "saved"): 3,
    ("owner", "retained"): 3,
    ("owner", "excluded"): 4,
    ("capture", "reversed"): 1,
    ("capture", "local"): 1,
    ("capture", "boundary"): 1,
    ("capture", "dev"): 1,
}
SAVED_DIRECT_FSYNC_TOTAL = sum(SAVED_DIRECT_FSYNC_BY_CASE.values())
SAVED_DEV_LINES = (
    "DEV api.get_preview_hotkey_state()",
    "DEV api.get_preview_hotkey_state()",
    "DEV api.list_rows()",
    "DEV api.get_settings()",
    "DEV api.theme_state()",
    "DEV api.set_bind_capture(true)",
    "DEV api.set_bind_capture(false)",
    "DEV api.get_preview_hotkey_state()",
    "DEV api.set_bind_capture(true)",
    "DEV api.set_bind_capture(false)",
    "DEV api.set_bind_capture(true)",
    "DEV api.set_bind_capture(true)",
    "DEV api.set_bind_capture(false)",
    "DEV api.set_bind_capture(false)",
    "DEV api.set_bind_capture(false)",
    "DEV api.get_preview_hotkey_state()",
    "DEV api.set_bind_capture(false)",
    "DEV api.set_bind_capture(true)",
    "DEV api.get_settings()",
    "DEV api.get_preview_hotkey_state()",
    "DEV api.get_preview_hotkey_state()",
)


@pytest.fixture(scope="session")
def saved_layout_page_worker(tmp_path_factory: pytest.TempPathFactory):
    text_tree = TextPageTree()
    text_tree.feed((WEB / "index.html").read_text(encoding="utf-8"))
    structural_tree = PageTree()
    structural_tree.feed((WEB / "index.html").read_text(encoding="utf-8"))
    manifest = tmp_path_factory.mktemp("saved-layout-page-worker") / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "pages": {
                    "text": text_tree.root,
                    "structural": structural_tree.root,
                },
            },
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    node = shutil.which("node")
    assert node is not None, "node is not installed"
    worker = NodeScenarioWorker(
        [
            node,
            str(ROOT / "tests/fixtures/page_scenario_worker.cjs"),
            "--worker",
            "saved-layouts",
            str(WEB),
            str(manifest),
        ],
        cwd=ROOT,
    )
    try:
        yield worker
    finally:
        worker.close()


@pytest.fixture(scope="session")
def saved_layout_receipt_bytes(
    tmp_path_factory: pytest.TempPathFactory,
    request: pytest.FixtureRequest,
) -> bytes:
    evidence = _saved_layout_receipt_once(tmp_path_factory, request.session)
    assert _saved_layout_receipt_build_count(request.session) == 1
    return evidence.receipt_bytes


@pytest.fixture(autouse=True)
def _record_direct_fsync_calls(request: pytest.FixtureRequest):
    real_fsync = os.fsync
    calls = 0

    def counting_fsync(fd: int) -> None:
        nonlocal calls
        calls += 1
        real_fsync(fd)

    os.fsync = counting_fsync
    try:
        yield
    finally:
        os.fsync = real_fsync
        if "test_saved_layout_page_ordering" in request.node.nodeid:
            expected = 0
        elif "test_displayed_owner_controls" in request.node.nodeid:
            expected = SAVED_DIRECT_FSYNC_BY_CASE[
                ("owner", request.node.callspec.params["source"])
            ]
        else:
            assert "test_capture_session_page_ordering" in request.node.nodeid
            expected = SAVED_DIRECT_FSYNC_BY_CASE[
                ("capture", request.node.callspec.params["scenario"])
            ]
        assert calls == expected
        request.node.user_properties.append(("stage_b.direct_fsync_calls", str(calls)))


def _record_saved_worker(
    request: pytest.FixtureRequest,
    worker: NodeScenarioWorker,
    reply: dict[str, object],
) -> None:
    process = worker._proc
    assert process is not None and process.pid > 0
    request.node.user_properties.extend(
        (
            ("stage_b.worker_family", "saved-layouts"),
            ("stage_b.worker_pid", str(process.pid)),
            ("stage_b.worker_request", str(reply["id"])),
        )
    )
    if (
        request.node.nodeid == "tests/test_preview_savedlayouts_page.py::"
        "test_saved_layout_page_ordering[reversed]"
    ):
        request.node.user_properties.extend(
            (
                ("stage_b.receipt_build", "saved-layout-main-v1"),
                ("stage_b.receipt_fsync_calls", "19"),
            )
        )


@dataclass(frozen=True)
class SavedLayoutReceiptEvidence:
    receipt_json: str
    receipt_bytes: bytes
    durable_json: str
    keys: tuple[str, ...]
    fsync_calls: int
    created_id: str
    created_revision: str
    updated_revision: str
    renamed_revision: str
    pending_action: str
    pending_was_true: bool


_SAVED_LAYOUT_RECEIPT_ATTRIBUTE = "_flygd_stage_b_saved_layout_receipt_v1"
_SAVED_LAYOUT_RECEIPT_LOCK_ATTRIBUTE = "_flygd_stage_b_saved_layout_receipt_lock_v1"
_SAVED_LAYOUT_RECEIPT_BUILDS_ATTRIBUTE = "_flygd_stage_b_saved_layout_receipt_builds_v1"
_SAVED_LAYOUT_RECEIPT_CLEANUP_ATTRIBUTE = (
    "_flygd_stage_b_saved_layout_receipt_cleanup_v1"
)
_SAVED_LAYOUT_RECEIPT_SESSION_ATTRIBUTES = (
    _SAVED_LAYOUT_RECEIPT_ATTRIBUTE,
    _SAVED_LAYOUT_RECEIPT_LOCK_ATTRIBUTE,
    _SAVED_LAYOUT_RECEIPT_BUILDS_ATTRIBUTE,
    _SAVED_LAYOUT_RECEIPT_CLEANUP_ATTRIBUTE,
)
_RECEIPT_MUTATION_SENTINELS = {
    "durable": "stage-b mutation receipt-durable-readback",
    "fsync": "stage-b mutation receipt-atomic-writer-fsync",
    "writer": "stage-b mutation receipt-writer-restoration",
    "environment": "stage-b mutation receipt-environment-restoration",
    "reader": "stage-b mutation receipt-reader-release",
    "pending": "stage-b mutation receipt-pending-first-apply",
    "once": "stage-b mutation receipt-once-construction",
}


def _saved_layout_receipt_build_count(session: pytest.Session) -> int:
    return int(getattr(session, _SAVED_LAYOUT_RECEIPT_BUILDS_ATTRIBUTE, 0))


def _saved_layout_receipt_cleanup_registered(session: pytest.Session) -> bool:
    return bool(getattr(session, _SAVED_LAYOUT_RECEIPT_CLEANUP_ATTRIBUTE, False))


def _saved_layout_receipt_once(
    tmp_path_factory: pytest.TempPathFactory,
    session: pytest.Session,
) -> SavedLayoutReceiptEvidence:
    lock = session.__dict__.setdefault(
        _SAVED_LAYOUT_RECEIPT_LOCK_ATTRIBUTE, threading.Lock()
    )
    with lock:
        if not getattr(session, _SAVED_LAYOUT_RECEIPT_CLEANUP_ATTRIBUTE, False):

            def clear_session_receipt() -> None:
                for name in _SAVED_LAYOUT_RECEIPT_SESSION_ATTRIBUTES:
                    if hasattr(session, name):
                        delattr(session, name)

            session.config.add_cleanup(clear_session_receipt)
            setattr(session, _SAVED_LAYOUT_RECEIPT_CLEANUP_ATTRIBUTE, True)
        cached = getattr(session, _SAVED_LAYOUT_RECEIPT_ATTRIBUTE, None)
        if cached is not None:
            return cached
        evidence = _build_saved_layout_receipt(tmp_path_factory)
        builds = _saved_layout_receipt_build_count(session) + 1
        assert builds == 1, _RECEIPT_MUTATION_SENTINELS["once"]
        setattr(session, _SAVED_LAYOUT_RECEIPT_BUILDS_ATTRIBUTE, builds)
        setattr(session, _SAVED_LAYOUT_RECEIPT_ATTRIBUTE, evidence)
        return evidence


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
                    receipt_bytes=receipt_json.encode("utf-8"),
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
def test_saved_layout_page_ordering(
    saved_layout_page_worker,
    saved_layout_receipt_bytes,
    request,
    scenario,
):
    input_payload = json.loads(saved_layout_receipt_bytes.decode("utf-8"))
    input_payload["scenario"] = scenario
    input_payload["page"] = "text"
    reply = saved_layout_page_worker.request(
        f"preview-saved-layouts/page/{scenario}",
        {"protocol": "saved-main", "input": input_payload},
        timeout=25.0,
    )
    assert reply["output"] == f"PASS {scenario}"
    assert reply["diagnostics"] == []
    assert reply["cleanup"] == ZERO_CLEANUP
    _record_saved_worker(request, saved_layout_page_worker, reply)


@pytest.mark.parametrize("source", ["saved", "retained", "excluded"])
def test_displayed_owner_controls_use_real_api_receipts(
    tmp_path, saved_layout_page_worker, request, source
):
    from tests.test_preview_owner_eligibility import owner_api

    api = owner_api(tmp_path, source)
    initial = api.get_preview_hotkey_state()
    marker = api.set_preview_character_marker("Target", "cyan")
    visible = api.set_preview_excluded("Target", False)
    copied = api.copy_preview_layout("Target", "Source")
    reply = saved_layout_page_worker.request(
        f"preview-saved-layouts/owners/{source}",
        {
            "protocol": "saved-owner",
            "input": {
                "source": source,
                "page": "text",
                "scenario": "owner-controls",
                "initial": initial,
                "marker": marker,
                "visible": visible,
                "copied": copied,
            },
        },
        timeout=25.0,
    )
    assert reply["output"] == "PASS owner-controls"
    assert reply["diagnostics"] == []
    assert reply["cleanup"] == ZERO_CLEANUP
    _record_saved_worker(request, saved_layout_page_worker, reply)


@pytest.mark.parametrize("scenario", ["reversed", "local", "boundary", "dev"])
def test_capture_session_page_ordering(
    tmp_path, saved_layout_page_worker, request, scenario
):
    state = make_state(tmp_path)
    with settings.update(state.settings) as doc:
        doc.setdefault("preview", {}).update(seen=["Alice", "Bob"])
    api = Api(state)
    protocol = "saved-dev" if scenario == "dev" else "saved-capture"
    label_group = "dev" if scenario == "dev" else "capture"
    reply = saved_layout_page_worker.request(
        f"preview-saved-layouts/{label_group}/{scenario}",
        {
            "protocol": protocol,
            "input": {
                "scenario": scenario,
                "page": "structural",
                "initial": api.get_preview_hotkey_state(),
            },
        },
        timeout=25.0,
    )
    assert reply["output"] == f"PASS {scenario}"
    if scenario == "dev":
        diagnostics = reply["diagnostics"]
        assert (
            tuple(row["rendered"] for row in diagnostics if row["level"] == "log")
            == SAVED_DEV_LINES
        )
        errors = [row for row in diagnostics if row["level"] == "error"]
        assert len(diagnostics) == 22 and len(errors) == 1
        error = errors[0]
        assert error["rendered"].startswith(
            "onTheme handler failed TypeError: "
            "Cannot read properties of undefined (reading 'apply')"
        )
        assert len(error["args"]) == 3
        assert error["args"][0] == "onTheme handler failed"
        assert error["args"][1]["name"] == "TypeError"
        assert isinstance(error["args"][2], dict)
    else:
        assert reply["diagnostics"] == []
    assert reply["cleanup"] == ZERO_CLEANUP
    _record_saved_worker(request, saved_layout_page_worker, reply)
