"""Wanderer Settings ownership runs under Node; markup checks are not a render."""

import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "wingman" / "web"


def test_wanderer_runtime():
    node = shutil.which("node")
    assert node, "Node is required for Wanderer response-ownership coverage"
    run = subprocess.run(
        [node, str(ROOT / "scripts" / "test_wanderer_runtime.js")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    assert "0 failed" in run.stdout


def test_wanderer_dev_fixtures_keep_credentials_presence_only_and_test_independent():
    node = shutil.which("node")
    assert node, "Node is required for the Wanderer dev contract"
    script = r"""
const fs = require('node:fs'), vm = require('node:vm');
const source = fs.readFileSync(process.argv[1], 'utf8');
const api = {}, pushes = [];
const context = {api, Promise, devSearch: new URLSearchParams(),
  window: {onWandererState: p => pushes.push(p)}, setTimeout: fn => fn()};
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('  // Wanderer dev connection'),
  source.indexOf('  var sharingOrder =')), context);
(async () => {
  const scenarios = {};
  for (const kind of ['off', 'setup', 'connecting', 'connected', 'no-tracked',
    'auth', 'wrong-map', 'api-disabled', 'retrying', 'stale', 'failed-save']) {
    context.wandererScenario(kind);
    scenarios[kind] = await api.wanderer_state();
  }
  const failed = await api.set_wanderer_url('https://refused.example');
  context.wandererScenario('connected');
  const removed = await api.remove_wanderer_connection();
  const changed = await api.set_wanderer_map('new-map');
  const bound = await api.replace_wanderer_token(String.fromCharCode(120),
    'https://wanderer.example', 'wrong-map');
  const replaced = await api.replace_wanderer_token(String.fromCharCode(120),
    'https://wanderer.example', 'new-map');
  await api.set_wanderer_enabled(false);
  const admitted = await api.test_wanderer_connection();
  const after = await api.wanderer_state();
  console.log(JSON.stringify({scenarios, failed, removed, changed, bound, replaced,
    admitted, after, pushes}));
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
    run = subprocess.run(
        [node, "-e", script, str(WEB / "dev.js")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
        check=False,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    data = json.loads(run.stdout)
    assert set(data["scenarios"]["off"]) == {
        "enabled",
        "base_url",
        "map_identifier",
        "revision",
        "credential_present",
        "credential_error",
        "generation",
        "automatic_ready",
        "status",
        "error_code",
        "paused",
        "in_flight",
        "test_pending",
        "test_in_flight",
        "test_result",
        "last_success_monotonic",
        "next_request_monotonic",
        "previewed",
        "matched",
        "available",
        "stale",
        "previews_enabled",
        "host_available",
        "status_text",
        "test_result_text",
    }
    assert data["scenarios"]["off"]["enabled"] is False
    assert data["scenarios"]["stale"]["available"] == 0
    assert data["scenarios"]["no-tracked"]["matched"] == 0
    assert data["failed"]["applied"] is False
    assert data["removed"]["acknowledged"]["credential_present"] is False
    assert data["changed"]["acknowledged"]["credential_present"] is False
    assert data["bound"]["applied"] is False
    assert data["replaced"]["acknowledged"]["credential_present"] is True
    assert data["admitted"]["applied"] is True
    assert data["after"]["enabled"] is False
    assert data["after"]["test_result"] == "success"
    assert any(p["test_pending"] for p in data["pushes"])
    assert any(p["test_in_flight"] for p in data["pushes"])
    assert '"token":' not in run.stdout


def test_wanderer_card_is_in_previews_with_accessible_safe_controls():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    previews = html.split('id="section-previews"', 1)[1].split('id="section-fleet"', 1)[
        0
    ]
    assert 'id="wanderer-settings"' in previews
    assert re.search(r"<h2[^>]*>Wanderer names</h2>", previews)
    assert re.search(r'id="wanderer-remove"[^>]*>Remove connection</button>', previews)
    for field in ("url", "map", "token"):
        assert f'for="wanderer-{field}"' in previews
        assert f'id="wanderer-{field}-apply"' in previews
        assert f'aria-describedby="wanderer-{field}' in previews
    token = re.search(r'<input[^>]*id="wanderer-token"[^>]*>', previews)
    assert token
    assert 'type="password"' in token[0]
    assert 'autocomplete="new-password"' in token[0]
    assert "value=" not in token[0]
    assert re.search(
        r'<label class="check">\s*<input[^>]*id="wanderer-enabled"[^>]*>'
        r'<span class="box">',
        previews,
    )
    assert re.search(r'id="wanderer-health"[^>]*role="status"', previews)
    scripts = re.findall(r'<script src="([^"]+)"', html)
    assert scripts[scripts.index("previews.js") + 1] == "wanderer.js"


def test_wanderer_owns_its_literal_bridge_and_no_other_settings_inputs():
    source = (WEB / "wanderer.js").read_text(encoding="utf-8")
    assert re.findall(r"WM\.handle\('([^']+)'", source) == ["onWandererState"]
    assert set(re.findall(r"WM\.send\('([^']+)'", source)) == {
        "wanderer_state",
        "set_wanderer_enabled",
        "set_wanderer_url",
        "set_wanderer_map",
        "replace_wanderer_token",
        "test_wanderer_connection",
        "remove_wanderer_connection",
    }
    assert "innerHTML" not in source
    assert not re.search(r"\b(?:let|const)\s|=>|`", re.sub(r"//[^\n]*", "", source))
