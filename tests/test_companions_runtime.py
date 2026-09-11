"""Execute companion page bodies with deferred native-operation receipts."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not on PATH")
def test_companion_page_operations_and_drafts():
    result = subprocess.run(
        ["node", str(ROOT / "scripts" / "test_companions_runtime.js")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("scenario", ["empty", "one", "full", "long", "waiting"])
def test_browser_fixtures_are_valid_companion_definitions(scenario):
    from wingman.preview.companions import (
        LABEL_MAX_CHARS,
        MAX_DEFINITIONS,
        MAX_ENABLED,
        TITLE_MAX_CHARS,
        validate_definitions,
    )

    node = shutil.which("node")
    assert node, "Node is required for companion browser fixtures"
    script = r"""
const fs = require('node:fs'), vm = require('node:vm');
const source = fs.readFileSync(process.argv[1], 'utf8');
const api = {}, window = {location: {search: '?companions=' + process.argv[2]}, onCompanionPreviews() {}};
vm.runInNewContext(source.slice(source.indexOf('  var _devCompanionId ='),
  source.indexOf('  // One saved crop per owner.')), {api, window, Promise, setTimeout});
api.companion_previews_state().then(state => console.log(JSON.stringify(state)));
"""
    result = subprocess.run(
        [node, "-e", script, str(ROOT / "wingman" / "web" / "dev.js"), scenario],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    state = json.loads(result.stdout)
    limits = state["limits"]
    assert limits["enabled"] == MAX_ENABLED
    assert limits["definitions"] == MAX_DEFINITIONS
    assert limits["label_max_chars"] == LABEL_MAX_CHARS
    assert limits["title_hint_max_chars"] == TITLE_MAX_CHARS
    assert isinstance(state["operations"], list)
    assert len(validate_definitions(state["rows"])) == len(state["rows"])
    if scenario == "full":
        assert len(state["rows"]) == MAX_DEFINITIONS
        assert sum(row["enabled"] for row in state["rows"]) == MAX_ENABLED
