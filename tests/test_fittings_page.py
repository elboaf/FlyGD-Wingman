"""The Fittings destination shell (SDD task 6).

Nothing executes web/*.js (docs/history/webview-replatform-design.md:545),
so every assertion here is lexical, the same posture test_bridge_contract.py
and test_settings_eve_gate.py already take. This file is deliberately
narrow: Task 6 adds only a route shell and a safe unavailable-state render,
not the fitting workspace -- test_fittings_wiring.py (Task 9) is where the
real curation UI gets its coverage.
"""

import re
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "wingman" / "web"
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
        re.S,
    )
    assert route_listener, "fittings.js no longer has the route listener this regression guards"
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
        'Authenticate a character in Settings \u203a Characters, then return and '
        'press Refresh characters.'
    ) in FITTINGS_JS
    assert 'No EVE characters available.' not in FITTINGS_JS
    assert 'Enable fittings' not in FITTINGS_JS
    assert 'Re-authenticate this character from Skills first.' not in FITTINGS_JS


def test_copy_selected_remains_the_only_accent_action():
    route = re.search(
        r'<div class="route" id="route-fittings"[\s\S]*?</div>\s*\n\s*<div class="route" id="route-firstrun"',
        HTML,
    )
    assert route
    assert len(re.findall(r'class="[^"]*\bacc\b', route.group(0))) == 1


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
