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
