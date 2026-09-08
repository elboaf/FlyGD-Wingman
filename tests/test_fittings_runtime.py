"""Execute Fittings draft/result behavior, not browser layout or native focus."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not on PATH")
def test_fittings_runtime():
    result = subprocess.run(
        ["node", "--test", str(ROOT / "scripts" / "test_fittings_runtime.js")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
