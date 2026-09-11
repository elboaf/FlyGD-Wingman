"""Real section and capture owners against markup; no rendering/native claims."""

import json
import shutil
import subprocess
from pathlib import Path

from tests.html_tree import PageTree
from tests.test_api import make_state
from wingman import settings
from wingman.ui.api import Api

ROOT = Path(__file__).resolve().parents[1]


def test_fleet_navigation_releases_capture_without_writing_binds(tmp_path):
    assert shutil.which("node"), "Node is mandatory for navigation regression coverage"
    api = Api(make_state(tmp_path, **settings.load()))
    try:
        tree = PageTree()
        tree.feed((ROOT / "wingman/web/index.html").read_text(encoding="utf-8"))
        fixture = tmp_path / "fleet-navigation.json"
        fixture.write_text(
            json.dumps(
                {
                    "page": tree.root,
                    "bookmarks": api.get_bookmarks(),
                    "previews": api.get_preview_hotkey_state(),
                }
            ),
            encoding="utf-8",
        )
        result = subprocess.run(
            [
                "node",
                str(ROOT / "tests/fixtures/fleet_navigation.cjs"),
                str(fixture),
                str(ROOT / "wingman/web"),
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
    finally:
        api.shutdown_fleet_sharing()
