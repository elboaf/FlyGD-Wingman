"""The theme card's confirm gate, receipt, and listbox contract execute,
not grep: the same defer-and-acknowledge seam as the settings runtime."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not on PATH")
def test_theme_card_confirm_gate_listbox_contract_and_error_copy():
    result = subprocess.run(
        ["node", str(ROOT / "scripts" / "test_theme_runtime.js")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
