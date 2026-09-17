"""Bookmark presentation and capture keep the real page's owners and markup."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.html_tree import TextPageTree

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "wingman/web"


def _tree():
    tree = TextPageTree()
    tree.feed((WEB / "index.html").read_text(encoding="utf-8"))
    return tree.root


def _walk(node):
    yield node
    for child in node["children"]:
        yield from _walk(child)


def _by_id(root, name):
    return next(node for node in _walk(root) if node["attrs"].get("id") == name)


def _has(root, name):
    return any(node["attrs"].get("id") == name for node in _walk(root))


def test_bookmark_status_and_refresh_stay_with_their_owners():
    tree = _tree()
    section = _by_id(tree, "section-bookmarks")
    runtime = next(
        node
        for node in _walk(section)
        if "bookmark-runtime" in node["attrs"].get("class", "").split()
    )
    assert _has(runtime, "eve-enabled") and _has(runtime, "eve-engine-row")
    status = _by_id(runtime, "eve-engine-state")
    assert status["attrs"]["role"] == "status"
    assert status["attrs"]["aria-live"] == "polite"
    assert (
        sum(node["attrs"].get("id") == "eve-engine-state" for node in _walk(tree)) == 1
    )
    header = next(
        node
        for node in _walk(section)
        if node["tag"] == "header" and _has(node, "eve-refresh-windows")
    )
    assert any(
        node["tag"] == "h2" and "EVE windows" in node.get("text", "")
        for node in _walk(header)
    )
    sig = _by_id(tree, "btn-sigbar")
    assert sig["text"].strip() == "SIG"
    assert sig["attrs"]["aria-label"] == sig["attrs"]["title"] == "Floating sig bar"
    assert sig["attrs"]["aria-pressed"] == "false"


def test_preview_windows_uses_local_units_without_changing_disclosure_ownership():
    tree = _tree()
    windows = _by_id(tree, "settings-previews-windows")
    for group, open_by_default in (
        ("appearance", True),
        ("placement", True),
        ("size", False),
        ("switching", False),
    ):
        disclosure = _by_id(windows, "preview-group-" + group)
        assert disclosure["tag"] == "details"
        assert ("open" in disclosure["attrs"]) == open_by_default
    assert not _has(windows, "preview-enabled"), "master stays outside the scroller"
    units = [
        node
        for node in _walk(windows)
        if "preview-option-unit" in node["attrs"].get("class", "").split()
    ]
    for control, helper in (
        ("preview-show-system-names", "preview-show-system-names-status"),
        ("preview-opacity", "preview-opacity-status"),
        ("preview-default-size", "preview-default-size-status"),
        ("btn-preview-apply-size", "preview-apply-size-status"),
    ):
        assert any(_has(unit, control) and _has(unit, helper) for unit in units)
    assert not any(
        _has(unit, "preview-label-size") and _has(unit, "preview-opacity")
        for unit in units
    )
    assert not any(
        _has(unit, "preview-default-size") and _has(unit, "preview-selection-color")
        for unit in units
    )


def test_preview_layout_packs_controls_without_new_scroll_owners():
    css = (WEB / "style.css").read_text(encoding="utf-8")
    assert "grid-template-columns: minmax(200px, 260px)" in css
    header = re.search(r"\.cycle-group-panel > \.cycle-group-head\s*\{([^}]*)\}", css)
    assert header and "position: sticky" in header[1] and "top: 0" in header[1]
    assert "background: var(--panel)" in header[1]
    assert "0 -1px var(--panel)" in header[1]
    for selector in (r"\.cycle-group-chords", r"\.preview-geometry-grid"):
        rule = re.search(selector + r"\s*\{([^}]*)\}", css)
        assert rule and "repeat(2, minmax(0, 1fr))" in rule[1]
        assert "overflow" not in rule[1]
    assert ".preview-character-detail .geometry-actions > .size-none" in css
    assert ".preview-group-manager .group-add-row > .group-add-name" in css
    repair = re.search(r"\.preview-bookmark-conflict > \.linkbtn\s*\{([^}]*)\}", css)
    assert repair and "text-decoration: underline" in repair[1]
    assert "var(--text-btn)" in repair[1]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not on PATH")
def test_bookmark_runtime_status_and_capture():
    result = subprocess.run(
        ["node", str(ROOT / "scripts/test_bookmarks_runtime.js")],
        input=json.dumps(_tree()),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
