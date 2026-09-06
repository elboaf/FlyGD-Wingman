"""Fittings shell contracts and executable copy-control accessibility checks.

The Node DOM double executes the real Fittings module against the page's
markup. It tests keyboard/focus behavior, not browser layout or WebView2's
accessibility tree; those still require the Windows smoke pass.
"""

import json
import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parent.parent / "wingman" / "web"


class _PageTree(HTMLParser):
    """Keep real element order, ancestry, and attributes for the Node double."""

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


HTML = (WEB / "index.html").read_text(encoding="utf-8")
APP_JS = (WEB / "app.js").read_text(encoding="utf-8")
FITTINGS_JS = (WEB / "fittings.js").read_text(encoding="utf-8")
# Comments stripped before any rule parsing, same as test_page_conventions.py:
# a naive selector capture otherwise swallows a leading block comment.
CSS = re.sub(
    r"/\*.*?\*/", "", (WEB / "style.css").read_text(encoding="utf-8"), flags=re.DOTALL
)


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


def test_rejected_local_edits_immediately_requery_persisted_state():
    """Controller alerts explain refusal; a fresh state/detail render reverts
    controls that otherwise continue displaying values that were never saved."""
    for bridge_name in (
        "fittings_rename_collection",
        "fittings_update_metadata",
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
    assert "renderCopyPreflight();" in rejection
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
        "Success",
        "Already present",
        "Conflict / skipped",
        "Failed",
        "Unknown",
        "Unattempted due to throttle",
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
        "Authenticate a character in Settings \u203a Characters, then return and "
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


_COPY_ACCESSIBILITY_HARNESS = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const page = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const scenario = process.argv[3];

// Only DOM mechanics live here. Fittings rendering, listeners, selection and
// phase changes all run from the unmodified production module below.
class Element {
  constructor(tag, attrs = {}) {
    this.tagName = tag.toUpperCase();
    this.attrs = {...attrs};
    this.children = [];
    this.parentNode = null;
    this.listeners = {};
    this.hidden = 'hidden' in attrs;
    this.disabled = 'disabled' in attrs;
    this.className = attrs.class || '';
    this.id = attrs.id || '';
    this.type = attrs.type || '';
    this.value = '';
    this.style = {};
    this.classList = {
      contains: name => this.className.split(/\s+/).includes(name),
      add: name => { this.className += ' ' + name; },
      remove: name => {
        this.className = this.className.split(/\s+/).filter(x => x !== name).join(' ');
      }
    };
  }
  appendChild(child) {
    if (child.parentNode) child.remove();
    this.children.push(child);
    child.parentNode = this;
    return child;
  }
  remove() {
    this.parentNode.children = this.parentNode.children.filter(x => x !== this);
    this.parentNode = null;
  }
  set textContent(value) {
    this.children.forEach(child => { child.parentNode = null; });
    this.children = [];
    this.text = value;
  }
  get textContent() { return this.text || ''; }
  setAttribute(name, value) { this.attrs[name] = String(value); }
  getAttribute(name) { return this.attrs[name] ?? null; }
  contains(node) {
    return node === this || this.children.some(child => child.contains(node));
  }
  matches(selector) {
    return selector.split(',').some(part => {
      part = part.trim();
      const exclusions = [...part.matchAll(/:not\(([^)]+)\)/g)];
      if (exclusions.some(match => this.matches(match[1]))) return false;
      part = part.replace(/:not\([^)]+\)/g, '');
      const tag = part.match(/^[a-z]+/i);
      if (tag && tag[0].toUpperCase() !== this.tagName) return false;
      if (part.includes(':disabled') && !this.disabled) return false;
      if ([...part.matchAll(/\.([\w-]+)/g)].some(match =>
          !this.classList.contains(match[1]))) return false;
      return [...part.matchAll(/\[([\w-]+)(?:="([^"]*)")?\]/g)].every(match => {
        const value = match[1] === 'hidden' ? (this.hidden ? '' : null)
          : this.getAttribute(match[1]);
        return value !== null && (match[2] === undefined || value === match[2]);
      });
    });
  }
  querySelectorAll(selector) {
    const found = [];
    const walk = node => node.children.forEach(child => {
      if (child.matches(selector)) found.push(child);
      walk(child);
    });
    walk(this);
    return found;
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  getClientRects() {
    for (let node = this; node; node = node.parentNode) {
      if (node.hidden || node.style.display === 'none'
          || (node.classList.contains('route') && !node.classList.contains('active'))) {
        return [];
      }
    }
    return document.contains(this) ? [{}] : [];
  }
  focus() {
    if (!this.disabled && this.getClientRects().length
        && getComputedStyle(this).visibility === 'visible') document.activeElement = this;
  }
  blur() { if (document.activeElement === this) document.activeElement = document.body; }
  addEventListener(type, callback) { (this.listeners[type] ||= []).push(callback); }
  dispatchEvent(event) {
    event.target ||= this;
    event.currentTarget = this;
    (this.listeners[event.type] || []).forEach(callback => callback(event));
  }
  click() {
    if (!this.disabled) this.dispatchEvent({type: 'click'});
  }
}
function fromTree(tree) {
  const node = new Element(tree.tag, tree.attrs);
  tree.children.forEach(child => node.appendChild(fromTree(child)));
  return node;
}
const document = fromTree(page);
global.document = document;
document.body = document.querySelector('body');
document.activeElement = document.body;
document.createElement = tag => new Element(tag);
document.getElementById = id => document.querySelectorAll('[id]').find(x => x.id === id) || null;
global.getComputedStyle = node => {
  let visibility = 'visible';
  for (let current = node; current; current = current.parentNode) {
    if (current.style.visibility) { visibility = current.style.visibility; break; }
  }
  return {visibility};
};
const el = id => {
  const node = document.getElementById(id);
  assert.ok(node, 'missing real markup: ' + id);
  return node;
};
const route = el('route-fittings');
document.querySelectorAll('.route').forEach(node => node.classList.remove('active'));
route.classList.add('active');
const handlers = {};
const calls = [];
const state = {
  available: true, warnings: [], refreshing: false,
  collections: [{id: 'all', name: 'All fittings', count: 1}], ships: [],
  characters: [
    {character_id: 1, character_name: 'Pilot', status: 'enabled', fetched_utc: '2026-09-01', stale: false},
    {character_id: 2, character_name: 'Unavailable', status: 'disabled', fetched_utc: '', stale: false}
  ],
  rows: [{id: 'fit-1', name: 'Sabre tackle', ship_name: 'Sabre', ship_type_id: 22456,
    presence_count: 1, collection_ids: [], deployable: true, superseded_by: null}],
  total: 1, page: 1, page_size: 100
};
const WM = {
  current_route: 'fittings', el,
  make(tag, cls, text) {
    const node = new Element(tag, {class: cls || ''});
    if (text !== undefined) node.textContent = text;
    return node;
  },
  handle(name, callback) { handlers[name] = callback; },
  send(name, ...args) {
    calls.push([name, ...args]);
    if (name === 'fittings_state') return Promise.resolve(state);
    if (name === 'fittings_preflight_copy') return Promise.resolve({
      accepted: true, ticket_id: 'ticket', write_count: 1, requires_resolution: false,
      counts: {ready: 1}, pairs: [{entry_id: 'fit-1', character_id: 1,
        fitting_name: 'Sabre tackle', character_name: 'Pilot', status: 'ready', chosen_name: 'Sabre tackle'}]
    });
    if (name === 'fittings_start_copy' || name === 'fittings_cancel_copy') return Promise.resolve(true);
    throw new Error('Unexpected bridge call: ' + name);
  },
  confirm() { return Promise.resolve(true); }
};
global.window = {WM, getComputedStyle};
vm.runInThisContext(fs.readFileSync(process.argv[4], 'utf8'), {filename: 'fittings.js'});
function key(name, shift = false, handled = false) {
  const event = {type: 'keydown', key: name, shiftKey: shift, defaultPrevented: handled,
    preventDefault() { this.defaultPrevented = true; }};
  document.dispatchEvent(event);
  return event;
}
function tick(node) { node.checked = true; node.dispatchEvent({type: 'change'}); }
const flush = async () => { await Promise.resolve(); await Promise.resolve(); };
(async () => {
  document.dispatchEvent({type: 'wm:route', detail: 'fittings'});
  await flush();
  const checkbox = el('fittings-list').querySelector('input');
  if (scenario === 'checkbox-name') {
    assert.equal(checkbox.getAttribute('aria-label'), 'Select Sabre tackle');
    return;
  }
  tick(checkbox);
  const invoker = el('fittings-copy-selected');
  invoker.focus();
  invoker.click();
  const overlay = el('fittings-copy-overlay');
  const close = el('fittings-copy-close');
  const target = el('fittings-copy-body').querySelector('input');
  const review = el('fittings-copy-review');
  assert.equal(overlay.hidden, false, 'Copy selected opens overlay');
  assert.equal(document.activeElement, close, 'opening moves focus into dialog');

  if (scenario === 'tab-wrap') {
    // Review is initially disabled; unavailable target and Start/Cancel are excluded.
    close.focus();
    assert.equal(key('Tab').defaultPrevented, true);
    assert.equal(document.activeElement, target, 'last wraps to first enabled target');
    assert.equal(key('Tab', true).defaultPrevented, true);
    assert.equal(document.activeElement, close, 'first wraps to last');
    tick(target);
    review.focus();
    key('Tab');
    assert.equal(document.activeElement, target, 'newly enabled review is now last');
    target.focus();
    key('Tab', true);
    assert.equal(document.activeElement, review);
    close.focus();
    assert.equal(key('Tab').defaultPrevented, false, 'ordinary interior Tab stays native');
  } else if (scenario === 'tab-outside') {
    invoker.focus();
    assert.equal(key('Tab').defaultPrevented, true);
    assert.equal(document.activeElement, target);
  } else if (scenario === 'hidden-controls') {
    target.parentNode.style.display = 'none';
    close.focus();
    key('Tab');
    assert.equal(document.activeElement, close, 'hidden ancestor excludes target');
    close.disabled = true;
    assert.equal(key('Tab').defaultPrevented, true, 'empty focus list cannot leak Tab');
  } else if (scenario === 'close' || scenario === 'escape') {
    if (scenario === 'close') close.click(); else key('Escape');
    assert.equal(overlay.hidden, true);
    assert.equal(document.activeElement, invoker, 'dismissal restores the saved invoker');
  } else if (scenario.startsWith('fallback-')) {
    if (scenario === 'fallback-detached') {
      const replacement = new Element('button', {id: invoker.id});
      invoker.parentNode.appendChild(replacement);
      invoker.remove();
    } else if (scenario === 'fallback-hidden') invoker.parentNode.style.display = 'none';
    else if (scenario === 'fallback-invisible') invoker.style.visibility = 'hidden';
    else {
      // Real completion clears selection and disables the original invoker.
      handlers.onFittingsProgress({kind: 'copy', phase: 'complete',
        result: {results: [], write_count: 0, status: 'cancelled'}});
    }
    // Fallback must skip both a disabled first control and a hidden ancestor.
    el('fittings-refresh-all').disabled = true;
    el('fittings-manage-characters').parentNode.style.display = 'none';
    close.click();
    assert.equal(overlay.hidden, true);
    assert.equal(document.activeElement, el('fittings-collections').querySelector('button'),
      'fallback finds an available control on active Fittings route');
  } else if (scenario === 'shared-dialog') {
    el('overlay').hidden = false;
    el('dlg-ok').focus();
    key('Tab');
    assert.equal(document.activeElement, el('dlg-ok'), 'shared dialog keeps keyboard ownership');
    // panel.js handles Escape in capture phase, hiding itself before this listener.
    el('overlay').hidden = true;
    key('Escape', false, true);
    assert.equal(overlay.hidden, false, 'shared confirmation Escape does not close copy overlay');
  } else if (scenario === 'progress' || scenario === 'route-leave') {
    tick(target);
    review.click();
    await flush();
    const start = el('fittings-copy-start');
    start.focus();
    key('Tab');
    assert.equal(document.activeElement, close, 'preflight recalculates first control');
    close.focus();
    key('Tab', true);
    assert.equal(document.activeElement, start, 'preflight recalculates last control');
    start.click();
    await flush();
    assert.equal(close.disabled, true, 'Close stays disabled during progress');
    key('Escape');
    close.click();
    assert.equal(overlay.hidden, false, 'progress cannot be dismissed');
    if (scenario === 'route-leave') {
      WM.current_route = 'skills';
      route.classList.remove('active');
      el('route-skills').classList.add('active');
      el('nav-skills').focus();
      document.dispatchEvent({type: 'wm:route', detail: 'skills'});
      assert.equal(overlay.hidden, true, 'route leave force-closes progress');
      assert.equal(document.activeElement, el('nav-skills'), 'cleanup does not steal new route focus');
      assert.ok(calls.some(call => call[0] === 'fittings_cancel_copy'));
      WM.current_route = 'fittings';
      route.classList.add('active');
      document.dispatchEvent({type: 'wm:route', detail: 'fittings'});
      await flush();
      tick(el('fittings-list').querySelector('input'));
      invoker.focus();
      invoker.click();
      assert.equal(close.disabled, false, 'reentry resets progress guard');
      close.click();
      assert.equal(document.activeElement, invoker);
    }
  } else throw new Error('Unknown scenario: ' + scenario);
})().then(() => console.log('PASS ' + scenario)).catch(error => {
  // Node's object-identity diff can print the entire cyclic page tree.
  console.error(error.message.slice(0, 1000));
  process.exitCode = 1;
});
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.parametrize(
    "scenario",
    [
        "checkbox-name",
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
        "progress",
        "route-leave",
    ],
)
def test_copy_accessibility_in_node(tmp_path, scenario):
    page = _PageTree()
    page.feed(HTML)
    markup = tmp_path / "page.json"
    markup.write_text(json.dumps(page.root), encoding="utf-8")
    harness = tmp_path / "copy-accessibility.cjs"
    harness.write_text(_COPY_ACCESSIBILITY_HARNESS, encoding="utf-8")
    result = subprocess.run(
        ["node", str(harness), str(markup), scenario, str(WEB / "fittings.js")],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS {scenario}" in result.stdout
