"""Bounded presentation guards; browser geometry is recorded separately.

These rules pin the causes found in the task-8 browser pass, not screenshot
pixels. They do not claim Windows/WebView2 layout or native-operation coverage.
"""

import re
from pathlib import Path

import pytest

from scripts import shoot_screens
from tests.html_tree import PageTree

WEB = Path(__file__).resolve().parents[1] / "wingman" / "web"
HTML = (WEB / "index.html").read_text(encoding="utf-8")
CSS = re.sub(
    r"/\*.*?\*/", "", (WEB / "style.css").read_text(encoding="utf-8"), flags=re.DOTALL
)
FITTINGS = (WEB / "fittings.js").read_text(encoding="utf-8")


def declarations(selector):
    for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", CSS):
        if selector in [s.strip() for s in selectors.split(",")]:
            yield body


def test_inline_companion_radios_do_not_inherit_stacked_margins():
    assert any(
        re.search(r"margin-bottom:\s*0\s*;", rule)
        for rule in declarations(".companion-actions > .radio")
    )
    # Other stacked radio groups retain their intentional vertical spacing.
    assert any("margin-bottom: 8px" in rule for rule in declarations(".radio"))


def test_fitting_metadata_uses_shared_stacked_field_labels():
    block = FITTINGS.split("function metadataFieldsNode(current) {", 1)[1].split(
        "// Free text commits", 1
    )[0]
    assert "var nameRow = WM.make('div', 'row');" in block
    assert "var descRow = WM.make('div', 'row');" in block
    assert "WM.make('label', 'lab', 'Name')" in block
    assert "WM.make('label', 'lab', 'Description')" in block
    row_rules = list(declarations(".fit-metadata > .row"))
    label_rules = list(declarations(".fit-metadata > .row > .lab"))
    assert row_rules and row_rules == list(declarations(".settings .row"))
    assert label_rules and label_rules == list(declarations(".settings .row > .lab"))


def test_skills_plans_reserve_the_same_gutter_in_body_and_header():
    # Like Uploader, both sides must reserve the scrollbar even for short lists.
    # Real READY/ratio edge measurements and the four-row floor are browser checks.
    assert any(
        "scrollbar-gutter: stable" in rule for rule in declarations("#skills-plans")
    )
    assert any(
        "padding-right: calc(8px + var(--scrollbar-w))" in rule
        for rule in declarations("#route-skills .rail-plans-block > .rail-head-row")
    )


def test_groups_scroll_clearance_uses_only_the_two_live_sticky_headers():
    rules = list(declarations(".preview-group-manager"))
    assert any(
        "scroll-margin-top: calc(var(--preview-bind-head-height) * 2)" in rule
        for rule in rules
    )
    assert "--preview-jump-height" not in CSS


def test_backups_actions_header_follows_action_cluster_anchor():
    assert any(
        "text-align: right" in rule
        for rule in declarations(".es-backup-head > :last-child")
    )
    assert any(
        "justify-content: flex-end" in rule for rule in declarations(".bk-actions")
    )


def test_character_management_order_agrees_between_workspaces():
    for manage, refresh in (
        ("skills-manage-characters", "skills-refresh"),
        ("fittings-manage-characters", "fittings-refresh-all"),
    ):
        assert HTML.index('id="' + manage + '"') < HTML.index('id="' + refresh + '"')


def test_fitting_presence_count_says_where_not_readiness():
    assert "meta.push('On ' + row.presence_count" in FITTINGS
    assert "row.presence_count === 1 ? ' character' : ' characters'" in FITTINGS


@pytest.mark.parametrize("presence", ["On 1 character", "On 0 characters"])
def test_copy_capture_staging_tracks_presence_copy(presence):
    # The renderer's wording and the generated read-only stage must agree:
    # otherwise mixed preflight cannot find its present/conflicting fitting.
    setup = shoot_screens._fittings_setup_script("fittings-copy-preflight")
    assert "textContent.indexOf(" + repr(presence) + ") === 0" in setup


def test_formation_import_text_is_compact_but_editable_and_resizable():
    tree = PageTree()
    tree.feed(HTML)

    def nodes(node):
        yield node
        for child in node["children"]:
            yield from nodes(child)

    textarea = next(
        n for n in nodes(tree.root) if n["attrs"].get("id") == "fm-import-text"
    )
    assert textarea["attrs"]["rows"] == "4"
    assert "readonly" not in textarea["attrs"]
    assert "fm-import-save-note" in textarea["attrs"]["aria-describedby"].split()
    assert any("resize: vertical" in rule for rule in declarations("#fm-import-text"))
