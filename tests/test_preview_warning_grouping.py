"""Warning ownership/order on real Preview DOM, without native or browser calls."""

import json
import subprocess

import pytest

from tests.html_tree import PageTree
from tests.test_new_screenshots import ROOT, shoot


def run_preview_warning_grouping(tmp_path, scenario):
    tree = PageTree()
    tree.feed((ROOT / "wingman/web/index.html").read_text(encoding="utf-8"))
    data = {
        "page": tree.root,
        "fixture": shoot.load_dev_preview_fixture(),
        "scenario": scenario,
        "stage": shoot.screen_setup_script(
            next(
                s for s in shoot.SCREENS if s.key == "settings-previews-sticky-conflict"
            )
        ),
    }
    payload = tmp_path / "preview-grouping.json"
    payload.write_text(json.dumps(data), encoding="utf-8")
    return subprocess.run(
        [
            "node",
            str(ROOT / "tests/fixtures/preview_warning_grouping.cjs"),
            str(payload),
            str(ROOT / "wingman/web"),
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


@pytest.mark.parametrize(
    "scenario",
    [
        "collapsed",
        "expanded",
        "sticky-normal",
        "sticky-missing-row",
        "sticky-wrong-owner",
        "sticky-covered",
        "sticky-bottom-clamp",
        "sticky-outside-scrollport",
    ],
)
def test_preview_warning_grouping_and_sticky_stage(tmp_path, scenario):
    result = run_preview_warning_grouping(tmp_path, scenario)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS preview warning grouping {scenario}" in result.stdout.splitlines(), (
        result.stdout + result.stderr
    )


@pytest.mark.parametrize("scenario", ["not-a-scenario", "sticky-not-a-scenario"])
def test_preview_warning_grouping_rejects_unknown_scenario(tmp_path, scenario):
    result = run_preview_warning_grouping(tmp_path, scenario)
    assert result.returncode != 0, result.stdout + result.stderr
    assert "Unknown preview warning scenario" in result.stderr
    assert "PASS preview warning grouping" not in result.stdout
