"""Run the actual editor module/markup; DOM mechanics are not layout evidence."""

import json
import os
import random
import shutil
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

from tests.html_tree import PageTree
from tests.node_scenario_worker import NodeScenarioFailure, NodeScenarioWorker

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "wingman" / "web"
SCENARIOS = [
    "commit-keeps-newer-edit",
    "ignored-read-keeps-baseline",
    "old-completion-ignored",
    "second-save-retained-draft",
    "start-reply-after-completion",
    "failed-switch",
    "account-context",
    "preview-key-separation",
    "preview-origin-scale",
    "preview-fractional-scale",
    "preview-empty-scale",
    "preview-import-key",
    "preview-rotation",
    "switch-edit",
    "stale-read-route",
    "stale-read-attempt",
    "stale-read-error",
    "reload-cancel-fail-success",
    "reload-edit",
    "stale-save-editable",
    "start-refusal",
    "request-identity",
    "back-dirty",
    "paste-cancel-draft",
    "paste-batch",
    "paste-empty",
    "paste-invalid-destination",
    "paste-conflict",
    "paste-unicode-name",
    "paste-invalid-text",
    "paste-byte-limit",
    "paste-invalid-renames",
    "paste-text-during-parse",
    "paste-name-during-add",
    "paste-text-during-add",
    "paste-new-target-conflict",
    "paste-draft-during-add",
    "paste-route-during-parse",
    "paste-route-during-add",
    "paste-account-during-parse",
    "paste-account-during-add",
    "paste-reopen-during-add",
    "paste-cancel-during-add",
    "paste-double-add",
    "paste-rejected-parse",
    "paste-rejected-add",
    "paste-range-cycles",
    "copy-draft-selection",
    "copy-selection-identity",
    "copy-selection-replacement",
    "copy-empty-limits",
    "copy-busy-recovery",
    "copy-denied",
    "copy-throws",
    "copy-missing-clipboard",
    "copy-bridge-error",
    "copy-bridge-rejection",
    "copy-bridge-empty",
    "copy-repeated-bridge",
    "copy-repeated-clipboard",
    "copy-stale-account",
    "copy-stale-route",
    "copy-stale-bridge-error",
    "copy-stale-bridge-rejection",
    "copy-stale-clipboard-success",
    "copy-stale-clipboard-denied",
    "copy-typing-keeps-input",
    "copy-rename-retains-controls",
    "stale-confirm-back",
    "stale-confirm-switch",
    "stale-confirm-reload",
    "delete-during-reload",
    "delete-during-save-reread",
    "delete-after-exit",
    "delete-after-reopen",
    "delete-selection-changed",
    "delete-live-during-save",
    "typing-name-before-completion",
    "typing-name-during-reread",
    "typing-x-before-completion",
    "typing-x-during-reread",
    "typing-y-before-completion",
    "typing-y-during-reread",
    "typing-z-before-completion",
    "typing-z-during-reread",
]

# Exhaustive order comparisons were useful migration evidence but erase the
# worker's PR-time gain. These cases retain cross-branch state-leak coverage.
ORDER_ISOLATION_SCENARIOS = [
    "ignored-read-keeps-baseline",  # Save completion and reread ownership.
    "paste-cancel-draft",  # Real Python parse child plus draft restoration.
    "copy-denied",  # Clipboard rejection and recovery state.
    "delete-live-during-save",  # Delete/save completion ownership.
    "preview-rotation",  # SVG rendering and window event listeners.
]


@pytest.fixture(scope="session")
def formations_page_markup(tmp_path_factory: pytest.TempPathFactory) -> Path:
    page = PageTree()
    page.feed((WEB / "index.html").read_text(encoding="utf-8"))
    path = tmp_path_factory.mktemp("formations-page") / "page.json"
    path.write_text(json.dumps(page.root), encoding="utf-8")
    return path


@pytest.fixture(scope="session")
def formations_worker(formations_page_markup: Path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    worker = NodeScenarioWorker(
        [
            node,
            str(ROOT / "tests/fixtures/formations_page.cjs"),
            str(formations_page_markup),
            str(WEB / "formations.js"),
            sys.executable,
        ],
        cwd=ROOT,
    )
    try:
        yield worker
    finally:
        worker.close()


def test_formations_fixture_yields_without_running_a_business_scenario(
    formations_page_markup: Path,
):
    with contextmanager(formations_worker.__wrapped__)(
        formations_page_markup
    ) as worker:
        assert worker._proc is None


def test_formations_fixture_closes_worker_after_scenario_failure(
    formations_page_markup: Path,
):
    with (
        pytest.raises(NodeScenarioFailure, match="Unknown scenario"),
        contextmanager(formations_worker.__wrapped__)(formations_page_markup) as worker,
    ):
        try:
            worker.request("not-a-formations-scenario", {"env": {}})
        finally:
            process = worker._proc

    assert process is not None and process.poll() is not None
    assert worker._proc is None


def test_formations_worker_protocol_reuses_process_and_isolates_requests(
    formations_worker: NodeScenarioWorker,
):
    first_a = formations_worker.request(
        "commit-keeps-newer-edit", {"env": {}}, timeout=60.0
    )
    process = formations_worker._proc
    middle_b = formations_worker.request(
        "preview-origin-scale", {"env": {}}, timeout=60.0
    )
    second_a = formations_worker.request(
        "commit-keeps-newer-edit", {"env": {}}, timeout=60.0
    )

    assert middle_b["output"] == "PASS preview-origin-scale"
    assert first_a["output"] == second_a["output"] == "PASS commit-keeps-newer-edit"
    assert second_a["id"] == first_a["id"] + 2
    assert formations_worker._proc is process

    unknown = "not-a-formations-scenario"
    with pytest.raises(
        NodeScenarioFailure, match=f"Unknown scenario: {unknown}"
    ) as failure:
        formations_worker.request(unknown, {"env": {}}, timeout=60.0)
    assert failure.value.reply is not None
    assert failure.value.reply["id"] == second_a["id"] + 1
    assert failure.value.reply["scenario"] == unknown
    assert "commit-keeps-newer-edit" not in str(failure.value)
    assert "preview-origin-scale" not in str(failure.value)
    assert formations_worker._proc is process


@pytest.mark.parametrize("failure_mode", ["throw", "reject"])
def test_formations_worker_preserves_vm_error_stack(
    formations_page_markup: Path, tmp_path: Path, failure_mode: str
):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    source = (WEB / "formations.js").read_text(encoding="utf-8")
    module = tmp_path / "formations-vm-error.js"
    trigger = (
        "vmOriginFailure();"
        if failure_mode == "throw"
        else "Promise.resolve().then(vmOriginFailure);"
    )
    module.write_text(
        source
        + "\nfunction vmOriginFailure() { throw new Error('VM-only sentinel'); }\n"
        + trigger,
        encoding="utf-8",
    )
    worker = NodeScenarioWorker(
        [
            node,
            str(ROOT / "tests/fixtures/formations_page.cjs"),
            str(formations_page_markup),
            str(module),
            sys.executable,
        ],
        cwd=ROOT,
    )
    try:
        with pytest.raises(NodeScenarioFailure) as failure:
            worker.request("commit-keeps-newer-edit", {"env": {}})
        assert "vmOriginFailure" in failure.value.stack
        assert "formations-vm-error.js:" in failure.value.stack
        assert failure.value.reply["error"] == "VM-only sentinel"
        process = worker._proc
        module.write_text(source, encoding="utf-8")
        assert worker.request("commit-keeps-newer-edit", {"env": {}})["ok"] is True
        assert worker._proc is process
    finally:
        worker.close()


def test_formations_worker_consumes_encoding_overlay_without_mutating_parent(
    formations_worker: NodeScenarioWorker,
):
    parent_encoding = os.environ.get("PYTHONIOENCODING")
    reply = formations_worker.request(
        "paste-cancel-draft",
        {"env": {"PYTHONIOENCODING": "ascii"}},
        timeout=60.0,
    )

    assert reply["encoding_boundary"] == "ascii"
    assert os.environ.get("PYTHONIOENCODING") == parent_encoding


def test_formations_worker_order_isolation(formations_worker: NodeScenarioWorker):
    def run(order: list[str]) -> dict[str, str]:
        return {
            scenario: formations_worker.request(scenario, {"env": {}}, timeout=60.0)[
                "output"
            ]
            for scenario in order
        }

    forward = run(ORDER_ISOLATION_SCENARIOS)
    process = formations_worker._proc
    reverse = run(list(reversed(ORDER_ISOLATION_SCENARIOS)))
    seed = 20260305
    shuffled = ORDER_ISOLATION_SCENARIOS.copy()
    random.Random(seed).shuffle(shuffled)
    print(f"formations worker isolation seed: {seed}")
    seeded = run(shuffled)
    expected = {scenario: f"PASS {scenario}" for scenario in ORDER_ISOLATION_SCENARIOS}

    assert forward == reverse == seeded == expected
    assert formations_worker._proc is process


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_formation_editor_runtime(formations_worker: NodeScenarioWorker, scenario: str):
    result = formations_worker.request(scenario, {"env": {}}, timeout=60.0)
    assert result["output"] == f"PASS {scenario}"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.parametrize("scenario", ["paste-conflict", "paste-unicode-name"])
def test_unicode_bridge_ignores_locale_encoding(
    formations_worker: NodeScenarioWorker, scenario: str
):
    # Node and its real Python child use explicit UTF-8 buffers even when the
    # child process advertises a Windows code page.
    result = formations_worker.request(
        scenario, {"env": {"PYTHONIOENCODING": "cp1252"}}, timeout=60.0
    )
    assert result["output"] == f"PASS {scenario}"
    assert result["encoding_boundary"] == "cp1252"
