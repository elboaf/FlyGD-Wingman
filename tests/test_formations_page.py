"""Run the actual editor module/markup; DOM mechanics are not layout evidence."""

import json
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "wingman" / "web"


class _PageTree(HTMLParser):
    def __init__(self):
        super().__init__()
        self.root = {"tag": "document", "attrs": {}, "children": []}
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = {"tag": tag, "attrs": dict(attrs), "children": []}
        self.stack[-1]["children"].append(node)
        if tag not in {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index]["tag"] == tag:
                del self.stack[index:]
                return


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.parametrize(
    "scenario",
    [
        "commit-keeps-newer-edit",
        "ignored-read-keeps-baseline",
        "old-completion-ignored",
        "second-save-retained-draft",
        "start-reply-after-completion",
        "failed-switch",
        "switch-edit",
        "stale-read-route",
        "stale-read-attempt",
        "stale-read-error",
        "reload-cancel-fail-success",
        "reload-edit",
        "stale-save-editable",
        "start-refusal",
        "request-identity",
        "back-dirty",
        "stale-confirm-back",
        "stale-confirm-switch",
        "stale-confirm-reload",
    ],
)
def test_formation_editor_runtime(tmp_path, scenario):
    page = _PageTree()
    page.feed((WEB / "index.html").read_text(encoding="utf-8"))
    markup = tmp_path / "page.json"
    markup.write_text(json.dumps(page.root), encoding="utf-8")
    result = subprocess.run(
        [
            "node",
            str(ROOT / "tests/fixtures/formations_page.cjs"),
            str(markup),
            scenario,
            str(WEB / "formations.js"),
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS {scenario}" in result.stdout
