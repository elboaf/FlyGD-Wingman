"""Run real Skills handlers with deferred bridge calls and a stateful DOM subset.

Node checks hydration/read/push ordering, not CSS or Windows/WebView2 rendering.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not on PATH")
def test_skills_runtime():
    result = subprocess.run(
        ["node", "--test", str(ROOT / "scripts" / "test_skills_runtime.js")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
