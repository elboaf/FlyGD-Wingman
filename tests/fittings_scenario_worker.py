from __future__ import annotations

import json
import shutil
from collections.abc import Mapping
from pathlib import Path

import pytest

from tests.html_tree import PageTree
from tests.node_scenario_worker import NodeScenarioWorker

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "wingman" / "web"


def create_fittings_worker(
    tmp_path_factory: pytest.TempPathFactory,
) -> NodeScenarioWorker:
    node = shutil.which("node")
    assert node is not None, "node is not installed"
    tree = PageTree()
    tree.feed((WEB / "index.html").read_text(encoding="utf-8"))
    markup = tmp_path_factory.mktemp("fittings-worker") / "page.json"
    markup.write_text(json.dumps(tree.root, ensure_ascii=False), encoding="utf-8")
    return NodeScenarioWorker(
        [
            node,
            str(ROOT / "tests/fixtures/fittings_page.cjs"),
            str(markup),
            str(WEB / "fittings.js"),
            str(WEB / "panel.js"),
        ],
        cwd=ROOT,
    )


def request_fittings_scenario(
    worker: NodeScenarioWorker,
    scenario: str,
    *,
    screenshot: Mapping[str, object] | None = None,
) -> dict[str, object]:
    return worker.request(
        scenario,
        {"screenshot": screenshot},
        timeout=15.0,
    )
