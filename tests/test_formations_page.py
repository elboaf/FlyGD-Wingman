"""Run the actual editor module/markup; DOM mechanics are not layout evidence."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.html_tree import PageTree

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "wingman" / "web"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.parametrize(
    "scenario",
    [
        "commit-keeps-newer-edit",
        "ignored-read-keeps-baseline",
        "old-completion-ignored",
        "second-save-retained-draft",
        "start-reply-after-completion",
        "failed-switch",
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
    ],
)
def test_formation_editor_runtime(tmp_path, scenario):
    page = PageTree()
    page.feed((WEB / "index.html").read_text(encoding="utf-8"))
    markup = tmp_path / "page.json"
    markup.write_text(json.dumps(page.root), encoding="utf-8")
    result = subprocess.run(
        [
            "node",
            str(ROOT / "tests/fixtures/formations_page.cjs"),
            str(markup),
            scenario,
            str(WEB / "formations.js"),
            sys.executable,
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS {scenario}" in result.stdout
