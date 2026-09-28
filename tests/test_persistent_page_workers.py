"""Isolation, cleanup, protocol, CLI, and receipt contracts for page workers."""

from __future__ import annotations

import gc
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import weakref
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.html_tree import PageTree, TextPageTree
from tests.node_scenario_worker import (
    NodeScenarioCrash,
    NodeScenarioFailure,
    NodeScenarioWorker,
)
from tests.test_api import Api, make_state
from tests.test_api_fleetsharing import setup
from tests.test_fleetsharing_hydration import SharingPageTree
from tests.test_fleetsharing_worker import drive
from tests.test_preview_owner_eligibility import owner_api
from tests.test_preview_savedlayouts_page import (
    SAVED_DEV_LINES,
    SAVED_DIRECT_FSYNC_TOTAL,
    SavedLayoutReceiptEvidence,
    _saved_layout_receipt_build_count,
    _saved_layout_receipt_cleanup_registered,
    _saved_layout_receipt_once,
)
from wingman import paths, settings
from wingman.preview.labelmarkers import marker_choices

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "wingman/web"
WORKER = ROOT / "tests/fixtures/page_scenario_worker.cjs"
ZERO_CLEANUP = {
    "host_timer_handles": 0,
    "host_callbacks": 0,
    "active_rejection_listeners": 0,
    "pending_rejection_records": 0,
    "retained_realms": 0,
}
FAILURE_MESSAGE_LIMIT = 8192
FAILURE_STACK_LIMIT = 32768
REALM_SENTINELS = {
    "saved-layouts": "stage-b qualification realm saved-layouts: fresh execution violated",
    "fleet-sharing": "stage-b qualification realm fleet-sharing: fresh execution violated",
    "group-backward": "stage-b qualification realm group-backward: fresh execution violated",
    "label-markers": "stage-b qualification realm label-markers: fresh execution violated",
}
MUTATION_SENTINELS = {
    "context": "stage-b mutation realm-saved-context-reuse",
    "source": "stage-b mutation realm-saved-source-reexecution",
    "input": "stage-b mutation realm-saved-input-detachment",
    "reply": "stage-b mutation realm-saved-prior-reply-detachment",
    "module": "stage-b mutation realm-saved-module-export-isolation",
    "promise": "stage-b mutation realm-saved-promise-completion",
    "final-drain": "stage-b mutation rejection-final-timer-drain",
    "native-stack": "stage-b mutation failure-native-error-stack",
    "long-stack": "stage-b mutation failure-native-error-long-stack-envelope",
    "diagnostic-error": "stage-b mutation diagnostics-native-error-detachment",
    "pending": "stage-b mutation receipt-pending-first-apply",
    "identity": "stage-b mutation receipt-production-identity",
    "durable": "stage-b mutation receipt-durable-readback",
    "real-dom": "stage-b mutation real-dom-listener-tracking",
    "saved-program": "stage-b mutation adapter-saved-program-selection",
    "sharing-source": "stage-b mutation realm-sharing-completion-reuse",
    "group-source": "stage-b mutation realm-group-source-reexecution",
    "marker-root": "stage-b mutation marker-retained-realm-release",
    "business-retention": "stage-b mutation business-failure-process-retention",
    "fatal-no-replay": "stage-b mutation protocol-fatal-no-replay",
}


@dataclass(frozen=True)
class DirectCliCase:
    name: str
    program: str
    input_json: str
    extra_argv: tuple[str, ...]
    terminal: str


@dataclass(frozen=True)
class QualificationInputs:
    manifests: tuple[tuple[str, str], ...]
    direct_cases: tuple[DirectCliCase, ...]
    receipt: SavedLayoutReceiptEvidence
    qualification_fsync_calls: int

    def manifest_for(self, family: str) -> Path:
        return Path(dict(self.manifests)[family])


def _json_text(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )


def _reader_snapshot() -> dict[int, weakref.ReferenceType[object]]:
    return {
        key: weakref.ref(value) for key, value in settings._COMMITTED_PREVIEWS.items()
    }


def _build_qualification_inputs(
    tmp_path_factory: pytest.TempPathFactory,
    session: pytest.Session,
) -> QualificationInputs:
    receipt = _saved_layout_receipt_once(tmp_path_factory, session)
    root = tmp_path_factory.mktemp("persistent-page-qualification")
    state_root = root / "state"
    state_root.mkdir()
    had_localappdata = "LOCALAPPDATA" in os.environ
    original_localappdata = os.environ.get("LOCALAPPDATA")
    original_use_legacy = paths._use_legacy
    original_save_locked = settings._save_locked
    original_fsync = os.fsync
    baseline_readers = _reader_snapshot()
    owned_refs: list[weakref.ReferenceType[object]] = []
    reader_keys: set[int] = set()
    fsync_calls = 0
    apis: list[Api] = []
    result = None

    def counting_fsync(fd: int) -> None:
        nonlocal fsync_calls
        fsync_calls += 1
        original_fsync(fd)

    text_tree = TextPageTree()
    text_tree.feed((WEB / "index.html").read_text(encoding="utf-8"))
    structural_tree = PageTree()
    structural_tree.feed((WEB / "index.html").read_text(encoding="utf-8"))
    sharing_tree = SharingPageTree()
    sharing_tree.feed((WEB / "index.html").read_text(encoding="utf-8"))
    pages_by_family = {
        "saved-layouts": {"text": text_tree.root, "structural": structural_tree.root},
        "fleet-sharing": {"sharing": sharing_tree.root},
        "group-backward": {"structural": structural_tree.root},
        "label-markers": {"structural": structural_tree.root},
    }
    manifests = []
    for family, pages in pages_by_family.items():
        manifest = root / (family + "-manifest.json")
        manifest.write_text(
            _json_text({"version": 1, "pages": pages}), encoding="utf-8"
        )
        manifests.append((family, str(manifest)))

    try:
        with pytest.MonkeyPatch.context() as patch:
            patch.setenv("LOCALAPPDATA", str(state_root))
            patch.setattr(paths, "_use_legacy", False)
            patch.setattr(os, "fsync", counting_fsync)
            try:
                saved_api = owner_api(state_root, "saved")
                apis.append(saved_api)
                reader_keys.add(id(saved_api._state.settings))
                owned_refs.extend(
                    weakref.ref(value)
                    for value in (
                        saved_api,
                        saved_api._state,
                        saved_api._preview_config,
                        saved_api._preview_layouts,
                    )
                )
                owner_payload = {
                    "page": text_tree.root,
                    "scenario": "owner-controls",
                    "initial": saved_api.get_preview_hotkey_state(),
                    "marker": saved_api.set_preview_character_marker("Target", "cyan"),
                    "visible": saved_api.set_preview_excluded("Target", False),
                    "copied": saved_api.copy_preview_layout("Target", "Source"),
                }

                capture_state = make_state(state_root)
                with settings.update(capture_state.settings) as capture_doc:
                    capture_doc.setdefault("preview", {}).update(seen=["Alice", "Bob"])
                capture_api = Api(capture_state)
                apis.append(capture_api)
                reader_keys.add(id(capture_state.settings))
                owned_refs.extend(
                    weakref.ref(value)
                    for value in (
                        capture_api,
                        capture_state,
                        capture_api._preview_config,
                        capture_api._preview_layouts,
                    )
                )
                capture_payload = {
                    "scenario": "reversed",
                    "page": structural_tree.root,
                    "initial": capture_api.get_preview_hotkey_state(),
                }

                missing_state = make_state(state_root, **settings.load())
                missing_api = Api(missing_state)
                apis.append(missing_api)
                reader_keys.add(id(missing_state.settings))
                live_api, worker, _client, _store, mono, _timers = setup(state_root)
                apis.append(live_api)
                reader_keys.add(id(live_api._state.settings))
                owned_refs.extend(
                    weakref.ref(value)
                    for value in (
                        missing_api,
                        missing_state,
                        missing_api._preview_config,
                        missing_api._preview_layouts,
                        live_api,
                        live_api._state,
                        live_api._preview_config,
                        live_api._preview_layouts,
                    )
                )
                older = live_api.fleet_sharing_state()
                worker.set_source_watch(True)
                drive(worker, mono, 12)
                sharing_payload = {
                    "page": sharing_tree.root,
                    "missing": missing_api.fleet_sharing_watch(True),
                    "live": live_api.fleet_sharing_state(),
                    "older": older,
                    "rejected": None,
                    "preference_case": None,
                }

                saved_payload = json.loads(receipt.receipt_json)
                saved_payload.update(scenario="reversed", page=text_tree.root)
                group_payload = {
                    "page": structural_tree.root,
                    "choices": marker_choices(),
                    "scenario": "dev",
                }
                marker_payload = {
                    "page": structural_tree.root,
                    "choices": marker_choices(),
                    "scenario": "hydration",
                }
                dev_payload = dict(capture_payload, scenario="dev")
                direct_cases = (
                    DirectCliCase(
                        "saved-main",
                        "preview_savedlayouts.cjs",
                        _json_text(saved_payload),
                        (),
                        "PASS reversed",
                    ),
                    DirectCliCase(
                        "saved-owner",
                        "preview_savedlayouts.cjs",
                        _json_text(owner_payload),
                        (),
                        "PASS owner-controls",
                    ),
                    DirectCliCase(
                        "saved-capture",
                        "preview_capture_sessions.cjs",
                        _json_text(capture_payload),
                        (),
                        "PASS reversed",
                    ),
                    DirectCliCase(
                        "saved-dev",
                        "preview_dev_capture.cjs",
                        _json_text(dev_payload),
                        (),
                        "PASS dev",
                    ),
                    DirectCliCase(
                        "fleet-sharing",
                        "fleetsharing_page.cjs",
                        _json_text(sharing_payload),
                        ("missing-worker",),
                        "PASS missing-worker",
                    ),
                    DirectCliCase(
                        "group-backward",
                        "preview_group_backward.cjs",
                        _json_text(group_payload),
                        (),
                        "PASS group backward dev",
                    ),
                    DirectCliCase(
                        "label-markers",
                        "preview_labelmarkers.cjs",
                        _json_text(marker_payload),
                        (),
                        "PASS marker page hydration",
                    ),
                )
                assert fsync_calls == 4
                result = QualificationInputs(
                    manifests=tuple(manifests),
                    direct_cases=direct_cases,
                    receipt=receipt,
                    qualification_fsync_calls=fsync_calls,
                )
            finally:
                for owned_api in reversed(apis):
                    owned_api.shutdown_previews()
                    vars(owned_api).clear()
                apis.clear()
                owned_api = None
                saved_api = None
                capture_api = None
                capture_state = None
                capture_doc = None
                missing_api = None
                missing_state = None
                live_api = None
                worker = None
                gc.collect()
                retained = {
                    key: settings._COMMITTED_PREVIEWS.get(key)
                    for key in reader_keys
                    if settings._COMMITTED_PREVIEWS.get(key) is not None
                }
                assert not retained
                assert all(reference() is None for reference in owned_refs)
    finally:
        paths._use_legacy = original_use_legacy

    assert ("LOCALAPPDATA" in os.environ) is had_localappdata
    assert os.environ.get("LOCALAPPDATA") == original_localappdata
    assert paths._use_legacy is original_use_legacy
    assert settings._save_locked is original_save_locked
    assert os.fsync is original_fsync
    assert not {
        key: value
        for key, reference in baseline_readers.items()
        if (value := reference()) is not None
        and settings._COMMITTED_PREVIEWS.get(key) is not value
    }
    assert result is not None
    return result


@pytest.fixture(scope="session")
def qualification_inputs(
    tmp_path_factory: pytest.TempPathFactory,
    request: pytest.FixtureRequest,
) -> QualificationInputs:
    return _build_qualification_inputs(tmp_path_factory, request.session)


@pytest.fixture
def page_worker_factory(qualification_inputs: QualificationInputs):
    node = shutil.which("node")
    assert node is not None, "node is not installed"
    workers: list[NodeScenarioWorker] = []

    def create(family: str) -> NodeScenarioWorker:
        worker = NodeScenarioWorker(
            [
                node,
                str(WORKER),
                "--worker",
                family,
                str(WEB),
                str(qualification_inputs.manifest_for(family)),
            ],
            cwd=ROOT,
        )
        workers.append(worker)
        return worker

    try:
        yield create
    finally:
        errors = []
        for worker in reversed(workers):
            try:
                worker.close()
            except NodeScenarioCrash as error:
                errors.append(error)
        if errors:
            raise errors[0]


def _qualification_request(
    worker: NodeScenarioWorker,
    family: str,
    mode: str,
    **values: object,
) -> dict[str, object]:
    page = (
        "sharing"
        if family == "fleet-sharing"
        else "text"
        if family == "saved-layouts"
        else "structural"
    )
    payload = {"mode": mode, "page": page, **values}
    return worker.request(
        f"qualification/{family}/{mode}",
        {"protocol": "qualification", "input": payload},
        timeout=10.0,
    )


def _saved_main_request(
    worker: NodeScenarioWorker,
    inputs: QualificationInputs,
    *,
    mode: str,
    run: str = "",
) -> dict[str, object]:
    input_payload = json.loads(inputs.receipt.receipt_json)
    input_payload.update(
        scenario="reversed",
        page="text",
        mode=mode,
        run=run,
        nested={"value": "clean"},
    )
    return worker.request(
        "preview-saved-layouts/page/reversed",
        {"protocol": "saved-main", "input": input_payload},
        timeout=25.0,
    )


def _fleet_request(
    worker: NodeScenarioWorker,
    inputs: QualificationInputs,
    *,
    mode: str,
    run: str,
) -> dict[str, object]:
    case = next(item for item in inputs.direct_cases if item.name == "fleet-sharing")
    payload = json.loads(case.input_json)
    payload.update(
        scenario="missing-worker",
        page="sharing",
        mode=mode,
        run=run,
        nested={"value": "clean"},
    )
    return worker.request(
        "fleet-sharing/page/missing-worker",
        {"protocol": "fleet-sharing", "input": payload},
        timeout=20.0,
    )


def _realm_request(
    worker: NodeScenarioWorker,
    family: str,
    inputs: QualificationInputs,
    run: str,
) -> dict[str, object]:
    if family == "saved-layouts":
        return _saved_main_request(worker, inputs, mode="realm", run=run)
    if family == "fleet-sharing":
        return _fleet_request(worker, inputs, mode="realm", run=run)
    case_name, protocol, scenario, label, page, timeout = {
        "group-backward": (
            "group-backward",
            "group-backward",
            "dev",
            "preview-group-backward/page/dev",
            "structural",
            30.0,
        ),
        "label-markers": (
            "label-markers",
            "label-markers",
            "hydration",
            "preview-label-markers/page/hydration",
            "structural",
            30.0,
        ),
    }[family]
    case = next(item for item in inputs.direct_cases if item.name == case_name)
    payload = json.loads(case.input_json)
    payload.update(
        scenario=scenario,
        page=page,
        mode="realm",
        run=run,
        nested={"value": "clean"},
    )
    return worker.request(
        label,
        {"protocol": protocol, "input": payload},
        timeout=timeout,
    )


def _record_qualification(
    request: pytest.FixtureRequest, *, worker_starts: int, fsync_calls: int
) -> None:
    request.node.user_properties.append(
        ("stage_b.qualification.worker_starts", str(worker_starts))
    )
    request.node.user_properties.append(
        ("stage_b.qualification.fsync_calls", str(fsync_calls))
    )


def _assert_mutation(condition: object, key: str) -> None:
    assert condition, MUTATION_SENTINELS[key]


def _fail_mutation(key: str) -> None:
    raise AssertionError(MUTATION_SENTINELS[key]) from None


def _is_exact_target_module_retention(error: NodeScenarioCrash) -> bool:
    rendered = str(error)
    return (
        "request retained a target module" in rendered
        and '"require_cache_targets":[' in rendered
        and '"module_child_targets":[' in rendered
        and rendered.count("screenshot_dom.cjs") >= 2
    )


def _raise_target_module_mutation_or_original(error: NodeScenarioCrash) -> None:
    if _is_exact_target_module_retention(error):
        _fail_mutation("module")
    raise error


def _load_bare_saved_layout_module() -> tuple[object, bool]:
    existing = sys.modules.get("test_preview_savedlayouts_page")
    if existing is not None:
        return existing, False
    module_path = ROOT / "tests/test_preview_savedlayouts_page.py"
    spec = importlib.util.spec_from_file_location(
        "test_preview_savedlayouts_page", module_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:  # Remove the incomplete alias before rethrowing.
        sys.modules.pop(spec.name, None)
        raise
    return module, True


def _assert_finite_json(value: object) -> None:
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, (int, float)):
        assert not isinstance(value, bool)
        assert value == value and value not in (float("inf"), float("-inf"))
        return
    if isinstance(value, list):
        for item in value:
            _assert_finite_json(item)
        return
    assert isinstance(value, dict)
    for key, item in value.items():
        assert isinstance(key, str)
        _assert_finite_json(item)


def _assert_group_dev_diagnostics(rows: list[dict[str, object]]) -> str:
    assert len(rows) == 5
    assert [row["level"] for row in rows] == ["log"] * 5
    generated = rows[1]["args"][1]
    assert isinstance(generated, str)
    assert re.fullmatch(r"g-dev-\d+", generated)
    expected_args = [
        ["DEV api.create_preview_cycle_group(", "Backward test", ")"],
        ["DEV api.set_preview_cycle_group_bind(", generated, "Ctrl+F2", ")"],
        [
            "DEV api.set_preview_cycle_group_prev_bind(",
            generated,
            "Ctrl+F3",
            ")",
        ],
        ["DEV api.set_preview_cycle_group_prev_bind(", "stale", "Ctrl+F4", ")"],
        ["DEV api.set_preview_cycle_group_prev_bind(", generated, "", ")"],
    ]
    assert [row["args"] for row in rows] == expected_args
    expected_rendered = [
        "DEV api.create_preview_cycle_group( Backward test )",
        f"DEV api.set_preview_cycle_group_bind( {generated} Ctrl+F2 )",
        f"DEV api.set_preview_cycle_group_prev_bind( {generated} Ctrl+F3 )",
        "DEV api.set_preview_cycle_group_prev_bind( stale Ctrl+F4 )",
        f"DEV api.set_preview_cycle_group_prev_bind( {generated}  )",
    ]
    assert [row["rendered"] for row in rows] == expected_rendered
    return generated


@pytest.mark.parametrize(
    "family",
    ["saved-layouts", "fleet-sharing", "group-backward", "label-markers"],
)
def test_request_realm_is_fresh_and_program_is_reexecuted(
    family, page_worker_factory, qualification_inputs, request
):
    worker = page_worker_factory(family)
    try:
        first = _realm_request(worker, family, qualification_inputs, "A")
    except NodeScenarioCrash as error:
        if _is_exact_target_module_retention(error):
            _fail_mutation("module")
        if family == "label-markers" and "retained a VM realm" in str(error):
            _fail_mutation("marker-root")
        raise
    except NodeScenarioFailure as error:
        rendered = str(error)
        if family == "saved-layouts" and "business source" in rendered:
            _fail_mutation("saved-program")
        if family == "fleet-sharing" and "business source" in rendered:
            _fail_mutation("sharing-source")
        if family == "group-backward" and "business source" in rendered:
            _fail_mutation("group-source")
        raise
    process = worker._proc
    assert first["output"].get("serialization_safe") is True, REALM_SENTINELS[family]
    first["output"]["nested_python_poison"] = True
    try:
        poison = _realm_request(worker, family, qualification_inputs, "poison")
        final = _realm_request(worker, family, qualification_inputs, "A")
    except NodeScenarioCrash as error:
        if _is_exact_target_module_retention(error):
            _fail_mutation("module")
        if family == "label-markers" and "retained a VM realm" in str(error):
            _fail_mutation("marker-root")
        if (
            "poisoned" in str(error)
            or "already been declared" in str(error)
            or "JSON at position" in str(error)
        ):
            _fail_mutation("context")
        raise
    except NodeScenarioFailure as error:
        rendered = str(error)
        if family == "saved-layouts" and "business source" in rendered:
            _fail_mutation("saved-program")
        if family == "fleet-sharing" and "business source" in rendered:
            _fail_mutation("sharing-source")
        if family == "group-backward" and "business source" in rendered:
            _fail_mutation("group-source")
        if family == "label-markers" and "business source" in rendered:
            _fail_mutation("source")
        if "poisoned" in rendered:
            _fail_mutation("context")
        raise

    assert process is not None and worker._proc is not None
    assert worker._proc.pid == process.pid
    _assert_mutation(final["output"]["realm_pristine"] is True, "context")
    source_executed = all(
        reply["output"]["source_execution_count"] == 1
        for reply in (first, poison, final)
    )
    _assert_mutation(
        source_executed,
        "sharing-source" if family == "fleet-sharing" else "source",
    )
    run_values_are_fresh = [
        reply["output"]["run"] for reply in (first, poison, final)
    ] == ["A", "poison", "A"]
    _assert_mutation(
        run_values_are_fresh,
        "sharing-source" if family == "fleet-sharing" else "context",
    )
    _assert_mutation(
        len(
            {
                first["output"]["realm_token"],
                poison["output"]["realm_token"],
                final["output"]["realm_token"],
            }
        )
        == 3,
        "context",
    )
    _assert_mutation(
        all(
            reply["output"]["host_input_clean"] is True
            for reply in (first, poison, final)
        ),
        "input",
    )
    _assert_mutation(
        all(
            reply["output"]["prior_reply_detached"] is True
            for reply in (first, poison, final)
        ),
        "reply",
    )
    _assert_mutation(
        all(
            reply["output"]["module_export_isolated"] is True
            for reply in (first, poison, final)
        ),
        "module",
    )
    _assert_mutation(poison["output"]["promise_completion"] is True, "promise")
    assert poison["output"]["serialization_safe"] is True
    assert poison["output"]["mode"] == "realm"
    assert poison["output"]["array_after_poison"] == ["outer", ["inner", 7]]
    assert first["output"]["array_after_poison"] is None
    assert final["output"]["array_after_poison"] is None
    expected_business_output = {
        "saved-layouts": "PASS reversed",
        "fleet-sharing": "PASS missing-worker",
        "group-backward": "PASS group backward dev",
        "label-markers": "PASS marker page hydration",
    }[family]
    business_output_matches = all(
        reply["output"]["business_output"] == expected_business_output
        for reply in (first, poison, final)
    )
    if family == "saved-layouts":
        _assert_mutation(business_output_matches, "saved-program")
    else:
        assert business_output_matches
    if family in {"saved-layouts", "fleet-sharing"}:
        _assert_mutation(
            all(
                reply["output"]["registered_real_listeners"] > 0
                and reply["output"]["real_listeners_after_cleanup"] == 0
                for reply in (first, poison, final)
            ),
            "real-dom" if family == "saved-layouts" else "sharing-source",
        )
    assert poison["output"].get("output") != "forged"
    poison_diagnostics = poison["diagnostics"]
    expected_poison = {
        "level": "warn",
        "rendered": 'realm poison {"nested":{"value":"before"}}',
        "args": ["realm poison", {"nested": {"value": "before"}}],
    }
    if family == "group-backward":
        _assert_group_dev_diagnostics(first["diagnostics"])
        _assert_group_dev_diagnostics(poison_diagnostics[:-1])
        _assert_group_dev_diagnostics(final["diagnostics"])
        assert poison_diagnostics[-1] == expected_poison
        wrong_suffix = json.loads(json.dumps(first["diagnostics"]))
        wrong_suffix[1]["args"][2] = "Ctrl+F9"
        with pytest.raises(AssertionError):
            _assert_group_dev_diagnostics(wrong_suffix)
        empty_args = json.loads(json.dumps(first["diagnostics"]))
        empty_args[0]["args"] = []
        with pytest.raises(AssertionError):
            _assert_group_dev_diagnostics(empty_args)
    else:
        assert poison_diagnostics == [expected_poison]
    assert final["output"]["host_prototypes_clean"] is True
    assert final["output"]["realm_pristine"] is True
    assert final["output"]["dom_pristine"] is True
    assert final["output"]["poison_absent"] is True
    assert final["output"]["decoded_input_value"] == "clean"
    assert final["output"]["prior_reply_value"] == "clean"
    assert "nested_python_poison" not in final["output"]
    assert first["cleanup"] == poison["cleanup"] == final["cleanup"] == ZERO_CLEANUP
    _record_qualification(request, worker_starts=1, fsync_calls=0)


def _run_direct_cli_matrix(inputs: QualificationInputs) -> None:
    node = shutil.which("node")
    assert node is not None
    with tempfile.TemporaryDirectory(prefix="stage-b-direct-cli-") as directory:
        temporary = Path(directory)
        for index, case in enumerate(inputs.direct_cases):
            data = temporary / f"{index}-{case.name}.json"
            data.write_text(case.input_json, encoding="utf-8")
            program = ROOT / "tests/fixtures" / case.program
            argv = [node, str(program), str(data), *case.extra_argv, str(WEB)]
            success = subprocess.run(
                argv,
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
                check=False,
            )
            assert success.returncode == 0, success.stdout + success.stderr
            stdout_lines = success.stdout.splitlines()
            assert stdout_lines[-1] == case.terminal
            assert stdout_lines.count(case.terminal) == 1
            if case.name == "saved-dev":
                assert tuple(stdout_lines[:-1]) == SAVED_DEV_LINES
                assert success.stderr.count("onTheme handler failed") == 1
                assert (
                    "Cannot read properties of undefined (reading 'apply')"
                    in success.stderr
                )
            elif case.name == "group-backward":
                assert len(stdout_lines) == 6
                assert stdout_lines[0] == (
                    "DEV api.create_preview_cycle_group( Backward test )"
                )
                forward = re.fullmatch(
                    r"DEV api\.set_preview_cycle_group_bind\( ([^ ]+) Ctrl\+F2 \)",
                    stdout_lines[1],
                )
                backward = re.fullmatch(
                    r"DEV api\.set_preview_cycle_group_prev_bind\( ([^ ]+) Ctrl\+F3 \)",
                    stdout_lines[2],
                )
                assert stdout_lines[3] == (
                    "DEV api.set_preview_cycle_group_prev_bind( stale Ctrl+F4 )"
                )
                cleared = re.fullmatch(
                    r"DEV api\.set_preview_cycle_group_prev_bind\( ([^ ]+)  \)",
                    stdout_lines[4],
                )
                assert (
                    forward is not None and backward is not None and cleared is not None
                )
                assert forward.group(1) == backward.group(1) == cleared.group(1)
                assert success.stderr == ""
            else:
                assert stdout_lines == [case.terminal]
                assert success.stderr == ""

            missing = subprocess.run(
                [node, str(program)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=10,
                check=False,
            )
            assert missing.returncode != 0
            assert "PASS" not in missing.stdout
            assert missing.stdout == ""
            assert missing.stderr

            corrupt = temporary / f"{index}-{case.name}-corrupt.json"
            corrupt.write_text("{", encoding="utf-8")
            corrupt_result = subprocess.run(
                [node, str(program), str(corrupt), *case.extra_argv, str(WEB)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=10,
                check=False,
            )
            assert corrupt_result.returncode != 0
            assert case.terminal not in corrupt_result.stdout
            assert corrupt_result.stderr


def test_request_cleanup_after_success(
    page_worker_factory, qualification_inputs, request
):
    assert qualification_inputs.receipt.fsync_calls == 19
    assert _saved_layout_receipt_build_count(request.session) == 1
    assert _saved_layout_receipt_cleanup_registered(request.session)
    assert (
        qualification_inputs.receipt.fsync_calls
        + qualification_inputs.qualification_fsync_calls
        + SAVED_DIRECT_FSYNC_TOTAL
        == 37
    )
    unrelated_startup = NodeScenarioCrash(
        "qualification/saved-layouts/resources", "worker startup ENOENT"
    )
    assert not _is_exact_target_module_retention(unrelated_startup)
    with pytest.raises(NodeScenarioCrash, match="ENOENT"):
        _raise_target_module_mutation_or_original(unrelated_startup)

    worker = page_worker_factory("saved-layouts")
    resources = _qualification_request(worker, "saved-layouts", "resources")
    process = worker._proc
    assert resources["output"]["registered_timer_handles"] >= 2
    assert resources["output"]["registered_listeners"] == 1
    assert resources["output"]["registered_real_listeners"] == 0
    assert resources["output"]["real_listeners_after_cleanup"] == 0
    assert resources["cleanup"] == ZERO_CLEANUP, (
        "stage-b qualification cleanup-success: retained resources"
    )
    asynchronous = _qualification_request(worker, "saved-layouts", "async-timer")
    assert asynchronous["output"]["async_globals"] is True
    assert asynchronous["diagnostics"] == [
        {
            "level": "info",
            "rendered": 'async timer complete {"ready":true}',
            "args": ["async timer complete", {"ready": True}],
        }
    ]
    listener_poison = _qualification_request(
        worker, "saved-layouts", "cleanup-listener-poison"
    )
    assert listener_poison["output"]["registered_listeners"] == 1
    assert listener_poison["cleanup"] == ZERO_CLEANUP

    node = shutil.which("node")
    assert node is not None
    cleanup_failure_worker = NodeScenarioWorker(
        [
            node,
            str(WORKER),
            "--worker",
            "fleet-sharing",
            str(WEB),
            str(qualification_inputs.manifest_for("fleet-sharing")),
        ],
        cwd=ROOT,
    )
    try:
        cleanup_failure_worker._ensure_started("fleet-sharing/page/missing-worker")
        real_listener_process = cleanup_failure_worker._proc
        assert real_listener_process is not None
        with pytest.raises(NodeScenarioCrash) as cleanup_failure:
            _fleet_request(
                cleanup_failure_worker,
                qualification_inputs,
                mode="real-listener-removal-failure",
                run="fault",
            )
        assert cleanup_failure.value.reply is None
        assert "real listener removal failure" in str(cleanup_failure.value)
        assert cleanup_failure_worker._proc is None
        assert real_listener_process.poll() is not None
        fleet_recovery = _fleet_request(
            cleanup_failure_worker,
            qualification_inputs,
            mode="realm",
            run="recovery",
        )
        assert fleet_recovery["cleanup"] == ZERO_CLEANUP
        assert fleet_recovery["output"]["registered_real_listeners"] > 0
        assert fleet_recovery["output"]["real_listeners_after_cleanup"] == 0
        assert cleanup_failure_worker._proc is not None
        assert cleanup_failure_worker._proc.pid != real_listener_process.pid
        with pytest.raises(NodeScenarioCrash) as timer_failure:
            _qualification_request(
                cleanup_failure_worker,
                "fleet-sharing",
                "cleanup-timer-failure",
            )
        assert "synthetic timer cleanup failure" in str(timer_failure.value)
        assert cleanup_failure_worker._proc is None
        cleanup_recovery = _qualification_request(
            cleanup_failure_worker, "fleet-sharing", "clean"
        )
        assert cleanup_recovery["cleanup"] == ZERO_CLEANUP
    finally:
        cleanup_failure_worker.close()

    diagnostics = _qualification_request(worker, "saved-layouts", "diagnostics")
    diagnostic_rows = diagnostics["diagnostics"]
    assert diagnostic_rows[:5] == [
        {
            "level": "log",
            "rendered": 'ordinary diagnostic 7 {"nested":{"value":"before"}}',
            "args": ["ordinary diagnostic", 7, {"nested": {"value": "before"}}],
        },
        {
            "level": "info",
            "rendered": 'info diagnostic {"index":2}',
            "args": ["info diagnostic", {"index": 2}],
        },
        {
            "level": "debug",
            "rendered": 'debug diagnostic {"index":3}',
            "args": ["debug diagnostic", {"index": 3}],
        },
        {
            "level": "warn",
            "rendered": 'warn diagnostic {"index":4}',
            "args": ["warn diagnostic", {"index": 4}],
        },
        {
            "level": "error",
            "rendered": 'expected diagnostic {"kind":"controlled"}',
            "args": ["expected diagnostic", {"kind": "controlled"}],
        },
    ]
    native_rows = diagnostic_rows[5:]
    _assert_mutation(
        [row["level"] for row in native_rows]
        == ["log", "info", "debug", "warn", "error"],
        "diagnostic-error",
    )
    _assert_mutation(len(native_rows) == 5, "diagnostic-error")
    for level, row in zip(
        ("log", "info", "debug", "warn", "error"), native_rows, strict=True
    ):
        detached_error = row["args"][1]
        _assert_mutation(
            isinstance(detached_error, dict)
            and detached_error.get("name") == "TypeError"
            and detached_error.get("message") == "synthetic diagnostic TypeError"
            and detached_error.get("stack", "").startswith(
                "TypeError: synthetic diagnostic TypeError"
            )
            and "\n    at " in detached_error.get("stack", ""),
            "diagnostic-error",
        )
        assert row["args"] == [
            f"{level} native diagnostic",
            detached_error,
            "<unserializable>",
            "<unserializable>",
        ]
        assert row["rendered"].startswith(
            f"{level} native diagnostic TypeError: synthetic diagnostic TypeError"
        )
        assert "\n    at " in row["rendered"]
        assert row["rendered"].endswith("<unserializable> <unserializable>")
    forged = _qualification_request(worker, "saved-layouts", "completion-forge")
    assert forged["ok"] is True
    assert forged["output"]["own_value"] == "preserved"
    assert forged["output"].get("output") != "forged"
    clean = _qualification_request(worker, "saved-layouts", "clean")
    assert worker._proc is not None and process is not None
    assert worker._proc.pid == process.pid
    assert clean["cleanup"] == ZERO_CLEANUP

    inventory = _qualification_request(worker, "saved-layouts", "inventory")
    structure = inventory["output"]["inventory"]
    assert len(structure["source_manifest"]) == 7
    assert all(
        row["bytes"] > 0 and len(row["sha256"]) == 64
        for row in structure["source_manifest"]
    )
    assert structure["require_cache_targets"] == []
    assert structure["module_child_targets"] == []
    assert structure["retained_target_functions"] == 0
    assert inventory["cleanup"] == ZERO_CLEANUP

    _run_direct_cli_matrix(qualification_inputs)
    _record_qualification(
        request,
        worker_starts=1,
        fsync_calls=qualification_inputs.qualification_fsync_calls,
    )


def _assert_business_failure(
    worker: NodeScenarioWorker, mode: str, *, expected: str
) -> NodeScenarioFailure:
    process = worker._proc
    captured: NodeScenarioFailure | None = None
    try:
        _qualification_request(worker, "saved-layouts", mode)
    except NodeScenarioFailure as failure:
        assert expected in str(failure)
        captured = failure
    except NodeScenarioCrash:
        _fail_mutation("business-retention")
    else:
        _fail_mutation("business-retention")
    assert worker._proc is not None
    if process is not None:
        assert worker._proc.pid == process.pid
    clean = _qualification_request(worker, "saved-layouts", "clean")
    assert clean["cleanup"] == ZERO_CLEANUP
    assert worker._proc is not None
    if process is not None:
        assert worker._proc.pid == process.pid
    assert captured is not None
    return captured


def _assert_final_timer_failure(worker: NodeScenarioWorker) -> None:
    process = worker._proc
    try:
        _qualification_request(worker, "saved-layouts", "nested-boundary-rejection")
    except NodeScenarioFailure as failure:
        _assert_mutation(
            "synthetic nested timer-boundary rejection" in str(failure),
            "final-drain",
        )
    except NodeScenarioCrash:
        worker._discard_process(reason="final timer rejection escaped")
        _fail_mutation("final-drain")
    else:
        worker._discard_process(reason="final timer rejection was missed")
        _fail_mutation("final-drain")
    _assert_mutation(
        process is not None
        and worker._proc is not None
        and worker._proc.pid == process.pid,
        "final-drain",
    )
    clean = _qualification_request(worker, "saved-layouts", "clean")
    _assert_mutation(clean["cleanup"] == ZERO_CLEANUP, "final-drain")
    _assert_mutation(
        worker._proc is not None and worker._proc.pid == process.pid,
        "final-drain",
    )


def _assert_long_stack_failure(worker: NodeScenarioWorker) -> None:
    process = worker._proc
    try:
        _qualification_request(worker, "saved-layouts", "long-stack-rejection")
    except NodeScenarioFailure as failure:
        reply = failure.reply
        _assert_mutation(
            reply is not None
            and len(str(reply["error"])) == FAILURE_MESSAGE_LIMIT
            and str(reply["error"]).startswith("synthetic long failure ")
            and len(failure.stack) == FAILURE_STACK_LIMIT
            and failure.stack.startswith("TypeError: synthetic long failure ")
            and "retainedLongStackFrame" in failure.stack
            and "\x00" in failure.stack,
            "long-stack",
        )
    except NodeScenarioCrash:
        worker._discard_process(reason="long failure envelope was rejected")
        _fail_mutation("long-stack")
    else:
        worker._discard_process(reason="long failure unexpectedly succeeded")
        _fail_mutation("long-stack")
    _assert_mutation(
        process is not None
        and worker._proc is not None
        and worker._proc.pid == process.pid,
        "long-stack",
    )
    clean = _qualification_request(worker, "saved-layouts", "clean")
    _assert_mutation(clean["cleanup"] == ZERO_CLEANUP, "long-stack")
    _assert_mutation(
        worker._proc is not None and worker._proc.pid == process.pid,
        "long-stack",
    )


def _request_invalid_payload(worker: NodeScenarioWorker) -> dict[str, object]:
    return worker.request(
        "qualification/saved-layouts/clean",
        {"protocol": "qualification"},
        timeout=5.0,
    )


def test_request_cleanup_after_business_failure(
    page_worker_factory, qualification_inputs, request
):
    worker = page_worker_factory("saved-layouts")
    ordinary = _assert_business_failure(
        worker, "error", expected="synthetic Error failure"
    )
    _assert_mutation(
        ordinary.stack.startswith("Error: synthetic Error failure")
        and "\n    at " in ordinary.stack,
        "native-stack",
    )
    process_a = worker._proc
    assert process_a is not None
    accessor = _assert_business_failure(
        worker, "accessor-error", expected="synthetic accessor failure"
    )
    _assert_mutation(
        accessor.stack == "AccessorTypeError: synthetic accessor failure\n"
        "    at syntheticAccessorFrame (qualification.cjs:1:1)",
        "native-stack",
    )
    hostile_native = _assert_business_failure(
        worker, "hostile-native-error", expected="<unreadable message>"
    )
    _assert_mutation(hostile_native.stack == "<unreadable stack>", "native-stack")
    for mode, expected in (
        ("primitive", "synthetic primitive failure"),
        ("null", "null"),
        ("hostile", "<unreadable message>"),
        ("proxy", "<unreadable message>"),
        ("hostile-completion", "JSON object keys were unreadable"),
        ("invalid-business", "synthetic invalid business input"),
        ("before-rejection", "synthetic before-settlement rejection"),
        ("boundary-rejection", "synthetic timer-boundary rejection"),
    ):
        _assert_business_failure(worker, mode, expected=expected)
        assert worker._proc is not None and worker._proc.pid == process_a.pid, (
            "stage-b qualification cleanup-failure: process retention violated"
        )

    _assert_final_timer_failure(worker)
    assert worker._proc is not None and worker._proc.pid == process_a.pid
    _assert_long_stack_failure(worker)
    assert worker._proc is not None and worker._proc.pid == process_a.pid
    poisoned = _assert_business_failure(
        worker, "poisoned-error", expected="protected poisoned Error failure"
    )
    _assert_mutation(
        poisoned.stack.startswith("Error: protected poisoned Error failure")
        and "\n    at " in poisoned.stack
        and "ForgedError" not in poisoned.stack
        and "forged reflected failure" not in poisoned.stack,
        "native-stack",
    )
    fatal_id = worker._next_id
    try:
        _request_invalid_payload(worker)
    except NodeScenarioCrash as fatal:
        assert fatal.scenario == "qualification/saved-layouts/clean"
        assert fatal.reply is None
    else:
        _fail_mutation("fatal-no-replay")
    assert worker._proc is None

    late = _qualification_request(worker, "saved-layouts", "late-success")
    process_b = worker._proc
    late_id = late["id"]
    assert process_b is not None and process_b.pid != process_a.pid
    deadline = time.monotonic() + 2.0
    while process_b.poll() is None and time.monotonic() < deadline:
        time.sleep(0.01)
    assert process_b.poll() is not None
    with pytest.raises(NodeScenarioCrash) as late_crash:
        _qualification_request(worker, "saved-layouts", "clean")
    rendered = str(late_crash.value)
    assert late_crash.value.scenario == "qualification/saved-layouts/clean"
    assert "status 70" in rendered
    assert "before the next request" in rendered
    assert "qualification/saved-layouts/late-success" in rendered
    assert f"request {late_id}" in rendered
    assert worker._proc is None

    recovered = _qualification_request(worker, "saved-layouts", "clean")
    process_c = worker._proc
    assert process_c is not None and process_c.pid not in {process_a.pid, process_b.pid}
    assert recovered["id"] == late_id + 2
    assert fatal_id < late_id
    assert recovered["cleanup"] == ZERO_CLEANUP

    node = shutil.which("node")
    assert node is not None
    oversized_worker = NodeScenarioWorker(
        [
            node,
            str(WORKER),
            "--worker",
            "saved-layouts",
            str(WEB),
            str(qualification_inputs.manifest_for("saved-layouts")),
        ],
        cwd=ROOT,
    )
    try:
        oversized_worker._ensure_started(
            "qualification/saved-layouts/hostile-oversized-serialization"
        )
        oversized_process = oversized_worker._proc
        assert oversized_process is not None
        with pytest.raises(NodeScenarioCrash) as oversized:
            _qualification_request(
                oversized_worker,
                "saved-layouts",
                "hostile-oversized-serialization",
            )
        assert oversized.value.reply is None
        assert "failure serialization exceeded boundary" in str(oversized.value)
        assert oversized_worker._proc is None
        stderr_lines = oversized.value.stderr.splitlines()
        assert len(stderr_lines) <= 40
        assert all(len(line) <= 400 for line in stderr_lines)
        oversized_recovery = _qualification_request(
            oversized_worker, "saved-layouts", "clean"
        )
        assert oversized_worker._proc is not None
        assert oversized_worker._proc.pid != oversized_process.pid
        assert oversized_recovery["cleanup"] == ZERO_CLEANUP
    finally:
        oversized_worker.close()

    _record_qualification(request, worker_starts=3, fsync_calls=0)


def test_saved_layout_receipt_is_durable_and_detached(tmp_path_factory, request):
    evidence = _saved_layout_receipt_once(tmp_path_factory, request.session)
    alias, remove_alias = _load_bare_saved_layout_module()
    try:
        alias_provider = getattr(alias, "_saved_layout_receipt_once")
        for providers in (
            (_saved_layout_receipt_once, alias_provider),
            (alias_provider, _saved_layout_receipt_once),
        ):
            values = [
                provider(tmp_path_factory, request.session) for provider in providers
            ]
            assert values == [evidence, evidence]
            assert values[0] is values[1] is evidence
            assert _saved_layout_receipt_build_count(request.session) == 1
            assert _saved_layout_receipt_cleanup_registered(request.session)
    finally:
        if remove_alias:
            sys.modules.pop("test_preview_savedlayouts_page", None)
    assert evidence.receipt_bytes == evidence.receipt_json.encode("utf-8")
    receipt = json.loads(evidence.receipt_json)
    assert isinstance(receipt, dict) and receipt is not evidence, (
        "stage-b qualification receipt: detachment violated"
    )
    expected_keys = (
        "initial",
        "hidden",
        "both",
        "visible",
        "bulk",
        "pending",
        "refused",
        "retry",
        "created",
        "duplicate",
        "stale",
        "updated",
        "renamed",
        "removed",
        "size_ack",
        "geometry_apply",
        "newer_geometry",
        "newer_copy",
        "newer_reset",
        "failed_save",
        "incomplete",
        "unavailable",
    )
    assert tuple(receipt) == expected_keys == evidence.keys
    _assert_finite_json(receipt)
    _assert_finite_json(json.loads(evidence.durable_json))
    assert evidence.fsync_calls == 19

    created = receipt["created"]["state"]["layouts"][0]
    updated = receipt["updated"]["state"]["layouts"][0]
    renamed = receipt["renamed"]["state"]["layouts"][0]
    _assert_mutation(
        created["id"] == evidence.created_id
        and len(created["id"]) == 32
        and all(character in "0123456789abcdef" for character in created["id"]),
        "identity",
    )
    assert created["revision"] == evidence.created_revision
    assert updated["id"] == created["id"]
    assert updated["revision"] == evidence.updated_revision
    assert renamed["id"] == created["id"]
    assert renamed["revision"] == evidence.renamed_revision
    assert len({created["revision"], updated["revision"], renamed["revision"]}) == 3
    assert evidence.pending_action == "apply"
    _assert_mutation(evidence.pending_was_true is True, "pending")
    durable = json.loads(evidence.durable_json)
    _assert_mutation(durable["preview"]["layouts"] == {}, "durable")

    decodes = [json.loads(evidence.receipt_json) for _ in range(55)]
    decodes[0]["initial"]["characters"].append("Python poison")
    assert all(
        "Python poison" not in decoded["initial"]["characters"]
        for decoded in decodes[1:]
    )
    assert len({id(decoded) for decoded in decodes}) == 55
    _record_qualification(request, worker_starts=0, fsync_calls=0)
