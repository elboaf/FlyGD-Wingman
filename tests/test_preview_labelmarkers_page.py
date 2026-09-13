"""Execute production Preview listeners, not a second page implementation."""

import json
import subprocess
from pathlib import Path

import pytest

from tests.html_tree import PageTree
from wingman.preview.labelmarkers import marker_choices

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "scenario",
    [
        "hydration",
        "receipts",
        "owners",
        "retention",
        "refresh",
        "navigation",
        "screenshot",
        "copy",
        "reset-copy",
        "reset-draft",
        "reset-headings",
        "reset-headings-off",
        "reset-capture",
        "reset-owner-capture",
        "capture-entry-pointer",
        "capture-entry-focus",
        "capture-entry-pointer-deferred",
        "capture-entry-focus-deferred",
        "capture-entry-before-arm",
        "screenshot-deferred",
    ],
)
def test_marker_page_ownership(tmp_path, scenario):
    tree = PageTree()
    tree.feed((ROOT / "wingman/web/index.html").read_text(encoding="utf-8"))
    data = tmp_path / "markers.json"
    data.write_text(
        json.dumps(
            {"page": tree.root, "choices": marker_choices(), "scenario": scenario}
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            "node",
            str(ROOT / "tests/fixtures/preview_labelmarkers.cjs"),
            str(data),
            str(ROOT / "wingman/web"),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS marker page {scenario}" in result.stdout
