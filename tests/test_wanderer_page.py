"""Wanderer Settings ownership runs under Node; markup checks are not a render."""

import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "wingman" / "web"


def test_wanderer_retains_compact_identity_without_pinning_the_whole_form():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    context = re.search(
        r'<header class="scroll-context"[^>]*>(.*?)</header>', html, re.DOTALL
    )
    assert context, "Wanderer needs a bounded local context at the scroll edge"
    assert 'id="wanderer-heading"' in context.group(1)
    assert 'id="wanderer-health"' in context.group(1)
    # Heading and authoritative status stay; editable controls and long feedback
    # must not consume the scrollport or separate the switch from its refusal.
    for field in ("enabled", "coverage", "url", "token", "enabled-error"):
        assert f'id="wanderer-{field}"' not in context.group(1)
    assert html.count('id="wanderer-health"') == 1
    health = re.search(r'<p[^>]*id="wanderer-health"[^>]*>(.*?)</p>', html, re.DOTALL)
    assert health and 'id="wanderer-health-label"' in health[1]
    assert 'class="status-announcement" id="wanderer-health-detail"' in health[1]
    css = (WEB / "style.css").read_text(encoding="utf-8")
    rule = re.search(r"^\.scroll-context\s*\{([^}]*)\}", css, re.MULTILINE)
    assert rule and "position: sticky" in rule.group(1)
    assert "background: var(--panel)" in rule.group(1)
    assert "top: 0" in rule.group(1)
    pane = re.search(r"#settings-previews-wanderer\s*\{([^}]*)\}", css)
    clearance = (
        re.search(r"scroll-padding-top:\s*(\d+)px", pane.group(1)) if pane else None
    )
    assert clearance and int(clearance.group(1)) >= 62 + 4
    announcement = re.search(r"\.status-announcement\s*\{([^}]*)\}", css)
    assert announcement and "position: absolute" in announcement[1]
    assert "clip-path: inset(50%)" in announcement[1]
    assert (
        "display: none" not in announcement[1]
        and "visibility: hidden" not in announcement[1]
    )


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
const start = source.indexOf('  // Wanderer dev connection');
const end = source.indexOf('  var sharingOrder =');
if (start < 0 || end <= start) {
  throw new Error('Wanderer dev fixture markers missing or out of order');
}
vm.createContext(context);
vm.runInContext(source.slice(start, end), context);
(async () => {
  const scenarios = {};
  for (const kind of ['off', 'setup', 'connecting', 'connected', 'no-tracked',
    'auth', 'wrong-map', 'api-disabled', 'retrying', 'stale', 'failed-save']) {
    context.wandererScenario(kind);
    scenarios[kind] = await api.wanderer_state();
  }
  const failed = await api.test_wanderer_connection('https://refused.example/new-map', String.fromCharCode(120));
  context.wandererScenario('connected');
  const revision = (await api.wanderer_state()).revision;
  const staleRemove = await api.remove_wanderer_connection(revision - 1);
  const removed = await api.remove_wanderer_connection(revision);
  const blank = await api.test_wanderer_connection('https://wanderer.example/new-map', '');
  const replaced = await api.test_wanderer_connection('https://wanderer.example/new-map', String.fromCharCode(120));
  const rebound = await api.test_wanderer_connection('https://other.example/new-map', '');
  await api.set_wanderer_enabled(false);
  const admitted = await api.test_wanderer_connection('https://wanderer.example/new-map', '');
  const after = await api.wanderer_state();
  const punctuated = await api.test_wanderer_connection('https://self.example/prefix/Map_1.~', String.fromCharCode(120));
  const sameMap = await api.test_wanderer_connection('https://self.example/prefix/Map_1.~', '');
  const dot = await api.test_wanderer_connection('https://self.example/prefix/.', String.fromCharCode(120));
  const dotdot = await api.test_wanderer_connection('https://self.example/prefix/..', String.fromCharCode(120));
  console.log(JSON.stringify({scenarios, failed, staleRemove, removed, blank, rebound, replaced,
    admitted, after, punctuated, sameMap, dot, dotdot, pushes}));
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
        "persistence_error",
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
    assert data["removed"]["acknowledged"]["base_url"] == ""
    assert data["removed"]["acknowledged"]["map_identifier"] == ""
    assert data["removed"]["acknowledged"]["enabled"] is True
    assert data["staleRemove"]["applied"] is False
    assert data["blank"]["applied"] is False
    assert data["rebound"]["applied"] is False
    assert data["replaced"]["acknowledged"]["credential_present"] is True
    assert data["admitted"]["applied"] is True
    assert data["admitted"]["test_accepted"] is True
    assert data["admitted"]["test_generation"] == data["after"]["generation"]
    assert data["after"]["enabled"] is False
    assert data["after"]["test_result"] == "success"
    assert data["punctuated"]["test_accepted"] is True
    assert (
        data["punctuated"]["acknowledged"]["base_url"] == "https://self.example/prefix"
    )
    assert data["punctuated"]["acknowledged"]["map_identifier"] == "Map_1.~"
    assert data["sameMap"]["test_accepted"] is True
    assert (
        data["sameMap"]["acknowledged"]["revision"]
        == data["punctuated"]["acknowledged"]["revision"]
    )
    for refused in (data["dot"], data["dotdot"]):
        assert refused["applied"] is False
        assert refused["acknowledged"] == data["punctuated"]["acknowledged"]
    assert any(p["test_pending"] for p in data["pushes"])
    assert any(p["test_in_flight"] for p in data["pushes"])
    assert '"token":' not in run.stdout


def test_wanderer_card_is_in_previews_with_accessible_safe_controls():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    previews = html.split('id="section-previews"', 1)[1].split('id="section-fleet"', 1)[
        0
    ]
    assert 'id="wanderer-settings"' in previews
    heading = re.search(r'<h2 id="wanderer-heading">([^<]+)</h2>', previews)
    tab = re.search(
        r'id="settings-tab-previews-wanderer"[^>]*>([^<]+)</button>', previews
    )
    assert heading and tab
    assert heading[1] != tab[1], "Connection heading must not repeat its selected tab"
    assert re.search(r'id="wanderer-remove"[^>]*>Remove connection</button>', previews)
    for field in ("url", "token"):
        assert f'for="wanderer-{field}"' in previews
        assert f'id="wanderer-{field}-apply"' not in previews
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
    assert re.search(r'<p class="operational-status" id="wanderer-health"', previews)
    assert re.search(r'<p class="hint" id="wanderer-coverage"', previews), (
        "Only the combined health/coverage headline is authoritative; recovery is subordinate"
    )
    for state in ("health", "coverage"):
        assert previews.index(f'id="wanderer-{state}"') < previews.index(
            'id="wanderer-url"'
        )
    assert 'id="wanderer-connection-error"' in previews
    assert "saves the map URL and token" in previews
    source = (WEB / "wanderer.js").read_text(encoding="utf-8")
    initial_hint = re.search(r'id="wanderer-token-draft"[^>]*>([^<]+)</p>', previews)
    painted_hint = re.search(r"el\('token-draft'\)\.textContent = '([^']*)';", source)
    assert initial_hint and painted_hint
    assert initial_hint[1] == painted_hint[1]
    scripts = re.findall(r'<script src="([^"]+)"', html)
    assert scripts[scripts.index("previews.js") + 1] == "wanderer.js"


def test_wanderer_owns_its_literal_bridge_and_no_other_settings_inputs():
    source = (WEB / "wanderer.js").read_text(encoding="utf-8")
    assert re.findall(r"WM\.handle\('([^']+)'", source) == ["onWandererState"]
    assert set(re.findall(r"WM\.send\('([^']+)'", source)) == {
        "wanderer_state",
        "set_wanderer_enabled",
        "test_wanderer_connection",
        "remove_wanderer_connection",
    }
    assert "innerHTML" not in source
    assert not re.search(r"\b(?:let|const)\s|=>|`", re.sub(r"//[^\n]*", "", source))
