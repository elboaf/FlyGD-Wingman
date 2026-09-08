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
    "import-unavailable",
    "singular-counts",
    "copy-throws",
    "copy-late-denial",
    "save-rejected",
    "late-context",
    "unavailable-pairs",
]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_setup_export_runtime(tmp_path, monkeypatch, scenario):
    if scenario == "unicode-locale":
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
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS {scenario}" in result.stdout
