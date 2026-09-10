"""Execute behavioral and work-bound regressions for the screenshot test DOM."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_screenshot_dom_selectors_and_live_traversal():
    result = subprocess.run(
        ["node", str(ROOT / "tests/fixtures/screenshot_dom.test.cjs")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
