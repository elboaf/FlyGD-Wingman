"""Execute the complete Fleet Settings/status-strip owner, fleet.js, under Node."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not on PATH")
def test_previews_fleet_bar_runtime():
    result = subprocess.run(
        ["node", str(ROOT / "scripts" / "test_previews_fleetbar_runtime.js")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
