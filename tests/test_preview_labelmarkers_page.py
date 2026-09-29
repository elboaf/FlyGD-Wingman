"""Execute production Preview listeners, not a second page implementation."""

import json
import os
import shutil
from pathlib import Path

import pytest

from tests.html_tree import PageTree
from tests.node_scenario_worker import NodeScenarioFailure, NodeScenarioWorker
from wingman.preview.labelmarkers import marker_choices

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "wingman/web"
MARKER_DEFERRED_SENTINEL = "stage-b mutation marker-deferred-roster"
ZERO_CLEANUP = {
    "host_timer_handles": 0,
    "host_callbacks": 0,
    "active_rejection_listeners": 0,
    "pending_rejection_records": 0,
    "retained_realms": 0,
}


def _family_worker_fixture(
    tmp_path_factory: pytest.TempPathFactory,
    family: str,
    pages: dict[str, object],
):
    manifest = tmp_path_factory.mktemp(f"{family}-page-worker") / "manifest.json"
    manifest.write_text(
        json.dumps(
            {"version": 1, "pages": pages},
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
            family,
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
def labelmarkers_page_worker(tmp_path_factory: pytest.TempPathFactory):
    tree = PageTree()
    tree.feed((WEB / "index.html").read_text(encoding="utf-8"))
    yield from _family_worker_fixture(
        tmp_path_factory, "label-markers", {"structural": tree.root}
    )


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
        assert calls == 0
        request.node.user_properties.append(("stage_b.direct_fsync_calls", "0"))


def _record_labelmarkers_worker(
    request: pytest.FixtureRequest,
    worker: NodeScenarioWorker,
    reply: dict[str, object],
) -> None:
    process = worker._proc
    assert process is not None and process.pid > 0
    request.node.user_properties.extend(
        (
            ("stage_b.worker_family", "label-markers"),
            ("stage_b.worker_pid", str(process.pid)),
            ("stage_b.worker_request", str(reply["id"])),
        )
    )


@pytest.mark.parametrize(
    "scenario",
    [
        "hydration",
        "receipts",
        "owners",
        "retention",
        "exclusions",
        "refresh",
        "navigation",
        "screenshot",
        "copy",
        "reset-copy",
        "reset-draft",
        "reset-headings",
        "reset-headings-off",
        "reset-capture",
        "reset-owner-capture",
        "capture-entry-pointer",
        "capture-entry-focus",
        "capture-entry-pointer-deferred",
        "capture-entry-focus-deferred",
        "capture-entry-before-arm",
        "screenshot-deferred",
    ],
)
def test_marker_page_ownership(labelmarkers_page_worker, request, scenario):
    choices = json.loads(
        json.dumps(marker_choices(), ensure_ascii=False, allow_nan=False)
    )
    try:
        reply = labelmarkers_page_worker.request(
            f"preview-label-markers/page/{scenario}",
            {
                "protocol": "label-markers",
                "input": {
                    "scenario": scenario,
                    "page": "structural",
                    "choices": choices,
                },
            },
            timeout=30.0,
        )
    except NodeScenarioFailure as error:
        if MARKER_DEFERRED_SENTINEL in str(error):
            raise AssertionError(MARKER_DEFERRED_SENTINEL) from None
        raise
    assert reply["output"] == f"PASS marker page {scenario}"
    assert reply["diagnostics"] == []
    assert reply["cleanup"] == ZERO_CLEANUP
    _record_labelmarkers_worker(request, labelmarkers_page_worker, reply)
