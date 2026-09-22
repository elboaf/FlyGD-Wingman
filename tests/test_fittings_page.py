"""Fittings shell contracts and executable copy-control accessibility checks.

The Node DOM double executes the real Fittings module against the page's
markup. It tests keyboard/focus behavior, not browser layout or WebView2's
accessibility tree; those still require the Windows smoke pass.
"""

import re
import shutil
from pathlib import Path

import pytest

from tests.fittings_scenario_worker import request_fittings_scenario
from tests.html_tree import PageTree
from tests.node_scenario_worker import NodeScenarioFailure, NodeScenarioWorker

WEB = Path(__file__).resolve().parent.parent / "wingman" / "web"


HTML = (WEB / "index.html").read_text(encoding="utf-8")
APP_JS = (WEB / "app.js").read_text(encoding="utf-8")
FITTINGS_JS = (WEB / "fittings.js").read_text(encoding="utf-8")
# Comments stripped before any rule parsing, same as test_page_conventions.py:
# a naive selector capture otherwise swallows a leading block comment.
CSS = re.sub(
    r"/\*.*?\*/", "", (WEB / "style.css").read_text(encoding="utf-8"), flags=re.DOTALL
)


def test_copy_context_stays_outside_the_only_body_scroller():
    nodes = fitting_nodes()
    by_id = {node["attrs"].get("id"): node for node in nodes}
    heading = next(
        (n for n in nodes if "fit-copy-heading" in n["attrs"].get("class", "").split()),
        None,
    )
    assert heading, "Copy heading and summaries need one retained opaque surface"
    assert [n["attrs"].get("id") for n in heading["children"]] == [
        "fittings-copy-title",
        "fittings-copy-summary",
        "fittings-copy-limit-summary",
    ]
    dialog = by_id["fittings-copy-dialog"]["children"]
    assert dialog.index(heading) < dialog.index(by_id["fittings-copy-body"])
    assert by_id["fittings-copy-status"] in dialog
    assert by_id["fittings-copy-status"]["attrs"]["role"] == "status"
    assert all(
        "role" not in n["attrs"] and "aria-live" not in n["attrs"]
        for n in heading["children"]
    )
    assert any(by_id["fittings-copy-close"] in n["children"] for n in dialog)


def test_copy_dialog_bounds_its_existing_scroller_without_overlaying_the_footer():
    dialog = fitting_rules("#fittings-copy-dialog")[0]
    for prop in (
        "display: flex",
        "flex-direction: column",
        "max-height: calc(100vh - 48px)",
    ):
        assert prop in dialog
    body = fitting_rules("#fittings-copy-body")[0]
    for prop in (
        "min-height: 0",
        "overflow-y: auto",
        "scroll-padding:",
        "padding: 4px;",
    ):
        assert prop in body
    assert "flex: none" in fitting_rules(".fit-copy-heading")[0]
    assert "background: var(--panel)" in fitting_rules(".fit-copy-heading")[0]
    assert all("overflow-y:" not in rule for rule in fitting_rules(".fit-copy-heading"))
    assert "flex: none" in fitting_rules("#fittings-copy-dialog > .buttons")[0]


def test_copy_pair_identity_is_the_only_row_local_sticky_owner():
    context = fitting_rules(".fit-copy-pair-context")
    assert context, "Pair identity must remain attached while its outcome is visible"
    for prop in ("position: sticky", "top: 0", "background: var(--panel)"):
        assert prop in context[0]
    assert all("position: sticky" not in r for r in fitting_rules(".fit-copy-recovery"))
    assert "flex-direction: column" in fitting_rules(".fit-copy-pair")[0]
    assert (
        "grid-template-columns: minmax(0, 1fr)"
        in fitting_rules(".fit-copy-pair-context")[-1]
    )


@pytest.mark.parametrize(
    "selector",
    [
        "#fittings-copy-summary[hidden]",
        "#fittings-copy-limit-summary[hidden]",
        "#fittings-copy-progress[hidden]",
    ],
)
def test_copy_dynamic_header_and_progress_respect_hidden(selector):
    assert any("display: none" in body for body in fitting_rules(selector))


def test_copy_progress_is_compact_and_not_decoratively_animated():
    rules = fitting_rules("#fittings-copy-progress")
    assert rules
    assert "width: 100%" in rules[0]
    assert "appearance: none" in rules[0], (
        "Native paint must not bypass the token-owned track"
    )
    assert all("animation:" not in r and "transition:" not in r for r in rules)


def test_copy_progress_retains_a_visible_forced_colour_track_and_value():
    assert "forced-color-adjust: none" in fitting_rules("#fittings-copy-progress")[-1]
    assert (
        "var(--fitting-forced-ink)"
        in fitting_rules("#fittings-copy-progress::-webkit-progress-value")[-1]
    )
    assert (
        "var(--fitting-forced-surface)"
        in fitting_rules("#fittings-copy-progress::-webkit-progress-bar")[-1]
    )


def test_copy_technical_disclosure_keeps_support_id_selectable_and_wrapped():
    body = fitting_rules(".fit-copy-technical")
    assert body and "overflow-wrap: anywhere" in body[0]
    assert "user-select: text" in fitting_rules("#fittings-copy-operation-id")[0]
    assert (
        "var(--focus-ring)"
        in fitting_rules(".fit-copy-technical > summary:focus-visible")[0]
    )


def test_copy_native_skip_focus_uses_the_painted_label_bounds():
    assert fitting_rules(".fit-copy-resolution .check"), (
        "Native Skip needs a local focus footprint"
    )
    assert "position: relative" in fitting_rules(".fit-copy-resolution .check")[0]
    assert "inset: 0" in fitting_rules(".fit-copy-resolution .check input")[0]


def test_copy_mirrored_live_status_removes_the_visible_status_spacing():
    rules = fitting_rules("#fittings-copy-status.status-announcement")
    assert rules, (
        "The copy status ID spacing must not expose its screen-reader-only mirror"
    )
    assert "min-height: 0" in rules[0]
    assert "margin: 0" in rules[0]


def test_expanded_fitting_keeps_its_identity_above_the_detail():
    rule = re.search(r"\.fit-row\.open > \.fit-row-top\s*\{([^}]*)\}", CSS)
    assert rule, "Only the expanded fitting needs retained row identity"
    for prop in ("position: sticky", "top: 0", "background: var(--panel)", "z-index:"):
        assert prop in rule.group(1)
    workspace = re.search(r"\.fit-workspace-scroll\s*\{([^}]*)\}", CSS)
    assert workspace and re.search(
        r"scroll-padding-top:\s*var\(--fit-sticky-clearance,\s*44px\)",
        workspace.group(1),
    ), "Wrapped row identity needs measured clearance, with the original fallback"
    assert "'--fit-sticky-clearance'" in FITTINGS_JS
    assert "scroll-padding-bottom: 16px" in workspace.group(1), (
        "Native textarea caret reveal must also clear the full control border"
    )


def fitting_nodes():
    tree = PageTree()
    tree.feed(HTML)

    def walk(node):
        yield node
        for child in node["children"]:
            yield from walk(child)

    return list(walk(tree.root))


def fitting_rules(selector):
    return [
        body
        for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", CSS)
        if selector in [part.strip() for part in selectors.split(",")]
    ]


def test_fitting_visual_header_labels_existing_controls_without_table_roles():
    nodes = fitting_nodes()
    by_id = {node["attrs"].get("id"): node for node in nodes}
    header = by_id.get("fittings-list-head")
    assert header, "The fitting list needs deliberate visual column labels"
    assert header["attrs"].get("aria-hidden") == "true"
    assert "role" not in header["attrs"]
    workspace = by_id["fittings-workspace-scroll"]["children"]
    assert workspace.index(header) < workspace.index(by_id["fittings-list"])
    assert workspace.index(by_id["fittings-import-panel"]) < workspace.index(header)
    assert (
        'role="table"'
        not in HTML.split('id="route-fittings"')[1].split('id="route-firstrun"')[0]
    )


def test_fitting_header_and_rows_share_deliberate_tracks_and_insets():
    for selector in (".fit-list-head", ".fit-row-top"):
        body = fitting_rules(selector)[0]
        assert "grid-template-columns: var(--fit-row-tracks)" in body
        assert "padding: var(--fit-row-padding)" in body
        assert "gap: var(--fit-row-gap)" in body
    route = fitting_rules("#route-fittings")[0]
    assert "--fit-row-tracks:" in route and "--fit-identity-tracks:" in route
    assert (
        "grid-template-columns: var(--fit-identity-tracks)"
        in fitting_rules(".fit-row-toggle")[0]
    )


def test_fitting_selection_helpers_and_primary_share_one_action_area():
    nodes = fitting_nodes()
    by_id = {node["attrs"].get("id"): node for node in nodes}
    parent = next(
        node for node in nodes if by_id["fittings-copy-selected"] in node["children"]
    )
    children = parent["children"]
    assert by_id["fittings-select-page"] in children
    assert by_id["fittings-clear-selection"] in children
    assert [child["attrs"].get("id") for child in children] == [
        "fittings-select-page",
        "fittings-clear-selection",
        "fittings-copy-selected",
    ]
    assert "acc" in by_id["fittings-copy-selected"]["attrs"]["class"].split()
    assert all(
        "acc" not in by_id[id_]["attrs"]["class"].split()
        for id_ in ("fittings-select-page", "fittings-clear-selection")
    )


def test_fitting_details_stack_at_reachable_floor_without_another_scroller():
    detail = fitting_rules(".fit-detail")[0]
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in detail
    assert "grid-template-columns: minmax(0, 1fr)" in fitting_rules(".fit-detail")[-1]
    for selector in (".fit-detail-content", ".fit-detail-management", ".fit-immediate"):
        assert fitting_rules(selector), selector
        assert all("overflow-y:" not in rule for rule in fitting_rules(selector))
    assert "display: none" in fitting_rules(".fit-list-head")[-1]
    assert "grid-column: 2" in fitting_rules(".fit-row-status")[-1]


@pytest.mark.parametrize(
    "selector",
    [
        ".fit-row-toggle:focus-visible",
        ".fit-metadata-disclosure > summary:focus-visible",
    ],
)
def test_fitting_native_expanders_use_the_shared_focus_token(selector):
    assert any("var(--focus-ring)" in body for body in fitting_rules(selector))


def test_detail_module_wrapping_does_not_restyle_shared_clipboard_review():
    assert all("flex:" not in rule for rule in fitting_rules(".fit-item-qty"))
    assert any(
        "flex: none" in rule for rule in fitting_rules(".fit-detail .fit-item-qty")
    )
    assert fitting_rules(".fit-detail .fit-item-name")


def test_fitting_checkbox_focus_scrolls_its_visible_label():
    for selector in (".fit-select", ".fit-collections .check"):
        assert any("position: relative" in rule for rule in fitting_rules(selector))
    for selector in (".fit-select input", ".fit-collections .check input"):
        assert any(
            "inset: 0" in rule and "width: 100%" in rule and "height: 100%" in rule
            for rule in fitting_rules(selector)
        )


def test_fitting_forced_colour_outline_is_decided_at_root():
    assert "outline:" in fitting_rules(".fit-row.open")[-1]
    assert "var(--fitting-forced-ink)" in fitting_rules(".fit-row.open")[-1]
    roots = re.findall(r":root\s*\{([^{}]*)\}", CSS)
    assert any("--fitting-forced-ink: CanvasText" in body for body in roots)
    assert not re.search(r"\bCanvas(?:Text)?\b", re.sub(r":root\s*\{[^{}]*\}", "", CSS))


def test_clipboard_import_is_inline_labelled_and_keeps_status_mounted():
    tree = PageTree()
    tree.feed(HTML)

    def descendants(node):
        yield node
        for child in node["children"]:
            yield from descendants(child)

    nodes = list(descendants(tree.root))
    by_id = {node["attrs"].get("id"): node for node in nodes}
    panel = by_id["fittings-import-panel"]
    assert "hidden" in panel["attrs"]
    assert "card" not in panel["attrs"].get("class", "").split()
    scroll = list(descendants(by_id["fittings-workspace-scroll"]))
    assert panel in scroll and by_id["fittings-list"] in scroll
    assert scroll.index(panel) < scroll.index(by_id["fittings-list"])
    field = by_id["fittings-import-text"]
    assert field["tag"] == "textarea" and "field" in field["attrs"]["class"]
    help_node = by_id[field["attrs"]["aria-describedby"]]
    assert scroll.index(help_node) < scroll.index(by_id["fittings-import-review"])
    assert "hidden" not in help_node["attrs"]
    assert any(
        node["tag"] == "label"
        and node["attrs"].get("for") == "fittings-import-text"
        and "lab" in node["attrs"].get("class", "").split()
        for node in nodes
    )
    status = by_id["fittings-import-status"]["attrs"]
    assert status["role"] == "status" and "hidden" not in status
    for name in ("open", "read", "review", "add", "close", "show"):
        classes = by_id[f"fittings-import-{name}"]["attrs"]["class"].split()
        assert "btn" in classes and "acc" not in classes
    assert "disabled" in by_id["fittings-import-add"]["attrs"]
    for selector in (r"\.fit-import-panel", r"\.fit-import-candidate"):
        assert re.search(selector + r"\[hidden\]\s*\{\s*display:\s*none", CSS)


def test_the_nav_button_exists_and_points_at_the_route():
    """The fourth destination, in the same shape the other three take:
    a `.navbtn` with `data-route` naming a route the page actually has."""
    match = re.search(
        r'<button class="navbtn"[^>]*id="nav-fittings"[^>]*data-route="fittings"',
        HTML,
    )
    assert match, "index.html has no Fittings nav button in the expected shape"
    assert 'id="route-fittings"' in HTML, "index.html has no #route-fittings"


def test_route_uses_shared_eve_workspace_class():
    """Fittings route must use the shared .eve-workspace parent grid.

    Use a class-token-aware match so ordering or extra tokens do not fail.
    """
    match = re.search(
        r"<div[^>]*\bclass=\"(?=[^\"]*\broute\b)(?=[^\"]*\beve-workspace\b)[^\"]*\"[^>]*\bid=\"route-fittings\"",
        HTML,
    )
    assert match, (
        "route-fittings does not carry both route and eve-workspace class tokens"
    )


def test_eve_workspace_css_has_required_properties():
    """Assert the shared .eve-workspace rule declares the required geometry."""
    match = re.search(r"(?<![\w-])\.eve-workspace\s*\{([^}]*)\}", CSS, re.DOTALL)
    assert match, "no .eve-workspace rule found in style.css"
    body = match.group(1)
    assert "display" in body and "none" in body, (
        ".eve-workspace must default to display: none"
    )
    assert "grid-template-columns" in body and "214px minmax(0, 1fr)" in body, (
        ".eve-workspace must set grid-template-columns: 214px minmax(0, 1fr)"
    )
    assert "gap" in body and "12px" in body, ".eve-workspace must set gap: 12px"
    assert "padding" in body and "12px" in body, ".eve-workspace must set padding: 12px"
    assert "min-height" in body and "0" in body, ".eve-workspace must set min-height: 0"


def test_eve_workspace_active_sets_display_grid():
    match = re.search(
        r"(?<![\w-])\.eve-workspace\.active\s*\{([^}]*)\}", CSS, re.DOTALL
    )
    assert match and "display" in match.group(1) and "grid" in match.group(1), (
        ".eve-workspace.active must set display: grid"
    )


def test_primary_action_alignment_shared_rule():
    rule = re.search(
        r"(?<![\w-])\.skills-head\s*>\s*\.workspace-primary\s*\{([^}]*)\}",
        CSS,
        re.DOTALL,
    )
    assert rule, "no .skills-head > .workspace-primary rule found in style.css"
    body = rule.group(1)
    assert "margin-left" in body and "auto" in body, (
        ".skills-head > .workspace-primary must set margin-left: auto"
    )
    assert "align-self" in body and "center" in body, (
        ".skills-head > .workspace-primary must set align-self: center"
    )


def test_there_are_exactly_four_destinations():
    """The title-bar destination count this task adds. DESIGN.md's own
    warning is that a destination gets added "one at a time" without the
    arithmetic being redone -- this pins the count so the next one has to
    revisit it deliberately rather than by accident."""
    nav_routes = set(re.findall(r'class="navbtn[^"]*"[^>]*data-route="([\w-]+)"', HTML))
    assert nav_routes == {"main", "evesettings", "skills", "fittings"}, sorted(
        nav_routes
    )


def test_the_route_map_carries_fittings():
    """WM.route's `routes` object is the second half of the nav button --
    a button with no map entry lights nothing when clicked."""
    assert "fittings: 'route-fittings'" in APP_JS


def test_fittings_is_gated_with_the_other_eve_destinations():
    """Visibility only (DESIGN.md/app.js's own note on WM.apply_eve_gate):
    with the EVE tools hidden, Fittings must disappear along with Profiles
    and Skills, or it is a fourth control that does nothing useful without
    an EVE sign-in and no longer respects the gate."""
    declared = re.search(r"WM\.EVE_ROUTES = \[([^\]]*)\]", APP_JS)
    assert declared, "app.js no longer declares WM.EVE_ROUTES"
    gated = set(re.findall(r"'([\w-]+)'", declared.group(1)))
    assert "fittings" in gated


def test_fittings_joins_the_remembered_destination_list():
    """app.js:284's own bug record: the gear returns to `WM.last_destination`,
    and that variable is only ever set for the peer destinations named in
    one `if` inside WM.route. Leaving Fittings out of it means the gear
    could return here having never marked it current, or -- symmetrically --
    leaving some OTHER peer destination and coming back to Fittings looks
    fine until the EVE gate is toggled off while standing on it, at which
    point apply_eve_gate's `last_destination` repair (which walks
    WM.EVE_ROUTES generically) has nothing to repair because this route was
    never recorded as the last one in the first place."""
    match = re.search(
        r"if \(name === 'main'([^)]*)\)[\s\S]{0,300}?WM\.last_destination = name;",
        APP_JS,
    )
    assert match, (
        "WM.route's peer-destination block was not found in the expected shape"
    )
    assert "'fittings'" in match.group(1), (
        "entering fittings never updates WM.last_destination, so the gear "
        "can return to it having never registered it as current"
    )


def test_the_script_is_included():
    assert '<script src="fittings.js"></script>' in HTML


def test_fittings_registers_the_enter_leave_contract():
    """Same shape as alerts.js/formations.js's own `wm:route` listener: one
    `document.addEventListener('wm:route', ...)` with an explicit early
    return for every route that is not this one. That early return is the
    hook Task 9's poll/capture cleanup attaches to -- see the file's own
    header comment -- so it has to exist even though nothing is armed yet."""
    assert "document.addEventListener('wm:route'" in FITTINGS_JS
    match = re.search(
        r"document\.addEventListener\('wm:route', function \(event\) \{\s*"
        r"if \(event\.detail !== 'fittings'\) \{",
        FITTINGS_JS,
    )
    assert match, (
        "fittings.js's wm:route listener does not guard on entering "
        "'fittings' before doing anything, so it would fire on every route "
        "change in the app"
    )


def test_entry_asks_python_for_state_exactly_once():
    """The route asks; Python does not push unprompted (app.js:139-148's
    rule, restated by skills.js's own `asked` guard). This is the interface
    the Files list promises: 'route-enter call to fittings_state'.

    Task 9 gave `fittings_state` a `filters` argument (collection scope,
    search, ship, page), so the literal call is no longer the bare,
    argument-less form Task 6's stub answered -- only that call still
    happens exactly once per route entry."""
    assert "WM.send('fittings_state', " in FITTINGS_JS
    assert "var asked" in FITTINGS_JS or "asked = " in FITTINGS_JS


def test_returning_from_settings_after_an_authority_change_rereads_fittings_state():
    """Task 9 fix round 1: while Settings owns sign-in/forget, Fittings must
    not stay stale after an off-route authority change. The route still
    ignores `wm:eve-authority` while hidden, so leaving must clear the
    one-entry latch and returning must ask Python again exactly once."""
    route_listener = re.search(
        r"document\.addEventListener\('wm:route', function \(event\) \{(?P<body>.*?)\n  \}\);",
        FITTINGS_JS,
        re.DOTALL,
    )
    assert route_listener, (
        "fittings.js no longer has the route listener this regression guards"
    )
    body = route_listener.group("body")
    assert "if (event.detail !== 'fittings') {" in body
    assert "asked = false;" in body
    assert "if (asked) return;\n    asked = true;\n    requestState();" in body
    assert (
        "document.addEventListener('wm:eve-authority', function () {\n"
        "    if (WM.current_route !== 'fittings') return;\n"
        "    requestState();\n"
        "  });"
    ) in FITTINGS_JS


def test_fittings_state_bridge_call_matches_a_real_api_method():
    """The other half of test_bridge_contract.py's
    test_every_bridge_method_the_page_calls_exists_on_the_api, pinned here
    by name so a rename of the stub silently breaks this route specifically
    rather than only showing up in the generic sweep."""
    from wingman.ui.api import Api

    assert callable(getattr(Api, "fittings_state", None))


def test_the_pager_can_actually_hide():
    r"""Round 1 fix for a Major found after 5473d52 shipped: `#fittings-pager`
    carries a static `hidden` attribute in index.html, and `.fit-pager`
    sets its own `display`, so without a `.fit-pager[hidden]` override a
    single-page or an unavailable workspace rendered the pager anyway --
    the exact trap test_page_conventions.py's
    test_every_hidden_element_can_actually_hide exists to catch.

    That generic detector missed this instance because its display-search
    anchors to the start of a CSS line
    (`re.search(r"(?m)^\s*display\s*:", block)`), and `.fit-pager` declares
    `display: flex` mid-line, after `flex: none; ` on the same line --
    never at a line start. This test parses the actual declaration block
    instead of anchoring to line starts, so it does not share that blind
    spot and fails against 5473d52.
    """
    assert re.search(
        r'<div class="fit-pager" id="fittings-pager"[^>]*\bhidden\b', HTML
    ), "#fittings-pager no longer carries a static hidden attribute"

    block_match = re.search(r"(?<![\w-])\.fit-pager\s*\{([^{}]*)\}", CSS)
    assert block_match, "no bare .fit-pager rule found in style.css"
    assert re.search(r"display\s*:\s*\w+", block_match.group(1)), (
        "this test's own premise (that .fit-pager sets a display the UA "
        "[hidden] rule cannot beat) no longer holds -- if that is now "
        "true some other way, this assertion should be revisited rather "
        "than just deleted"
    )

    override_match = re.search(r"\.fit-pager\[hidden\]\s*\{([^{}]*)\}", CSS)
    assert override_match, (
        "style.css has no .fit-pager[hidden] rule, so #fittings-pager stays "
        "visible when its `hidden` attribute is set -- a single-page or "
        "unavailable Fittings workspace would show the pager"
    )
    assert re.search(r"display\s*:\s*none", override_match.group(1)), (
        ".fit-pager[hidden] exists but does not set display: none"
    )


def test_screenshot_state_handler_is_allowlisted_bounded_and_read_only():
    assert "'onFittingsScreenshotState'" in APP_JS
    assert "WM.handle('onFittingsScreenshotState'" in FITTINGS_JS
    api_source = (WEB.parent / "ui" / "api.py").read_text(encoding="utf-8")
    assert '_push("onFittingsScreenshotState"' not in api_source
    handler = FITTINGS_JS[FITTINGS_JS.index("WM.handle('onFittingsScreenshotState'") :]
    handler = handler[: handler.index("document.addEventListener('wm:route'")]
    assert "validScreenshotFixture(payload)" in handler
    validator = FITTINGS_JS[FITTINGS_JS.index("function validScreenshotFixture") :]
    validator = validator[: validator.index("function screenshotEntries")]
    assert "fittings-screenshot-v1" in validator
    assert "JSON.stringify(payload)" in validator
    assert "512 * 1024" in validator
    assert "renderScreenshotState" in handler
    for writer in (
        "fittings_start_copy",
        "fittings_refresh",
        "fittings_enable_character",
        "fittings_forget_character",
        "fittings_update_metadata",
        "fittings_set_membership",
        "fittings_set_supersession",
        "fittings_delete_entry",
    ):
        assert writer not in handler


def test_screenshot_mode_intercepts_reads_and_is_cleared_on_route_leave():
    assert "if (screenshotFixture)" in FITTINGS_JS
    assert "screenshotWorkspace(currentFilters())" in FITTINGS_JS
    assert "screenshotDetail(id)" in FITTINGS_JS
    assert "screenshotPreflight(" in FITTINGS_JS
    leave = FITTINGS_JS[FITTINGS_JS.index("document.addEventListener('wm:route'") :]
    leave = leave[: leave.index("// ---- rail")]
    assert "screenshotFixture = null;" in leave


def test_copy_selection_is_pruned_to_the_current_rendered_page():
    """Deleted, filtered-out, and other-page IDs must neither inflate the
    accent label nor cross into preflight."""
    assert "function pruneSelection" in FITTINGS_JS
    assert re.search(r"pruneSelection\(payload\.rows \|\| \[\]\);", FITTINGS_JS)
    assert "function visibleSelectedIds" in FITTINGS_JS
    assert "var entryIds = visibleSelectedIds();" in FITTINGS_JS
    assert re.search(r"fittings_preflight_copy',\s*entryIds", FITTINGS_JS)


def test_filter_collection_and_page_changes_clear_selection_before_refetch():
    """Selection from the page being left cannot remain actionable during
    a debounce or bridge round trip for the next page."""
    assert "function clearSelection()" in FITTINGS_JS
    for transition in (
        "filters.collection_id = id;\n    filters.page = 1;\n    clearSelection();\n    requestState();",
        "filters.page -= 1;\n    clearSelection();\n    requestState();",
        "filters.page += 1;\n    clearSelection();\n    requestState();",
    ):
        assert transition in FITTINGS_JS
    assert FITTINGS_JS.count("clearSelection();") >= 6


def test_route_leave_force_closes_copy_and_resets_progress_phase():
    """A late completion push is ignored after leave, so forced close itself
    must release the phase that disables the route's sole accent action."""
    close_at = FITTINGS_JS.index("function closeCopyOverlay")
    close = FITTINGS_JS[
        close_at : FITTINGS_JS.index("WM.el('fittings-copy-close')", close_at)
    ]
    leave = FITTINGS_JS[FITTINGS_JS.index("document.addEventListener('wm:route'") :]
    leave = leave[: leave.index("// ---- rail")]

    assert "if (force) copyPhase = 'targets';" in close
    assert "renderSelectionCount();" in close
    assert "closeCopyOverlay(true);" in leave
    assert leave.index("fittings_cancel_copy") < leave.index("closeCopyOverlay(true)")


def test_rejected_discrete_edits_immediately_requery_persisted_state():
    """Discrete controls revert on refusal. Metadata text instead remains a draft;
    its acknowledgement/failure ordering is covered by test_fittings_runtime.py.
    """
    for bridge_name in (
        "fittings_rename_collection",
        "fittings_set_membership",
        "fittings_set_supersession",
    ):
        call = FITTINGS_JS.index("WM.send('" + bridge_name + "'")
        tail = FITTINGS_JS[call : call + 300]
        assert ".then(requeryIfRejected)" in tail, bridge_name
    assert "function requeryIfRejected(applied)" in FITTINGS_JS
    assert "if (!applied) requestState();" in FITTINGS_JS


def test_rejected_fitting_delete_requeries_without_clearing_page_state():
    call = FITTINGS_JS.index("WM.send('fittings_delete_entry'")
    callback = FITTINGS_JS[call : FITTINGS_JS.index("});\n    });", call)]

    assert ".then(function (applied)" in callback
    rejection = callback[callback.index("if (!applied)") :]
    rejection = rejection[: rejection.index("}") + 1]
    assert "requestState();" in rejection
    assert "return;" in rejection
    for cleanup in (
        "delete selected[current.id];",
        "expandedId = '';",
        "detail = null;",
    ):
        assert cleanup not in rejection
        assert cleanup in callback[callback.index("if (!applied)") + len(rejection) :]


def test_refresh_refusal_error_is_rendered_from_semantic_progress():
    notices = FITTINGS_JS[
        FITTINGS_JS.index("function renderNotices") : FITTINGS_JS.index(
            "function renderShipFilterOptions"
        )
    ]
    assert "progress && progress.error" in notices
    assert "lines.push(progress.error);" in notices


def test_copy_has_preflight_progress_and_results_overlays():
    for element_id in (
        "fittings-copy-overlay",
        "fittings-copy-dialog",
        "fittings-copy-body",
        "fittings-copy-review",
        "fittings-copy-start",
        "fittings-copy-cancel",
    ):
        assert f'id="{element_id}"' in HTML
    assert "WM.send('fittings_preflight_copy'" in FITTINGS_JS
    assert "WM.send('fittings_start_copy'" in FITTINGS_JS
    assert "WM.send('fittings_cancel_copy'" in FITTINGS_JS
    assert "WM.confirm('Copy fittings'" in FITTINGS_JS
    assert "write_count" in FITTINGS_JS


def test_rejected_conflict_recheck_preserves_the_usable_preflight():
    request = FITTINGS_JS[
        FITTINGS_JS.index("function requestCopyPreflight") : FITTINGS_JS.index(
            "function preflightSummary"
        )
    ]
    rejected_at = request.index("if (!payload || !payload.accepted)")
    accepted_assignment_at = request.index("copyPreflight = payload;")
    rejection = request[rejected_at:accepted_assignment_at]

    assert accepted_assignment_at > rejected_at
    assert "renderCopyPreflight(true);" in rejection
    assert "payload && payload.error" in rejection
    assert (
        "updateConflictReady();"
        in FITTINGS_JS[
            FITTINGS_JS.index("function renderCopyPreflight") : FITTINGS_JS.index(
                "function conflictResolutionNode"
            )
        ]
    )


def test_copy_conflicts_offer_alternate_name_or_explicit_skip():
    assert "fit-copy-alternate" in FITTINGS_JS
    assert "Skip this pair" in FITTINGS_JS
    assert "alternateNames" in FITTINGS_JS
    assert "'Replace'" not in re.sub(
        r"/\*.*?\*/|//[^\n]*", "", FITTINGS_JS, flags=re.DOTALL
    )


def test_copy_results_name_every_terminal_category_and_never_offer_retry():
    for label in (
        "Copied",
        "Already present",
        "Conflict / skipped",
        "Failed",
        "Needs verification",
        "Not attempted",
        "Cancelled",
    ):
        assert label in FITTINGS_JS
    copy_section = FITTINGS_JS[FITTINGS_JS.index("function renderCopyResults") :]
    assert "Retry" not in copy_section


def test_copy_result_terminal_states_use_existing_semantic_tokens():
    failed = re.search(r"\.fit-copy-result\.failed\s*\{([^{}]*)\}", CSS)
    assert failed and "color: var(--err)" in failed.group(1)
    for status in ("unattempted_throttle", "cancelled"):
        rule = re.search(rf"\.fit-copy-result\.{status}\s*\{{([^{{}}]*)\}}", CSS)
        assert rule and "color: var(--warn)" in rule.group(1), status


def test_copy_identity_text_can_wrap_in_review_results_and_progress():
    for selector in (r"\.fit-copy-pair", r"#fittings-copy-status"):
        rule = re.search(selector + r"\s*\{([^{}]*)\}", CSS)
        assert rule and "overflow-wrap: anywhere" in rule.group(1), selector


def test_fittings_empty_state_starts_hidden_until_the_first_payload():
    empty = re.search(r'<div class="empty" id="fittings-empty"[^>]*>', HTML)
    assert empty and re.search(r"\bhidden\b", empty.group(0))


def test_fittings_hands_character_management_off_to_settings():
    assert 'id="fittings-manage-characters"' in HTML
    assert 'id="fittings-characters-open"' not in HTML
    assert "Manage characters…" in HTML
    assert "WM.openSettingsSection('characters')" in FITTINGS_JS
    for removed in (
        "fittings_enable_character",
        "fittings_cancel_auth",
        "fittings_forget_character",
    ):
        assert removed not in FITTINGS_JS
    for removed_id in (
        "fittings-characters-overlay",
        "fittings-characters-dialog",
        "fittings-characters-title",
        "fittings-characters-body",
        "fittings-characters-close",
    ):
        assert f'id="{removed_id}"' not in HTML


def test_fittings_empty_and_copy_target_copy_name_settings_without_auth_controls():
    assert (
        "Authenticate a character in Settings \u203a Character access, then return and "
        "press Refresh characters."
    ) in FITTINGS_JS
    assert "No EVE characters available." not in FITTINGS_JS
    assert "Enable fittings" not in FITTINGS_JS
    assert "Re-authenticate this character from Skills first." not in FITTINGS_JS


def test_copy_selected_remains_the_only_accent_action():
    route = re.search(
        r'<div[^>]*\bid="route-fittings"[^>]*>[\s\S]*?</div>\s*\n\s*<div[^>]*\bid="route-firstrun"',
        HTML,
    )
    assert route
    assert len(re.findall(r'class="[^\"]*\bacc\b', route.group(0))) == 1


def test_fittings_primary_action_includes_workspace_primary_token():
    """The Fittings primary action must carry the workspace-primary token.

    This should fail if workspace-primary is removed even while the
    shared .eve-workspace class and the acc token remain.
    """
    btn = re.search(r'<button[^>]*id="fittings-copy-selected"[^>]*>', HTML)
    assert btn, "fittings-copy-selected button is missing from index.html"
    assert re.search(r'class="[^"]*\bworkspace-primary\b', btn.group(0)), (
        "fittings-copy-selected must include the workspace-primary token: "
        + btn.group(0)
    )


def test_render_pager_defaults_page_when_the_payload_has_none():
    """Defence in depth alongside the CSS fix above: an unavailable
    payload (`{available: false, warnings: [...]}`) has no `page` key, and
    render() does not gate on `available` before calling renderPager, so
    if the CSS guard above ever regresses this must not also read 'Page
    undefined of 1' instead of a sane default."""
    match = re.search(r"function renderPager\(\) \{([\s\S]*?)\n  \}", FITTINGS_JS)
    assert match, "fittings.js's renderPager() was not found in the expected shape"
    body = match.group(1)
    assert re.search(r"var page = STATE\.page \|\| 1;", body), (
        "renderPager no longer defaults a missing/undefined STATE.page, so a "
        "malformed or unavailable payload can render 'Page undefined of N' "
        "in the pager's text content even while it is hidden"
    )
    # STATE.page_size is a different field and must not trip this -- only a
    # bare `STATE.page` read outside the one defaulting line is the problem.
    bare_reads = re.findall(r"STATE\.page(?!_size)\b", body)
    assert bare_reads == ["STATE.page"], (
        "renderPager reads STATE.page directly somewhere other than the "
        "defaulted `page` variable: " + repr(bare_reads)
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_fittings_worker_reuses_process_and_preserves_business_outcomes(
    fittings_page_worker: NodeScenarioWorker,
):
    first = fittings_page_worker.request(
        "checkbox-name",
        {"screenshot": None, "isolation_probe": "mutate"},
        timeout=15.0,
    )
    process = fittings_page_worker._proc
    dialog = request_fittings_scenario(fittings_page_worker, "dialog-description")
    pristine = fittings_page_worker.request(
        "checkbox-name",
        {"screenshot": None, "isolation_probe": "pristine"},
        timeout=15.0,
    )

    assert first["output"] == "PASS checkbox-name"
    assert dialog["output"] == "PASS dialog-description"
    assert pristine["output"] == "PASS checkbox-name"
    assert fittings_page_worker._proc is process


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_fittings_worker_vm_failures_preserve_stack_and_recover(
    fittings_page_worker: NodeScenarioWorker,
):
    initial = request_fittings_scenario(fittings_page_worker, "checkbox-name")
    process = fittings_page_worker._proc
    assert initial["output"] == "PASS checkbox-name"

    for mode, stack_name in [
        ("vm-throw", "protocolVmThrow"),
        ("vm-reject", "protocolVmReject"),
    ]:
        with pytest.raises(NodeScenarioFailure) as failure:
            fittings_page_worker.request(
                f"protocol/{mode}",
                {
                    "screenshot": None,
                    "protocol_probe": mode,
                    "failure_logs": True,
                },
                timeout=15.0,
            )
        assert stack_name in failure.value.stack
        assert failure.value.reply is not None
        logs = failure.value.reply.get("logs")
        assert isinstance(logs, list)
        assert 1 <= len(logs) <= 40
        assert all(isinstance(line, str) and len(line) <= 400 for line in logs)
        for level in ("log", "info", "warn", "debug"):
            assert any(f"protocol {level} context" in line for line in logs)
        assert any(line.endswith("…") for line in logs)
        recovered = request_fittings_scenario(fittings_page_worker, "checkbox-name")
        assert recovered["output"] == "PASS checkbox-name"
        assert fittings_page_worker._proc is process

    for kind in ("getters", "proxy"):
        with pytest.raises(NodeScenarioFailure) as failure:
            fittings_page_worker.request(
                f"protocol/vm-reject/{kind}",
                {
                    "screenshot": None,
                    "protocol_probe": "vm-reject",
                    "hostile_rejection": kind,
                    "failure_logs": True,
                },
                timeout=15.0,
            )
        assert "protocolHostileReject" in failure.value.stack
        assert failure.value.reply is not None
        recovered = fittings_page_worker.request(
            "checkbox-name",
            {"screenshot": None, "assert_unhandled_host_pristine": True},
            timeout=15.0,
        )
        assert recovered["output"] == "PASS checkbox-name"
        assert f"protocol hostile {kind} rejection" in str(failure.value.reply["error"])
        assert any(
            "protocol log context" in line
            for line in failure.value.reply.get("logs", [])
        )
        assert fittings_page_worker._proc is process


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.parametrize(
    "mode",
    ["pending-timer-normal-exit", "pending-timer-assertion-exit"],
    ids=["pending-timer-normal-exit", "pending-timer-assertion-exit"],
)
def test_fittings_worker_cancels_pending_timer(
    fittings_page_worker: NodeScenarioWorker, mode: str
):
    initial = request_fittings_scenario(fittings_page_worker, "checkbox-name")
    process = fittings_page_worker._proc
    assert initial["output"] == "PASS checkbox-name"

    with pytest.raises(NodeScenarioFailure) as failure:
        fittings_page_worker.request(
            f"protocol/{mode}",
            {"screenshot": None, "protocol_probe": mode},
            timeout=15.0,
        )
    expected_error = (
        "request left a live timer"
        if mode == "pending-timer-normal-exit"
        else "protocol cleanup probe failure"
    )
    assert failure.value.reply is not None
    assert str(failure.value.reply["error"]).splitlines()[0] == expected_error
    assert expected_error in failure.value.stack
    recovered = request_fittings_scenario(fittings_page_worker, "checkbox-name")
    assert recovered["output"] == "PASS checkbox-name"
    assert fittings_page_worker._proc is process


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.parametrize(
    "scenario",
    [
        "checkbox-name",
        "dialog-description",
        "tab-wrap",
        "tab-outside",
        "hidden-controls",
        "close",
        "escape",
        "fallback-detached",
        "fallback-hidden",
        "fallback-invisible",
        "fallback-disabled",
        "shared-dialog",
        "progress-focus",
        "progress-tab",
        "cancel-focus",
        "cancel-tab",
        "progress-shared-dialog",
        "review-scroller",
        "results-scroller",
        "interleaving-complete-dismiss",
        "interleaving-queued-complete-dismiss",
        "interleaving-rollback-false-cancel",
        "interleaving-rollback-null-cancel",
        "interleaving-rollback-false-uncancelled",
        "interleaving-rollback-null-uncancelled",
        "interleaving-root-tab",
        "interleaving-descendant-tab",
        "progress",
        "route-leave",
    ],
)
def test_copy_accessibility_in_node(
    fittings_page_worker: NodeScenarioWorker, scenario: str
):
    reply = request_fittings_scenario(fittings_page_worker, scenario)
    assert reply["output"] == f"PASS {scenario}"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.parametrize(
    "scenario",
    [
        "state-route-lifecycle",
        "state-request-sequence",
        "state-selection-scope",
        "state-detail-sequence",
        "state-rejected-mutation",
        "state-screenshot-progress",
        "state-stale-preflight",
        "state-stale-progress",
        "state-ticket-progress",
        "state-stale-start-result",
        "state-copy-lifecycle",
    ],
)
def test_fittings_state_machine_in_node(
    fittings_page_worker: NodeScenarioWorker, scenario: str
):
    reply = request_fittings_scenario(fittings_page_worker, scenario)
    assert reply["output"] == f"PASS {scenario}"
