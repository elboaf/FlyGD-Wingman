"""Run real Fleet handlers with deferred bridge replies and DOM measurements.

Node checks creation identity and continuation ordering, not native visibility,
CSS layout, or Windows/WebView2 behavior.
"""

import os
import shutil
import subprocess
from importlib.metadata import distribution
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_fleetbar_runtime():
    assert shutil.which("node"), "Node is a required verification prerequisite"
    customize = distribution("pywebview").locate_file("webview/js/customize.js")
    assert customize.is_file(), "Installed pywebview customize.js is required"
    result = subprocess.run(
        ["node", "--test", str(ROOT / "scripts" / "test_fleetbar_runtime.js")],
        env={**os.environ, "WINGMAN_PYWEBVIEW_CUSTOMIZE": str(customize)},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
