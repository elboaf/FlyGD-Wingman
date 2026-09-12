"""Deferred-ack regressions execute settings.js listeners, not source regexes."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.html_tree import PageTree

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not on PATH")
@pytest.mark.parametrize(
    "script", ["test_settings_runtime.js", "test_settings_tabs_runtime.js"]
)
def test_settings_acknowledgements_preserve_committed_values_and_newer_edits(script):
    tree = PageTree()
    tree.feed((ROOT / "wingman/web/index.html").read_text(encoding="utf-8"))
    result = subprocess.run(
        ["node", str(ROOT / "scripts" / script)],
        input=json.dumps(tree.root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
