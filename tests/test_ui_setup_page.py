"""Execute the production setup module and PageTree markup, not layout evidence."""

import json
import os
import random
import shutil
import sys
from pathlib import Path

import pytest

from tests.html_tree import PageTree
from tests.node_scenario_worker import NodeScenarioFailure, NodeScenarioWorker

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "wingman/web"
SCENARIOS = [
    "twenty-tab-help",
    "export-source-change",
    "export-route-exit",
    "export-reopen",
    "copy-denied",
    "copy-unavailable",
    "copy-late-success",
    "save-cancel",
    "save-failure",
    "unsupported-stack",
    "missing-pair",
    "unicode-locale",
    "export-success",
    "export-review-hierarchy",
    "context-change",
    "context-failure",
    "late-errors",
    "save-late-success",
    "singular-counts",
    "copy-throws",
    "copy-late-denial",
    "save-rejected",
    "late-context",
    "unavailable-pairs",
    "setup-dialog-export-preview",
    "setup-dialog-export-copy",
    "setup-dialog-export-save",
]

CATALOG_SCENARIOS = (
    [
        "catalog-browse-close",
        "catalog-empty-retry",
        "catalog-error-retry",
        "catalog-dialog-escape",
        "catalog-dialog-cancel",
        "catalog-dialog-accept",
        "catalog-dialog-queued-cancel",
        "catalog-dialog-queued-accept",
        "catalog-dialog-queued-ordinary-accept",
        "catalog-dialog-hidden-target",
        "catalog-dialog-invisible-target",
        "catalog-selection-status",
        "catalog-selection-scroll",
        "catalog-list-after-create",
        "catalog-list-rejected",
        "catalog-list-close-reopen",
        "catalog-literal-selection",
        "catalog-failed-entry",
        "catalog-rejected-entry",
        "catalog-use-empty",
        "catalog-replacement",
        "catalog-cancel-replacement",
        "catalog-origin",
        "catalog-selection-aba",
        "catalog-confirm-selection-aba",
    ]
    + [
        f"catalog-{stage}-after-{change}"
        for stage in ("read", "confirm")
        for change in (
            "text",
            "name",
            "base",
            "pair",
            "labels",
            "close",
            "reopen",
            "route",
            "create",
        )
    ]
    + [
        f"catalog-{direction}-{source}"
        for direction in ("supersedes", "superseded-by", "origin-cleared-by")
        for source in ("paste", "file")
    ]
    + [
        f"catalog-dialog-pending-{source}-{answer}"
        for source in ("paste", "file", "review", "labels")
        for answer in ("accept", "cancel", "queued-accept", "queued-cancel")
    ]
    + ["catalog-stale-manual-busy"]
    + [
        "catalog-dev-ordinary",
        "catalog-dev-long",
        "catalog-dev-empty",
        "catalog-dev-error",
        "catalog-dev-entry-error",
    ]
)

IMPORT_SCENARIOS = [
    *CATALOG_SCENARIOS,
    "ux-initial-source-choice",
    "ux-prerequisite-feedback",
    "ux-context-recovery",
    "ux-pair-feedback",
    "ux-catalog-escape",
    "ux-source-change-cancel",
    "ux-source-editor",
    "ux-file-summary",
    "ux-paste-fallback",
    "ux-source-cancel-pending",
    "ux-review-action",
    "ux-catalog-content",
    "context-does-not-select",
    "base-rosters-differ",
    "review-invalidated-by-text",
    "review-invalidated-by-name",
    "review-invalidated-by-pair",
    "review-invalidated-by-base",
    "old-review-after-new",
    "cancel-during-review",
    "cancel-reviewed",
    "yaml-label-choice",
    "yaml-no-layout",
    "stale-manifest",
    "eve-unknown",
    "double-create",
    "start-refused",
    "done-before-accepted",
    "done-before-refused",
    "published-with-warning",
    "route-exit-during-create",
    "old-discard-after-new-review",
    "labels-render-as-text",
    "missing-review-id",
    "review-rejected",
    "file-replaced",
    "file-cancel",
    "file-failure",
    "file-late",
    "paste-denied",
    "paste-late",
    "completion-correlation",
    "create-rejected",
    "edit-during-context",
    "review-blank",
    "keep-invalidates",
    "import-unavailable-pairs",
    "import-unicode",
    "malformed-text",
    "missing-summary",
    "failed-create",
    "setup-dialog-completion-success",
    "setup-dialog-completion-failure",
    "late-review-error",
    "pending-pair",
    "pending-base",
    "forwarded-completion",
    "import-context-failure",
    "import-late-context",
    "import-limits-failure",
    "yaml-warning-once",
    "portable-review-hierarchy",
    "portable-caveat-once",
    "native-no-copied-layout-caveat",
    "review-safety-outside-disclosures",
    "detached-success",
    "detached-failure",
    "detached-warning",
    "detached-warning-fallback",
    "detached-lost-starter",
    "detached-rejected-starter",
    "detached-refused",
    "detached-early-done",
    "detached-newer-review",
    "detached-two-creates",
    "detached-ordinary-copy",
    "detached-other-route",
    "detached-refresh-race",
    "detached-refresh-race-newer-review",
    "detached-refresh-race-ordinary-copy",
    "profiles-refresh-in-order",
    "profiles-refresh-newer-null",
    "profiles-refresh-older-null",
    "profiles-refresh-root-followup",
    "profiles-refresh-roster-followup",
]


class SetupPageTree(PageTree):
    """Retain static copy too: a hidden native caveat cannot be a DOM-double fiction."""

    def handle_data(self, data):
        node = self.stack[-1]
        node["text"] = node.get("text", "") + data


@pytest.fixture(scope="session")
def setup_page_markup(tmp_path_factory: pytest.TempPathFactory) -> Path:
    page = SetupPageTree()
    page.feed((WEB / "index.html").read_text(encoding="utf-8"))
    path = tmp_path_factory.mktemp("setup-page") / "page.json"
    path.write_text(json.dumps(page.root, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture(scope="session")
def setup_page_static_fixtures(tmp_path_factory: pytest.TempPathFactory) -> Path:
    from tests.setup_fixtures import wire
    from wingman.evesettings import setup_model, setup_sharing
    from wingman.evesettings.controller import ProfilesController
    from wingman.ui.api import Api

    def export_reply(label: str) -> dict:
        value = wire()
        value["overview"]["shipLabels"][0]["pre"] = label
        return {
            "ok": True,
            "error": "",
            "text": setup_sharing.export_text(value),
            "summary": setup_model.summarize(setup_model.validate_wingman(value)),
            "warnings": [
                "2 effective unsaved filter definitions override saved definitions "
                "in this snapshot."
            ],
        }

    api = Api.__new__(Api)
    api._profiles = ProfilesController.__new__(ProfilesController)
    native_path = ROOT / "tests/fixtures/ui_setup/native-complete.yaml"
    native_text = native_path.read_text(encoding="utf-8")
    native = setup_sharing.parse_text(native_text)
    fixtures = {
        "scenarios": SCENARIOS + IMPORT_SCENARIOS,
        "limits": api.eve_settings_setup_limits(),
        "exported": export_reply("Étiquette 𐐀 <b>literal</b>"),
        "fresh_export": export_reply("Fresh é 𐐀 <script>"),
        "native": {
            "text": native_text,
            "summary": setup_model.summarize(native),
            "warnings": list(native.warnings),
            "ambiguous": native.ambiguous_labels,
        },
    }
    path = tmp_path_factory.mktemp("setup-page-fixtures") / "fixtures.json"
    path.write_text(json.dumps(fixtures, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture(scope="session")
def setup_page_worker(setup_page_markup: Path, setup_page_static_fixtures: Path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    worker = NodeScenarioWorker(
        [
            node,
            str(ROOT / "tests/fixtures/ui_setup_page.cjs"),
            str(setup_page_markup),
            str(setup_page_static_fixtures),
            str(WEB / "uisetup.js"),
            sys.executable,
        ],
        cwd=ROOT,
    )
    try:
        yield worker
    finally:
        worker.close()


def test_setup_page_worker_protocol_reuses_process_and_correlates_unknown_scenario(
    setup_page_worker: NodeScenarioWorker,
):
    first = setup_page_worker.request(
        "copy-unavailable", {"mode": "export", "env": {}}, timeout=60.0
    )
    process = setup_page_worker._proc
    second = setup_page_worker.request(
        "ux-initial-source-choice", {"mode": "import", "env": {}}, timeout=60.0
    )

    assert first["output"] == "PASS copy-unavailable"
    assert second["output"] == "PASS ux-initial-source-choice"
    assert setup_page_worker._proc is process
    with pytest.raises(NodeScenarioFailure, match="unknown scenario") as failure:
        setup_page_worker.request(
            "not-a-setup-scenario", {"mode": "export", "env": {}}, timeout=60.0
        )
    assert failure.value.reply is not None
    assert failure.value.reply["id"] == second["id"] + 1
    assert failure.value.reply["scenario"] == "not-a-setup-scenario"
    assert setup_page_worker._proc is process


@pytest.mark.parametrize("failure_mode", ["throw", "reject"])
def test_setup_page_worker_preserves_vm_error_stack(
    setup_page_markup: Path,
    setup_page_static_fixtures: Path,
    tmp_path: Path,
    failure_mode: str,
):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    source = (WEB / "uisetup.js").read_text(encoding="utf-8")
    module = tmp_path / "setup-vm-error.js"
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
            str(ROOT / "tests/fixtures/ui_setup_page.cjs"),
            str(setup_page_markup),
            str(setup_page_static_fixtures),
            str(module),
            sys.executable,
        ],
        cwd=ROOT,
    )
    try:
        with pytest.raises(NodeScenarioFailure) as failure:
            worker.request("copy-unavailable", {"mode": "export", "env": {}})
        assert "vmOriginFailure" in failure.value.stack
        assert "setup-vm-error.js:" in failure.value.stack
        assert failure.value.reply["error"] == "VM-only sentinel"
        process = worker._proc
        module.write_text(source, encoding="utf-8")
        assert (
            worker.request("copy-unavailable", {"mode": "export", "env": {}})["ok"]
            is True
        )
        assert worker._proc is process
    finally:
        worker.close()


def test_setup_page_worker_consumes_encoding_overlay_without_mutating_parent(
    setup_page_worker: NodeScenarioWorker,
):
    parent_encoding = os.environ.get("PYTHONIOENCODING")
    ascii_reply = setup_page_worker.request(
        "unicode-locale",
        {"mode": "export", "env": {"PYTHONIOENCODING": "ascii"}},
        timeout=60.0,
    )
    cp1252_export = setup_page_worker.request(
        "unicode-locale",
        {"mode": "export", "env": {"PYTHONIOENCODING": "cp1252"}},
        timeout=60.0,
    )
    cp1252_import = setup_page_worker.request(
        "import-unicode",
        {"mode": "import", "env": {"PYTHONIOENCODING": "cp1252"}},
        timeout=60.0,
    )
    inherited_reply = setup_page_worker.request(
        "unicode-locale", {"mode": "export", "env": {}}, timeout=60.0
    )

    assert ascii_reply["encoding_boundary"] == "ascii"
    assert cp1252_export["encoding_boundary"] == "cp1252"
    assert cp1252_import["encoding_boundary"] == "cp1252"
    assert inherited_reply["encoding_boundary"] == (parent_encoding or "")
    assert os.environ.get("PYTHONIOENCODING") == parent_encoding


def _setup_payload(scenario: str) -> dict:
    return {
        "mode": "import" if scenario in IMPORT_SCENARIOS else "export",
        "env": (
            {"PYTHONIOENCODING": "cp1252"}
            if scenario in {"unicode-locale", "import-unicode"}
            else {}
        ),
    }


def test_setup_page_worker_isolation_sentinel(
    setup_page_worker: NodeScenarioWorker,
):
    first_a = setup_page_worker.request(
        "copy-unavailable", _setup_payload("copy-unavailable"), timeout=60.0
    )
    middle_b = setup_page_worker.request(
        "ux-initial-source-choice",
        _setup_payload("ux-initial-source-choice"),
        timeout=60.0,
    )
    second_a = setup_page_worker.request(
        "copy-unavailable", _setup_payload("copy-unavailable"), timeout=60.0
    )

    assert middle_b["output"] == "PASS ux-initial-source-choice"
    assert first_a["output"] == second_a["output"] == "PASS copy-unavailable"
    assert second_a["id"] == first_a["id"] + 2


@pytest.mark.parametrize("exit_kind", ["success", "failure"])
def test_setup_page_worker_cleanup_before_reply(
    setup_page_worker: NodeScenarioWorker, exit_kind: str
):
    # The fixture probes the real runScenario/finally, not worker.close(), which
    # terminates Node. Both exits leave real page work and a native timer pending.
    # Capture identity before the probe, including when either parameter runs alone.
    warmup = setup_page_worker.request(
        "copy-unavailable", _setup_payload("copy-unavailable")
    )
    assert warmup["output"] == "PASS copy-unavailable"
    process = setup_page_worker._proc
    pid = process.pid
    payload = {**_setup_payload("copy-unavailable"), "cleanup_probe": exit_kind}
    if exit_kind == "failure":
        with pytest.raises(NodeScenarioFailure) as failure:
            setup_page_worker.request("copy-unavailable", payload)
        reply = failure.value.reply
        assert reply is not None
        assert reply["error"] == "cleanup probe failure after pending timer"
    else:
        reply = setup_page_worker.request("copy-unavailable", payload)
        assert reply["output"] == "PASS cleanup probe success"

    assert setup_page_worker._proc is process, (
        "cleanup probe replaced the worker process"
    )
    assert setup_page_worker._proc.pid == pid
    assert reply["id"] == warmup["id"] + 1
    recovered = setup_page_worker.request(
        "copy-unavailable", _setup_payload("copy-unavailable")
    )
    assert recovered["output"] == "PASS copy-unavailable"
    assert recovered["id"] == reply["id"] + 1
    assert setup_page_worker._proc is process
    assert setup_page_worker._proc.pid == pid
    assert process.poll() is None


def test_setup_page_worker_order_isolation(setup_page_worker: NodeScenarioWorker):
    # All business cases still run individually below. Replay only the audited
    # spine: clipboard absence, dev fixture, queued panel, coupled completion,
    # and stale Profiles read. This samples predecessor orders, not every pair.
    # These do not leave timers pending; cleanup is proved separately above.
    scenarios = [
        "copy-unavailable",
        "catalog-dev-ordinary",
        "catalog-dialog-pending-file-queued-accept",
        "detached-ordinary-copy",
        "profiles-refresh-older-null",
    ]
    processes = []

    def run(order: list[str]) -> dict[str, str]:
        results = {}
        for scenario in order:
            results[scenario] = setup_page_worker.request(
                scenario, _setup_payload(scenario), timeout=60.0
            )["output"]
            processes.append(setup_page_worker._proc)
        return results

    seed = 20260304
    print(f"setup page worker isolation seed: {seed}; spine: {scenarios}")
    forward = run(scenarios)
    reverse = run(list(reversed(scenarios)))
    shuffled = scenarios.copy()
    random.Random(seed).shuffle(shuffled)
    seeded = run(shuffled)

    assert forward == reverse == seeded == {name: f"PASS {name}" for name in scenarios}
    assert all(process is processes[0] for process in processes)
    assert len({process.pid for process in processes}) == 1
    assert processes[0].poll() is None


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.parametrize("scenario", SCENARIOS + IMPORT_SCENARIOS)
def test_setup_page_runtime(setup_page_worker: NodeScenarioWorker, scenario: str):
    result = setup_page_worker.request(scenario, _setup_payload(scenario), timeout=60.0)
    assert result["output"] == f"PASS {scenario}"
