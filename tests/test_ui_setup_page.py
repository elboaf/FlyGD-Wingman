"""Execute the production setup module and PageTree markup, not layout evidence."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.html_tree import PageTree

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
]

CATALOG_SCENARIOS = (
    [
        "catalog-browse-close",
        "catalog-empty-retry",
        "catalog-error-retry",
        "catalog-dialog-escape",
        "catalog-dialog-cancel",
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
    "late-review-error",
    "pending-pair",
    "pending-base",
    "forwarded-completion",
    "import-context-failure",
    "import-late-context",
    "import-limits-failure",
    "yaml-warning-once",
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


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.parametrize("scenario", SCENARIOS + IMPORT_SCENARIOS)
def test_setup_page_runtime(tmp_path, monkeypatch, scenario):
    if scenario in ("unicode-locale", "import-unicode"):
        monkeypatch.setenv("PYTHONIOENCODING", "cp1252")
    page = PageTree()
    page.feed((WEB / "index.html").read_text(encoding="utf-8"))
    markup = tmp_path / "page.json"
    markup.write_text(json.dumps(page.root, ensure_ascii=False), encoding="utf-8")
    result = subprocess.run(
        [
            "node",
            str(ROOT / "tests/fixtures/ui_setup_page.cjs"),
            str(markup),
            scenario,
            str(WEB / "uisetup.js"),
            sys.executable,
            "import" if scenario in IMPORT_SCENARIOS else "export",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS {scenario}" in result.stdout
