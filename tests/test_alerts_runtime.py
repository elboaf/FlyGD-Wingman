"""Execute production Alerts listeners with delayed bridge replies and real IDs."""

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_custom_alert_runtime():
    node = shutil.which("node")
    assert node, "Node is required for custom Alerts runtime acceptance"
    result = subprocess.run(
        [node, str(ROOT / "scripts" / "test_alerts_runtime.js")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
