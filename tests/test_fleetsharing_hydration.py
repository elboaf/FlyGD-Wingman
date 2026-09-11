"""Actual missing-owner API replies through app.js and sharing's watch continuation."""

import json
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from tests.fleetsharing_capacity_helpers import maximal_state
from tests.html_tree import PageTree
from tests.test_api import make_state
from tests.test_api_fleetsharing import setup
from tests.test_fleetsharing_worker import UUID, drive
from wingman import settings
from wingman.ui.api import Api

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "wingman/web"


class SharingPageTree(PageTree):
    def handle_data(self, data):
        node = self.stack[-1]
        node["text"] = node.get("text", "") + data


def test_missing_worker_watch_returns_unavailable_without_startup(
    tmp_path, monkeypatch
):
    api = Api(make_state(tmp_path, **settings.load()))

    def forbidden(*args, **kwargs):
        pytest.fail("Unavailable hydration must not start or mutate anything")

    monkeypatch.setattr(api, "_start_fleet_sharing", forbidden)
    monkeypatch.setattr(api, "_reconcile_eve_runtime", forbidden)
    monkeypatch.setattr(settings, "save", forbidden)
    try:
        reply = api.fleet_sharing_watch(True)
        assert reply["queued"] is False
        assert reply["state"]["available"] is False
        assert reply["state"]["enabled"] is False
        assert reply["state"]["metadata"]["loaded"] is False
        assert api._sharing_section_open is False
        assert api._sharing_timer is None
    finally:
        assert api.shutdown_fleet_sharing()


@pytest.mark.parametrize(
    "scenario",
    [
        "missing-worker",
        "null",
        "error-no-state",
        "reject",
        "leave",
        "reenter",
        "newer-push",
        "stale-state",
        "failed-refresh-during-on",
        "rejected-admission",
        "mixed-history",
        "ended-only",
        "ended-prerequisites",
        "pending-precedence",
        "local-results",
        "retained-unknown",
        "failed-refresh-history",
        "binding-invalidation",
        "inflight-stop",
        "bridge-source-rejection",
        "inflight-start-leave",
        "inflight-binding-reply",
        "stable-history-focus",
        "visibility-ownership",
        "retained-local-result",
        "concurrent-stop-replies",
        "inflight-reenter",
        "stale-preference-after-failed-refresh",
        "equal-preference-after-failed-refresh",
        "boss-selection-across-unknown",
    ],
)
def test_sharing_watch_runtime(tmp_path, scenario):
    assert shutil.which("node"), "Node is mandatory for the sharing continuation tests"
    api = Api(make_state(tmp_path, **settings.load()))
    live_api, worker, _client, _store, mono, _timers = setup(tmp_path)
    try:
        older = live_api.fleet_sharing_state()
        rejected = None
        if scenario == "rejected-admission":
            _store._state = replace(
                _store._state,
                pending_source_commands=maximal_state().pending_source_commands[:200],
            )
            rejected = worker.request_source_start(1, UUID)
        worker.set_source_watch(True)
        drive(worker, mono, 12)
        page = SharingPageTree()
        page.feed((WEB / "index.html").read_text(encoding="utf-8"))
        fixture = tmp_path / "sharing-page.json"
        fixture.write_text(
            json.dumps(
                {
                    "page": page.root,
                    "missing": api.fleet_sharing_watch(True),
                    "live": live_api.fleet_sharing_state(),
                    "older": older,
                    "rejected": rejected,
                }
            ),
            encoding="utf-8",
        )
        result = subprocess.run(
            [
                "node",
                str(ROOT / "tests/fixtures/fleetsharing_page.cjs"),
                str(fixture),
                scenario,
                str(WEB),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert f"PASS {scenario}" in result.stdout
    finally:
        assert live_api.shutdown_fleet_sharing()
        assert api.shutdown_fleet_sharing()
