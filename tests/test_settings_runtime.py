"""Deferred-ack regressions execute settings.js listeners, not source regexes."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not on PATH")
def test_settings_acknowledgements_preserve_committed_values_and_newer_edits():
    result = subprocess.run(
        ["node", str(ROOT / "scripts" / "test_settings_runtime.js")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
