"""Page conventions, checked lexically.

Nothing in this suite executes web/*.js or renders index.html, so the
conventions the page depends on are enforced by reading its source -- the
same approach test_bridge_contract.py, test_engine_invariants.py and
test_no_tk.py already take, and for the same reason: "to stop something
that was removed on purpose creeping back."

Every rule below is here because it was BROKEN at least once, shipped, and
was found by eye rather than by a test:

- Bare checkboxes rendered as native white Win32 controls on a dark card,
  one per character, on a screen whose sibling module carried a comment
  warning about exactly that.
- A destructive confirmation raised browser chrome captioned with the page
  origin, under a comment claiming it was what the rest of the page did.
- Field labels outside the shared label column rendered brighter than
  every other label and at three different widths.
- An element given `hidden` stayed visible, because its class sets a
  display and an author rule beats the UA stylesheet's [hidden] rule
  regardless of specificity. The CSS documents this trap in six places,
  which is six times it was nearly missed.

These are deliberately mechanical. They cannot judge whether a screen is
well designed; they only stop a convention being dropped silently. What
they cannot see is recorded in DESIGN.md.
"""

import ast
import pathlib
import re

WEB = pathlib.Path(__file__).resolve().parents[1] / "wingman" / "web"
HTML = (WEB / "index.html").read_text(encoding="utf-8")
# Comments are stripped before any rule parsing below: style.css leads
# almost every rule with a block comment, and a naive selector capture
# swallows it -- which made the [hidden] check miss .evestat[hidden], a
# rule that has been there all along.
CSS = re.sub(
    r"/\*.*?\*/", "", (WEB / "style.css").read_text(encoding="utf-8"), flags=re.DOTALL
)
# The same sheet WITH its comments, for the one guard whose subject IS a
# comment: the type scale states its own ratios in prose, and prose is the
# thing that drifts off the values it describes.
RAW_CSS = (WEB / "style.css").read_text(encoding="utf-8")

# Read OFF the page rather than typed here: these two rules exist to catch
# the page drifting from settings.py, and a third hand-kept copy in the
# test would just be one more thing to drift. Sorted for a stable message.
_ALERT_EVENT_IDS = sorted(set(re.findall(r'id="alert-event-([a-z_]+)-enabled"', HTML)))

# The span that renders in place of a hidden native control, mapped to the
# wrapper class whose CSS hides it. Three of them, not two: the alert
# colour swatches are radios drawn as filled squares, so `.ring` -- a 12px
# circle with a dot -- is the wrong shape to reuse and would have meant a
# radio styled as something it is not just to satisfy a test.
#
# Adding a name here is only safe because test_every_hiding_wrapper_
# actually_hides_its_input checks each one really does take its input out
# of the layout. Without that, this dict is a hole in the guard.
_WRAPPERS = {"box": "check", "ring": "radio", "dot": "swatch"}
_WRAPPERS_FOR = {"checkbox": ("box",), "radio": ("ring", "dot")}


def _strip_html_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


def _strip_js_comments(text: str) -> str:
    """Line comments only. Every rationale comment in web/*.js is a line
    comment or a /* */ block at the top of a file; a rule quoted inside one
    must not be what fails a test whose whole point is to explain itself."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"(?m)^\s*//.*$", "", text)


# ---- native form controls ---------------------------------------------


def test_every_hiding_wrapper_actually_hides_its_input():
    """The invariant the two tests below stand on, asserted rather than
    assumed.

    Each wrapper works the same way: the real input is taken out of the
    layout and made invisible, and a styled sibling span is what renders.
    Naming a third wrapper in the allowlist below is only safe if that is
    true of it too -- otherwise the allowlist is how a native control gets
    waved through by a test written to catch native controls.
    """
    for wrapper in sorted(set(_WRAPPERS.values())):
        rule = re.search(rf"\.{wrapper} input \{{([^}}]*)\}}", CSS)
        assert rule, f".{wrapper} has no `input` rule, so its input renders"
        body = rule.group(1)
        assert "opacity: 0" in body and "position: absolute" in body, (
            f".{wrapper} input must be position:absolute and opacity:0 -- "
            f"otherwise the native control is still on screen"
        )


def test_no_checkbox_or_radio_renders_as_a_native_control():
    """Nothing in style.css targets input[type=checkbox] or [type=radio].
    The dark appearance comes ENTIRELY from the wrappers -- the input is
    opacity:0 and the styled span beside it is what you see. A bare input
    is therefore a white Windows widget on a dark card.

    EVE Settings shipped one per character in exactly this way, while
    bookmarks.js already carried a comment warning about it.
    """
    assert "input[type=checkbox]" not in CSS
    assert "input[type=radio]" not in CSS

    body = _strip_html_comments(HTML)
    for match in re.finditer(r'<input[^>]*type="(checkbox|radio)"[^>]*>', body):
        tag = match.group(0)
        after = body[match.end() : match.end() + 120]
        allowed = _WRAPPERS_FOR[match.group(1)]
        assert any(f'class="{w}"' in after for w in allowed), (
            f"bare {match.group(1)} renders as a native Windows control: {tag}"
        )


def test_profiles_generated_copy_checkbox_wraps_before_listeners():
    """The input and adjacent dark box enter one .check before behavior."""
    src = _strip_js_comments((WEB / "evesettings.js").read_text(encoding="utf-8"))
    match = re.search(
        r"groupBox\.type\s*=\s*'checkbox';(.*?)groupBox\.addEventListener",
        src,
        re.DOTALL,
    )
    assert match, "Profiles copy-group checkbox or its listener is missing"
    construction = match.group(1)
    assert re.search(
        r"var groupLabel = WM\.make\('label', 'check',.*?\);\s*"
        r"groupLabel\.prepend\(WM\.make\('span', 'box'\)\);\s*"
        r"groupLabel\.prepend\(groupBox\);",
        construction,
        re.DOTALL,
    ), (
        "before listener registration, the checkbox must be prepended into "
        "a .check label beside the prepended .box visual"
    )


def test_generated_controls_use_the_wrapper_too():
    """The markup is only half of it: the worst instance was built in JS,
    one row per character, so a check on index.html alone would have
    missed it entirely."""
    for path in sorted(WEB.glob("*.js")):
        src = _strip_js_comments(path.read_text(encoding="utf-8"))
        for match in re.finditer(r"""\.type\s*=\s*['"](checkbox|radio)['"]""", src):
            window = src[match.start() : match.start() + 600]
            allowed = _WRAPPERS_FOR[match.group(1)]
            assert any(f"'{w}'" in window or f'"{w}"' in window for w in allowed), (
                f"{path.name}: a generated {match.group(1)} with no "
                f"{' or '.join('.' + w for w in allowed)} wrapper renders "
                f"as a native Windows control"
            )


# ---- native dialogs ----------------------------------------------------


def test_no_native_dialogs():
    """WebView2 renders these as browser chrome captioned with the page
    origin -- a grey box mentioning localhost, in a frameless dark app with
    a custom title bar. WM.confirm and WM.prompt raise the app's own
    overlay through the same queue.

    Python's _confirm cannot serve a page-initiated dialog: it blocks the
    calling thread until dialog_response arrives, so calling it from a
    bridge method deadlocks the thread that has to deliver the answer.
    """
    for path in sorted(WEB.glob("*.js")):
        src = _strip_js_comments(path.read_text(encoding="utf-8"))
        for call in ("window.confirm", "window.prompt", "window.alert"):
            assert call not in src, f"{path.name} calls {call}"


def test_the_gear_carries_a_static_accessible_name_before_the_first_update_push():
    """renderUpdateBadge (app.js) sets `title`/`aria-label` from the first
    `onUpdateStatus` push, but that push is a round trip after the page
    paints. A screen reader that names the gear before it lands would read
    nothing at all without a name baked into the markup itself.
    """
    gear = re.search(r'<button class="winbtn gear"[^>]*>', HTML)
    assert gear, "#btn-settings markup not found"
    assert 'aria-label="Settings"' in gear.group(0)


def test_the_gear_can_show_active_and_update_available_together():
    """The gear is both a destination (`.active` while Settings is open)
    and a badge carrier (`.update-available`). Neither renderer may clear
    the other's class, or opening Settings while an update is available
    would erase the badge, or the reverse.
    """
    app = (WEB / "app.js").read_text(encoding="utf-8")
    assert (
        "WM.el('btn-settings').classList.toggle('active', name === 'settings');" in app
    )
    assert "gear.classList.toggle('update-available', available);" in app
    css = CSS
    assert ".winbtn.gear.update-available" in css
    assert ".winbtn.gear.active" in css


def test_update_progress_has_an_explicit_hidden_override():
    """`#update-progress` sets its own `display` for full-width layout, so
    it needs the author `[hidden]` override the same way `.routenav` and
    `.field-msg` do, or the UA stylesheet's rule loses to specificity-
    matched author origin and the bar stays visible once download finishes
    or a check turns up nothing to show a percentage of.
    """
    assert "#update-progress[hidden] { display: none; }" in CSS


def test_update_progress_animation_is_disabled_under_reduced_motion():
    reduced = re.search(
        r"@media \(prefers-reduced-motion: reduce\) \{(.*?)\n\}",
        CSS,
        re.DOTALL,
    )
    assert reduced and "update-progress" in reduced.group(1)


# ---- the label column --------------------------------------------------


def test_settings_rows_label_through_the_shared_column():
    """`.settings .row > .lab` is a 118px right-aligned column for the
    WHOLE screen. A bare <label> or <span> in a row gets none of it, so it
    renders at full brightness and at its own width -- which is how three
    labels on one screen ended up at 47px, 84px and 71px while every other
    label in the app shared one edge.

    <label class="lab" for="..."> is correct and preferred: it keeps the
    control association a bare span throws away.
    """
    body = _strip_html_comments(HTML)
    # Rows inside a .settings container, which is every Settings section.
    for row in re.finditer(r'<div class="row"[^>]*>(.*?)</div>', body, re.DOTALL):
        inner = row.group(1)
        for label in re.finditer(r"<label(?![^>]*\bclass=)[^>]*>", inner):
            assert False, (
                "a settings row labels outside the shared column: " + label.group(0)
            )


def _media_spans(max_width: int) -> list[tuple[int, int]]:
    """(start, end) offsets into CSS of every `max-width: <n>px` block BODY,
    brace-matched.

    Slicing from the first occurrence to the end of the file is not enough:
    these rules may sit beside the override they correct, so such a slice
    also contains the override itself and an assertion passes on the wrong
    text. That is not hypothetical -- the first version of
    test_an_id_override_of_the_label_column_still_collapses_at_the_floor did
    exactly that and survived deleting the rule it exists to require.

    Offsets rather than text, because the second caller needs to ask where a
    rule IS, not only what the narrow blocks contain.
    """
    spans = []
    for m in re.finditer(rf"@media \(max-width: {max_width}px\)\s*\{{", CSS):
        i, depth = m.end(), 1
        while i < len(CSS) and depth:
            depth += {"{": 1, "}": -1}.get(CSS[i], 0)
            i += 1
        spans.append((m.end(), i - 1))
    return spans


def test_preview_grid_tightens_only_its_column_gap_at_the_840_floor():
    """The six Preview tracks overflowed the pane by 18-20px at the floor.

    Five gaps are the only safe place to reclaim that width: the 210px
    identity floor and the controls remain unchanged, while 10px to 6px
    returns exactly 20px. The base layout stays at its roomier spacing.
    """
    base = re.search(r"#preview-binds\s*\{([^}]*)\}", CSS)
    assert base and re.search(r"\bcolumn-gap\s*:\s*10px\s*;", base.group(1))

    floor = "\n".join(CSS[lo:hi] for lo, hi in _media_spans(840))
    rule = re.search(r"#preview-binds\s*\{([^}]*)\}", floor)
    assert rule and re.fullmatch(r"\s*column-gap\s*:\s*6px\s*;\s*", rule.group(1)), (
        "the 840px tier must change only #preview-binds' column gap to 6px"
    )


def test_an_id_override_of_the_label_column_still_collapses_at_the_floor():
    """Two bind lists take the shared 118px label column away from their
    rows on purpose, for two different reasons: `#eve-binds` because its
    labels are long action names and it gives them a whole line instead,
    `#preview-binds` because it gives the character name a bounded
    length-based track of its own -- an inline column, not a line. Both do it with an
    ID selector: `#eve-binds .row > .lab` and `#preview-binds .row > .lab`.

    ID specificity also beats the `max-width: 720px` block that collapses
    the column above its field, and that block is written against
    `.settings .row > .lab`. So the collapse silently skipped exactly the
    rows that needed it most: three trailing controls on a ~324px row left
    about 60px for "Convert EvE-Scout Bookmarks", eighteen times, and
    `min-width: 0` made it shrink rather than overflow -- nothing said so.

    Any future override of that column has the same hole, so the rule is
    the general one: if you out-specify the shared label column, restore
    its collapse yourself.
    """
    overrides = set(re.findall(r"(#[\w-]+) \.row > \.lab \{", CSS))
    assert overrides, "no id override of the shared label column found at all"

    body = "\n".join(CSS[lo:hi] for lo, hi in _media_spans(720))

    for host in sorted(overrides):
        assert f"{host} .row > .lab" in body, (
            f"{host} out-specifies the shared label column but never "
            f"restores its collapse below 720px"
        )


def test_the_empty_continuation_collapse_never_swallows_a_control():
    """The blank-continuation-row rule hid a button for an entire release.

    `.settings .row:has(> .lab:empty)...:has(> .hint:empty)` exists to stop
    a status slot that is blank on most installs from spending a line. The
    row holding `Apply to open previews` has exactly that shape -- an empty
    `.lab`, and a `.hint` that settings.js only fills in AFTER the button
    has been clicked -- so the rule hid the control until you had performed
    the action the control was the only route to.

    Both halves were individually correct, which is why nothing caught it:
    the CSS is right about blank rows, the markup is right about a silent
    status slot, and nothing in this suite renders the page, so the two
    only met on a real machine. This is the failure class DESIGN.md opens
    with, arriving through CSS rather than through a handler name.

    The predicate is pinned rather than the one row, because the row is not
    special -- any future pairing of a control with a status slot that
    starts empty walks into the same rule.
    """
    collapse = [
        part.strip()
        for sel in re.findall(r"([^{}]*\.lab:empty[^{}]*)\{[^{}]*display:\s*none", CSS)
        for part in sel.split(",")
        # The ROW collapse only. `.settings .row > .lab:empty` hides the
        # empty label itself and is a different rule with a different job:
        # it takes a label out of the layout, never a control.
        if ".row:has(> .lab:empty)" in part
    ]
    assert collapse, "the empty-continuation collapse rule is gone entirely"

    for sel in collapse:
        for control in ("button", "input", "select"):
            assert f":not(:has(> {control}))" in sel, (
                f"the collapse selector {sel.strip()!r} does not exclude "
                f"<{control}>, so a row pairing a control with a status "
                f"slot that starts empty is hidden until it is used"
            )

    # The subject the rule was written against, so this test keeps a
    # reason to exist rather than guarding a shape nothing has any more.
    assert 'id="btn-preview-apply-size"' in HTML, (
        "Apply to open previews is gone; if that was deliberate, this "
        "test needs a new subject, not deleting"
    )


def test_each_keybind_list_declares_a_deliberate_first_track():
    """Round 3's B1 made both bind lists stack the name above its controls,
    because each list's first track was `max-content` over ITS OWN labels
    and the bind button sat 103.4 CSS px apart in two sections of one
    screen -- Previews' half moving between sessions, because the track
    followed whoever was logged in.

    THAT RULE IS RETIRED, deliberately, and this is what replaced it. The
    two lists differ in content: Bookmarks' longest label is "Convert
    EvE-Scout Bookmarks" at 189.6px and needs its own line, while character
    names are uniform and short enough for a column. Only four ungrouped
    Bookmarks rows were ever in the shared grid anyway -- round 5's C8 moved
    the other fourteen into .bind-dense, which is flex and shares no tracks.

    What still has to hold is that neither list gets there by accident. A
    `max-content` first track is the original bug; each list must declare
    either a fixed track or a spanning label, and say which.

    Read over EVERY `.lab` override a host declares, not the first one the
    file happens to contain. Both hosts carry two: the override itself and
    the `max-width: 720px` restore that hands the name a whole line at a
    narrow width -- required by
    test_an_id_override_of_the_label_column_still_collapses_at_the_floor
    and deliberately not re-checked here. A first-match read would make
    this test's answer depend on which of the two comes first in the
    stylesheet, so swapping two rule blocks -- an edit with no visible
    effect at any width this window can reach, since the CSS floor is
    840x625 -- would flip it silently. That is precisely the failure a
    lexical guard exists to prevent, so the property is asserted over the
    non-media blocks as a set.
    """
    narrow = _media_spans(720)

    for host, expected in (("#eve-binds", "span"), ("#preview-binds", "fixed")):
        m = re.search(re.escape(host) + r" \{(.*?)\}", CSS, re.DOTALL)
        assert m, f"{host} has no rule block"
        template = re.search(r"grid-template-columns:([^;]*);", m.group(1))
        assert template, f"{host} declares no grid-template-columns"
        first = template.group(1).strip().split()[0]
        assert not first.startswith("max-content"), (
            f"{host}'s first track is max-content over its own labels, "
            f"which is round 3's B1 -- the bind button moves with the "
            f"content and, in Previews, between sessions"
        )
        blocks = [
            b
            for b in re.finditer(
                re.escape(host) + r" \.row > \.lab \{(.*?)\}", CSS, re.DOTALL
            )
            if not any(lo <= b.start() < hi for lo, hi in narrow)
        ]
        assert blocks, f"{host} no longer overrides the shared label column"
        spans = any("grid-column: 1 / -1" in b.group(1) for b in blocks)
        assert spans == (expected == "span"), (
            f"{host}'s label {'spans' if spans else 'sits in a track'} at "
            f"full width, which is not what this list decided: Bookmarks "
            f"spans for its 189.6px labels, Previews takes a fixed column "
            f"for its names"
        )


# ---- the [hidden] trap -------------------------------------------------


def test_every_hidden_element_can_actually_hide():
    """An author rule beats the UA stylesheet's [hidden] { display: none }
    regardless of specificity, because author origin outranks UA origin.
    So any selector that sets a display needs its own [hidden] override or
    the element stays visible when hidden is set.

    style.css documents this trap in six separate places, which is six
    times someone nearly shipped it. This is the check that makes the
    seventh unnecessary.
    """
    body = _strip_html_comments(HTML)

    # Selectors that set a display, and the ones that opt back out.
    sets_display = set()
    for rule in re.finditer(r"([^{}]+)\{([^{}]*)\}", CSS):
        selector, block = rule.group(1).strip(), rule.group(2)
        if not re.search(r"(?m)^\s*display\s*:", block):
            continue
        if "[hidden]" in selector:
            continue
        for part in selector.split(","):
            part = part.strip()
            if re.fullmatch(r"[.#][\w-]+", part):
                sets_display.add(part)

    guarded = set()
    for rule in re.finditer(r"([^{}]+)\{([^{}]*)\}", CSS):
        selector = rule.group(1).strip()
        if "[hidden]" not in selector:
            continue
        for part in selector.split(","):
            part = part.strip()
            m = re.fullmatch(r"([.#][\w-]+)\[hidden\]", part)
            if m:
                guarded.add(m.group(1))

    problems = []
    for tag in re.finditer(r"<(\w+)([^>]*\bhidden\b[^>]*)>", body):
        attrs = tag.group(2)
        names = (
            [
                "." + c
                for c in (re.search(r'class="([^"]*)"', attrs) or re.match("", ""))
                .group(1)
                .split()
            ]
            if re.search(r'class="([^"]*)"', attrs)
            else []
        )
        ident = re.search(r'id="([^"]*)"', attrs)
        if ident:
            names.append("#" + ident.group(1))
        for name in names:
            if name in sets_display and name not in guarded:
                problems.append((tag.group(0)[:60], name))

    assert not problems, (
        "these carry `hidden` but their own rule sets a display, so they "
        "stay visible: " + repr(problems)
    )


# ---- one accent per screen ---------------------------------------------


def test_no_container_offers_two_primary_actions():
    """`.btn.acc` is documented as "the ONE brand-accent control on any
    screen". Two of them is two things claiming to be the primary action.

    Zero is allowed and is not checked: a screen that applies immediately
    has no commit action to accent, which is true of several now.
    """
    body = _strip_html_comments(HTML)
    # The dialog layer is excluded: it floats OVER whichever screen is
    # showing rather than belonging to one, and panel.js accents its OK
    # button only for a confirm. Two accents on screen at once is real
    # there, and deliberate -- the overlay dims the page behind it, so it
    # reads as layering rather than as two competing primaries.
    body = re.sub(
        r'<div id="dialog-slot">.*?</div>\s*</div>\s*</div>', "", body, flags=re.DOTALL
    )
    containers = re.split(r'(?=<div class="route"|<div class="settings")', body)
    for chunk in containers:
        ident = re.search(r'id="([\w-]+)"', chunk)
        count = len(re.findall(r'class="btn acc"', chunk))
        assert count <= 1, (
            f"{ident.group(1) if ident else '?'} has {count} accent buttons"
        )


def test_accent_hover_restates_its_own_fill_and_label():
    """`button.btn.acc:hover:not(:disabled)` and
    `button.btn:hover:not(:disabled)` are BOTH (0,3,1), so the accent's
    hover wins only on source order and only for the properties it names.

    Both halves have already failed in the shipped app. The accent rule
    used to declare `filter` alone, so the generic rule supplied the
    background and hovering the Upload button replaced the brand gradient
    with the flat grey fill -- through two accent colours, because nothing
    in this suite renders the page. Omitting `color` fails the same way
    more quietly: the generic rule's --text lands on the brightened
    gradient at 3.84:1, under the 4.5:1 floor.
    """
    generic = CSS.index("button.btn:hover:not(:disabled)")
    accent = CSS.index("button.btn.acc:hover:not(:disabled)")
    assert generic < accent, (
        "the accent hover rule must stay BELOW the generic one -- equal "
        "specificity means it wins on order alone"
    )
    block = CSS[accent : CSS.index("}", accent)]
    for prop in ("background", "color"):
        assert re.search(rf"\b{prop}\s*:", block), (
            f"button.btn.acc:hover must restate {prop}: the generic button "
            f"hover rule sets it at the same specificity and would win it"
        )


def test_an_armed_bind_and_a_clashing_one_do_not_fight_over_one_channel():
    """`.bindbtn.capturing` and `.bindbtn.clash` are both (0,2,0) and both
    set `border-color` and `color`, so a row that is BOTH used to render
    whichever came last -- which was clash, so an armed row showed no sign
    of being armed. That state is modal: the next keystroke is captured
    rather than delivered. Round 5's D7.

    The repair is `.bindbtn.clash.capturing`, which is (0,3,0) and so wins
    both properties outright regardless of where the two single-class rules
    sit. What it must declare is DERIVED from them rather than retyped:
    arming's border colour and clash's label colour, which is the split D7
    decided. Retyping either would let this test agree with itself while
    disagreeing with the sheet.
    """

    def decl(selector, prop):
        i = CSS.index(selector + " ")
        block = CSS[i : CSS.index("}", i)]
        # (?<![-\w]) rather than \b: a hyphen is a non-word character, so
        # \bcolor happily matches the tail of `border-color` and the first
        # draft of this test read arming's border into clash's label.
        m = re.search(rf"(?<![-\w]){prop}\s*:\s*([^;}}]+)", block)
        assert m, f"{selector} no longer declares {prop}"
        return m.group(1).strip()

    combined = ".bindbtn.clash.capturing"
    assert combined in CSS, (
        "a bind can be armed and clashing at once; without a combined rule "
        "the two equal-specificity blocks decide it on source order"
    )
    assert decl(combined, "border-color") == decl(
        ".bindbtn.capturing", "border-color"
    ), (
        "arming owns the border: it is the only channel here that clears "
        "the 3:1 that 1.4.11 asks of a non-text indicator"
    )
    assert decl(combined, "color") == decl(".bindbtn.clash", "color"), (
        "the clash mark keeps the label -- if it yielded, clicking a "
        "clashing row would clear the red and read as resolved"
    )


# ---- reachability ------------------------------------------------------


def test_every_destination_and_section_is_reachable_and_exists():
    """A container with no control never shows; a control with no container
    shows an empty pane. Both halves have to exist, and nothing else in the
    suite reads the page for this.
    """
    body = _strip_html_comments(HTML)
    app = _strip_js_comments((WEB / "app.js").read_text(encoding="utf-8"))

    routes = set(re.findall(r'id="route-([\w-]+)"', body))
    nav = set(re.findall(r'data-route="([\w-]+)"', body))
    # firstrun and settings are reached in code, not from the nav.
    assert nav <= routes, f"nav points at missing routes: {nav - routes}"
    for name in nav:
        assert f"{name}: 'route-{name}'" in app, (
            f"{name} has a nav button but no entry in WM.route's map"
        )

    sections = set(re.findall(r'id="section-([\w-]+)"', body))
    rail = set(re.findall(r'data-section="([\w-]+)"', body))
    assert rail == sections, (
        f"rail and sections disagree: only in rail {rail - sections}, "
        f"only in markup {sections - rail}"
    )


def test_the_formation_editor_offers_no_other_exit_while_editing():
    """The editor's own back button must be the ONLY way off #route-formations.

    The editor holds unsaved edits and confirms before discarding them --
    but only on its own back button. #routenav and the gear are chrome:
    they sit above every route, call WM.route directly, and know nothing
    about `state.dirty`. So with the nav visible there were five exits and
    four of them threw the edits away in silence, the next
    WM.openFormations reloading over them with no `protect`.

    The remedy is one place, in WM.route: decide the chrome's visibility
    per route, and hide it on `formations` exactly as `firstrun` already
    does (which is nothing more than the same rule -- a screen you cannot
    leave sideways). Pinned here because the two lines are three words
    apart and a later route added to one is easily left out of the other.
    """
    app = _strip_js_comments((WEB / "app.js").read_text(encoding="utf-8"))

    declared = re.search(r"WM\.CHROMELESS_ROUTES = \[([^\]]*)\]", app)
    assert declared, "app.js no longer declares WM.CHROMELESS_ROUTES"
    chromeless = set(re.findall(r"'([\w-]+)'", declared.group(1)))
    assert {"firstrun", "formations"} <= chromeless, (
        "chrome stays up on "
        f"{sorted({'firstrun', 'formations'} - chromeless)} -- a route you must "
        "not leave sideways cannot offer buttons that leave it"
    )
    # Both exits, decided from the one list. A gear hidden while the nav
    # stayed up would still leak four destinations.
    for element in ("btn-settings", "routenav"):
        assert f"WM.el('{element}').hidden = chromeless;" in app, (
            f"#{element}'s visibility no longer follows WM.CHROMELESS_ROUTES"
        )


def test_the_landing_section_is_one_fact_not_three():
    """`WM.current_section` and the visibly active section must agree.

    Settings' landing section is written in three places: the initial value
    of WM.current_section (web/app.js), the `active` class on a rail item,
    and the `active` class on a pane. They disagreed -- markup painted
    General while app.js announced `account` -- and nothing noticed, because
    no current listener acts on a section name other than its own.

    Latent rather than live, which is exactly why it needs a test. DESIGN.md
    makes section entry the FETCHING contract ("Route and section entry is
    how screens fetch"), so the first section that fetches on entry and is
    not Bookmarks or Previews would fetch for a pane the user is not looking
    at, or fail to fetch for the one they are. DESIGN.md's own remedy for a
    fact written more than once is this: "Derive it, or assert it in a test."
    """
    body = _strip_html_comments(HTML)
    app = _strip_js_comments((WEB / "app.js").read_text(encoding="utf-8"))

    declared = re.findall(r"WM\.current_section\s*=\s*'([\w-]+)'", app)
    assert declared, "app.js no longer declares an initial WM.current_section"
    landing = declared[0]

    rail = re.findall(r'rail-item active" data-section="([\w-]+)"', body)
    pane = re.findall(r'settings active" id="section-([\w-]+)"', body)

    # Exactly one of each: two active rail items paint two selected tabs,
    # and two active panes stack both groups' cards in one column.
    assert rail == [landing], f"app.js lands on {landing!r}, the rail marks {rail!r}"
    assert pane == [landing], f"app.js lands on {landing!r}, the panes mark {pane!r}"


def test_settings_does_not_land_on_the_switch_that_removes_the_product():
    """General's entire content is one checkbox for turning the EVE half
    off. It is a legitimate control and a poor landing: the least-used
    switch on the screen, in the most prominent pane of the app's
    configuration surface, framing Settings as "here is how to remove
    things". Pinned so it is not quietly moved back.
    """
    app = _strip_js_comments((WEB / "app.js").read_text(encoding="utf-8"))
    declared = re.findall(r"WM\.current_section\s*=\s*'([\w-]+)'", app)
    assert declared[0] != "general"


def test_settings_section_scripts_load_after_app_js():
    """Section modules reach through the WM bootstrap app.js defines.

    A section script loaded before app.js sees no WM to register against and
    dies during parse-time setup; in this stack that means a blank inert
    screen rather than a visible failure. Task 7's Characters shell is the
    new case and the page order is the only place that guarantees it.
    """
    scripts = re.findall(r'<script src="([^"]+)"></script>', HTML)
    assert "app.js" in scripts
    assert "characters.js" in scripts
    assert scripts.index("app.js") < scripts.index("characters.js")


def test_opening_a_dialog_disarms_an_armed_keybind_capture():
    """A module that captures keystrokes must disarm before raising an
    in-page dialog.

    The capture handler is document-level and preventDefault()s EVERY key,
    Tab included. While these prompts were window.prompt it did not matter:
    a native OS dialog takes input outside the page. WM.prompt is an
    in-page field, so an armed capture swallows everything typed into it --
    arm a capture on one bind, press Edit… on another, and the dialog opens
    dead.

    previews.js always disarmed here; bookmarks.js did not, and the
    conversion turned that difference into a bug.
    """
    for name in ("bookmarks.js", "previews.js"):
        src = _strip_js_comments((WEB / name).read_text(encoding="utf-8"))
        assert "endCapture" in src, f"{name} has no capture to disarm?"
        for match in re.finditer(r"WM\.prompt\(", src):
            # The handler that raises it must disarm somewhere above.
            before = src[max(0, match.start() - 400) : match.start()]
            assert "endCapture()" in before, (
                f"{name} raises WM.prompt without disarming an armed capture first"
            )


def test_no_colour_is_decided_outside_the_root_token_block():
    """Every hex colour in style.css lives in :root.

    DESIGN.md and CLAUDE.md have both stated this all along, and it was
    broken the whole time: the vermilion-to-purple retheme moved --brand
    and left 72 hex literals sitting in rules further down, so the tokens
    went violet and the surfaces they describe did not. What that looked
    like on screen was .list-head -- a `#101216` blue-grey band welded to
    the top of a violet list, on the first screen the app opens (round 3,
    finding 7). Nothing caught it, because nothing was looking.

    The count is DERIVED, not retyped: the assertion is "none", so a new
    literal fails here rather than drifting a number in a docstring.

    Comments are already stripped from CSS at the top of this module, so a
    literal QUOTED IN A COMMENT is fine and several are -- the notes on
    --brand-text and --link name the values they are explaining.
    """
    root = re.search(r":root\s*\{(.*?)\n\}", CSS, flags=re.DOTALL)
    assert root, "style.css has no :root block?"
    rules = CSS[: root.start()] + CSS[root.end() :]
    stray = re.findall(r"#[0-9a-fA-F]{3,8}\b", rules)
    assert not stray, (
        "colour decided outside :root: "
        + ", ".join(sorted(set(stray)))
        + " -- add a token instead (L1 owns :root; see finding 7)"
    )

    # And the same colours written as channels. The regex above reads `#hex`
    # ONLY, which is not the syntax a glow can be written in: box-shadow
    # needs an alpha and CSS cannot take one from a hex token, so five rules
    # carried `rgba(132, 48, 217, ...)` -- --brand, hand-copied, invisible to
    # the assertion directly above it. Exactly the drift this test exists to
    # stop, in the one form it could not see.
    #
    # Matched on VALUE, not on syntax: a bare `rgb(` ban would fire on the
    # legitimate neutrals (rgba(0,0,0,.5) shadows, transparent gradient
    # stops), which decide nothing about the brand. So :root's own hex
    # tokens are parsed to channel triples and only those are forbidden
    # below -- which also means a NEW token is protected the moment it is
    # added, with nothing here to update.
    tokens = {}
    for name, value in re.findall(r"(--[\w-]+):\s*#([0-9a-fA-F]{6})\b", root.group(1)):
        v = value.lower()
        tokens[(int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16))] = name

    copied = []
    for chans in re.findall(r"rgba?\(\s*(\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3})", rules):
        triple = tuple(int(c.strip()) for c in chans.split(","))
        if triple in tokens:
            copied.append(f"rgb{triple} == var({tokens[triple]})")
    assert not copied, (
        "a :root token's value is hand-copied as channels outside :root: "
        + ", ".join(sorted(set(copied)))
        + " -- add a `--x-rgb: r g b` token and use rgb(var(--x-rgb) / a), "
        + "the way --brand-rgb does, so moving the token moves these too"
    )


def test_the_type_scale_comment_still_describes_the_type_scale():
    """:root's type-scale note prints a size-and-ratio table. Check it.

    Round 5 (G3) asked for the scale to be stated with its ratios so a
    screen's hierarchy is a decision on the record rather than five loose
    numbers. A table in a comment is exactly the hand-kept copy CLAUDE.md
    says must be derived or asserted -- four places once carried a count
    of the bookmark binds and three of them were wrong.

    So the RATIOS ARE THE FIXTURE and the tokens are the truth: this
    parses the table out of the comment and recomputes every row against
    the values below it. Changing a token without touching the table
    fails here, which is the drift that matters -- the table is what a
    reader trusts, and nothing else in the suite reads it.

    Also pinned: --fs-muted stays UNDER --fs-body and --fs-label stays
    under --fs-muted. That ordering is the "column headers label the data,
    they are not the data" decision the note argues at length, and raising
    --fs-muted to 12px in round 5 is exactly the change that could have
    quietly ended it.
    """
    root = re.search(r":root\s*\{(.*?)\n\}", RAW_CSS, flags=re.DOTALL)
    assert root, "style.css has no :root block?"
    block = root.group(1)

    tokens = {
        name: float(value)
        for name, value in re.findall(r"(--fs-[\w-]+):\s*([\d.]+)px;", block)
    }
    assert tokens, "no --fs-* tokens found in :root"

    # `--fs-head   17px   1.31 over body    h1 x2, .dialog h3`
    rows = re.findall(
        r"^\s*(--fs-[\w-]+)\s+([\d.]+)px\s+"
        r"(?:--\s|([\d.]+)\s+(over|under|of)\s+(body|muted)\b)",
        block,
        flags=re.MULTILINE,
    )
    assert len(rows) == len(tokens), (
        f"the type-scale table lists {len(rows)} sizes but :root declares "
        f"{len(tokens)} --fs-* tokens: {sorted(tokens)}"
    )

    for name, stated_px, ratio, direction, against in rows:
        assert name in tokens, f"{name} is in the table but not in :root"
        assert float(stated_px) == tokens[name], (
            f"the table says {name} is {stated_px}px; :root says {tokens[name]}px"
        )
        if not ratio:  # the `--` row: the size everything else is relative to
            continue
        base = tokens[f"--fs-{against}"]
        computed = {
            "over": tokens[name] / base,
            "of": tokens[name] / base,
            "under": base / tokens[name],
        }[direction]
        assert round(computed, 2) == float(ratio), (
            f"the table says {name} is {ratio} {direction} --fs-{against}; "
            f"{tokens[name]}px against {base}px is {computed:.2f}"
        )

    assert tokens["--fs-muted"] < tokens["--fs-body"], (
        "--fs-muted reached --fs-body -- column headers are no longer below "
        "the data they label, which is the decision the :root note defends"
    )
    assert tokens["--fs-label"] < tokens["--fs-muted"], (
        "--fs-label reached --fs-muted -- the uppercase section labels are "
        "no longer a step below the muted text, which is what --fs-label's "
        "own note claims"
    )


def test_every_comment_in_the_stylesheet_opens_and_closes_exactly_once():
    """A stray `*/` silently deletes the rule that follows it.

    This sheet is mostly comment by volume, and its comments are edited
    far more often than its declarations. Replace a comment's tail and
    leave the old `*/` behind and you get two closers: the comment ends at
    the first, the prose after it becomes a qualified-rule PRELUDE, CSS
    error recovery reads that prelude up to the next `{` — which is the
    real selector — and drops the whole block as invalid.

    That happened on this branch to `.pv-master`. The symptom was not a
    parse error anywhere: `.pv-master > .row` on the following line still
    applied, so the block kept exactly enough styling to look deliberate
    while its display, gap, padding and border were all gone.

    NOTHING ELSE HERE CAN SEE IT. Every other guard in this file reads the
    sheet lexically — they match selectors and declarations as text, and
    text is exactly what a dropped rule still is. Only the browser knows,
    and no test starts one.

    Checks the property directly rather than counting: `/*` and `*/` in
    equal numbers is true of the broken file too (the stray closer came
    with a real opener elsewhere). What has to hold is that a closer never
    appears while the scanner is outside a comment, and that the file does
    not end inside one. CSS comments do not nest, so a `/*` seen while
    already inside one is content, not a second opener.

    The second assertion catches the OTHER half, which the first cannot
    see: DELETE a closer instead of adding one and the tokens still
    balance, because the comment simply runs on to the next comment's
    closer and eats every rule in between. The tell is a rule opening at
    column 0 inside a comment body. Every comment in this sheet is
    indented, including the many that quote CSS at themselves, so a
    selector starting hard against the left margin is never comment text.
    """
    css = (WEB / "style.css").read_text(encoding="utf-8")

    i, line, in_comment, opened_at = 0, 1, False, None
    swallowed = []
    at_line_start = True
    while i < len(css):
        if css[i] == "\n":
            line += 1
            i += 1
            at_line_start = True
            continue
        pair = css[i : i + 2]
        if not in_comment and pair == "/*":
            in_comment, opened_at = True, line
            i += 2
            at_line_start = False
            continue
        if in_comment and pair == "*/":
            in_comment = False
            i += 2
            at_line_start = False
            continue
        assert not (not in_comment and pair == "*/"), (
            f"style.css:{line} closes a comment that was never opened. The "
            f"CSS after it is read as a selector prelude and the next rule "
            f"is dropped whole — silently, because every guard in this file "
            f"reads the sheet as text"
        )
        # A rule opening hard against the left margin, inside a comment.
        if in_comment and at_line_start and not css[i].isspace():
            eol = css.find("\n", i)
            text = css[i : eol if eol != -1 else len(css)]
            if text.rstrip().endswith("{"):
                swallowed.append((line, text.strip()[:60], opened_at))
        at_line_start = False
        i += 1

    assert not in_comment, (
        f"style.css: the comment opened at line {opened_at} is never closed, "
        f"so everything after it is swallowed"
    )
    assert not swallowed, (
        "these rules open at column 0 INSIDE a comment, which means a "
        "comment's closer was deleted and the comment now runs on and eats "
        "them: "
        + "; ".join(
            f"style.css:{ln} {sel!r} (swallowed by the comment opened at line {opened})"
            for ln, sel, opened in swallowed
        )
    )


def test_the_uppercase_tracked_labels_split_headings_from_sub_labels():
    """Four rules carry the `.14em` uppercase treatment. Two ranks, not one.

    Round 5's G3 came in two parts. The type-scale lane moved --fs-muted;
    the card-titles lane moved two CONSUMERS -- `.card > h2` and
    `.rail-head`, the app's two uppercase tracked headings -- from
    --fs-label up to --fs-body, because a heading set below the prose
    beneath it gives a screen no skimmable skeleton. The other two rules
    are subordinate and stayed: `.bind-group-name` is a divider inside a
    card and `.alert-head > span` is a column header.

    This is asserted rather than left to the comments because the four
    rules LOOK like one pattern implemented four times, and the obvious
    tidy-up -- "these should all be the same size" -- is exactly the
    regression. The split is the decision. The `.14em` treatment is what
    they still share, so that is pinned too: a fifth rule joining the
    group has to choose a rank, and a rule leaving --fs-body silently is
    what this catches.

    Derived from the sheet, not retyped: the group is found by grepping
    for the tracking, so adding a rule to it cannot skip the check.

    The pattern is deliberately looser than the four selectors it expects,
    because the failure that matters here is a SILENT one -- a fifth rule
    the grep cannot see passes this test while breaking the rank. So it
    accepts a leading indent (a rule nested in a media query, and also any
    rule whose preceding comment was just stripped), a bare element
    selector, and the `0.14em` spelling, none of which an anchored
    `\\n[.#]...\\.14em` would have matched. Known and accepted gap: a
    selector list split across lines is captured by its last line only.
    That still fails the set comparison below rather than passing quietly,
    which is the property being bought.
    """
    group = re.findall(
        r"(?m)^[ \t]*([^\n{}@/][^\n{}]*?)\s*\{"
        r"([^{}]*letter-spacing:\s*0?\.14em[^{}]*)\}",
        CSS,
    )
    # Counted BEFORE the dict: two rules sharing a selector collapse to one
    # key, and "four keys" would then be true of a sheet with five rules.
    assert len(group) == 4, (
        "expected exactly four rules carrying the .14em uppercase treatment, "
        f"found {len(group)}: {sorted(sel.strip() for sel, _ in group)} -- a "
        "new one must pick a rank (see .card > h2's comment) and be added here"
    )
    selectors = {sel.strip(): body for sel, body in group}

    headings = {".card > h2", ".rail-head"}
    sub_labels = {".bind-group-name", ".alert-head > span"}
    assert set(selectors) == headings | sub_labels, (
        f"the .14em group is {sorted(selectors)}, expected "
        f"{sorted(headings | sub_labels)}"
    )

    for sel in sorted(headings):
        assert "font-size: var(--fs-body)" in selectors[sel], (
            f"{sel} is a HEADING and must stay at --fs-body: it heads prose "
            "and rail entries that are themselves --fs-body, and --fs-label "
            "put it below them. See .card > h2's comment for why --fs-head "
            "was the wrong token to reach for instead"
        )
    for sel in sorted(sub_labels):
        assert "font-size: var(--fs-label)" in selectors[sel], (
            f"{sel} is SUBORDINATE to a card heading -- a divider or a "
            "column header -- and must stay at --fs-label. Raising it to "
            "match the headings is the tidy-up that erases the rank"
        )
    for sel, body in selectors.items():
        assert "text-transform: uppercase" in body, (
            f"{sel} carries .14em tracking without uppercase; the two are "
            "one treatment and tracking alone reads as a spacing bug"
        )


def test_nothing_hides_itself_with_an_inline_display_style():
    """There are two hiding mechanisms and there must not be a third.

    `hidden` is the one the page uses, and test_every_hidden_element_can
    _actually_hide above checks that anything carrying it has an
    author-rule override wherever its own selector sets a display -- the
    trap DESIGN.md names in six places.

    Five elements hid with `style="display:none"` plus `el.style.display =
    'none' | ''` instead. They WORKED, which is why nothing noticed: .hint
    sets no display, so nothing had to be overridden. What they were not
    was covered -- the guard above inspects the `hidden` attribute, so an
    inline-styled element is invisible to it, and two of the five were in
    the Alerts card. Give .hint a display one day and the guard would stay
    green while those five stopped hiding.

    Both halves are pinned: the attribute in markup, and the property in
    the modules, so a module cannot reintroduce it on an element that
    starts out correct.

    Both checks are pattern-based rather than literal-substring, and the
    module list is derived rather than hand-kept. The original form of
    this test matched only the one exact spelling `style="display:none"`
    (no space after the colon, that one value, double quotes) and a bare
    `.style.display` substring, and named eleven modules by hand --
    missing `fittings.js` outright and blind to `style="display: none"`,
    single-quoted markup, a combined `style="color:red;display:none"`
    attribute, bracket-notation (`el.style['display']`), and
    `el.style.setProperty('display', ...)`, every one of which hides an
    element exactly as invisibly to the [hidden] guard as the five this
    test was written to catch.
    """
    inline_display = re.search(
        r"""style\s*=\s*(['"])(?:(?!\1).)*?\bdisplay\s*:""",
        _strip_html_comments(HTML),
        re.IGNORECASE,
    )
    assert inline_display is None, (
        "an element hides with an inline display style "
        f"({inline_display.group(0)!r}); use the `hidden` attribute so "
        "test_every_hidden_element_can_actually_hide sees it"
    )
    js_display_write = re.compile(
        r"""\.style(?:\.display\b|\s*\[\s*['"]display['"]\s*\]|\s*\.\s*setProperty\s*\(\s*['"]display['"])"""
    )
    for path in sorted(WEB.glob("*.js")):
        if path.name == "dev.js":
            continue  # the one file allowed to fabricate/poke internal state
        src = _strip_js_comments(path.read_text(encoding="utf-8"))
        match = js_display_write.search(src)
        assert match is None, (
            f"{path.name} hides an element by writing style.display "
            f"({match.group(0)!r}); set `el.hidden` instead so the "
            f"[hidden] guard covers it"
        )


def test_a_readiness_state_is_not_painted_in_the_error_colour():
    """`Missing` / `Not trained` are facts about a character, not failures.

    C2 settled this for `Unknown skill`; round 3's S3 found the same
    mistake still shipping on five rules, where --err painted a readiness
    state, a group swatch AND `Forget character` -- the control that
    deletes the character -- in one colour, about 130 CSS px apart. The
    readiness ramp now ends in --unmet and destructive controls carry
    --danger, so no one token means all three.

    The check is over every `.key-` / `.status-` / `.state-` rule there IS
    rather than a list of names. R3's S2 deleted three of them -- the row
    no longer restates its group, so `.status-Unknown`, `.status-Ready` and
    `.status-Locked` paint nothing -- and a hand-kept list turns a correct
    deletion into a failure that reads as "the classes moved". What must
    hold is a property of the whole family, and the two rungs that were
    actually wrong are pinned by name below.
    """
    painted = re.findall(r"\.((?:key|status|state)-\w+)\s*\{([^}]*)\}", CSS)
    assert painted, "the readiness classes are gone entirely -- did they move?"
    for cls, body in painted:
        assert "var(--err)" not in body, (
            f".{cls} paints a readiness state in --err; it belongs on --unmet"
        )

    # The two S3 named, on the two surfaces that still render them.
    named = {cls for cls, _ in painted}
    for cls in ("key-Missing", "key-Unknown", "state-Missing", "state-Unknown"):
        assert cls in named, f".{cls} is gone -- did the readiness classes move?"


def test_the_training_states_do_not_reuse_the_outbound_link_colour():
    """--link means "this leaves the application" and nothing else.

    After the purple retheme it was the only blue left, and the three
    training states were a bare `#7aa2f7` -- which is EXACTLY --link's
    value, so blue meant both "follow this out of the app" and "this skill
    is queued", and the queued one is not clickable (round 3, S5). --link
    could not move: it carries a legal obligation to be followed and its
    own note says so. The states moved, to --training.
    """
    root = re.search(r":root\s*\{(.*?)\n\}", CSS, flags=re.DOTALL)
    values = dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", root.group(1)))
    assert values["--training"].strip() != values["--link"].strip(), (
        "--training and --link hold the same value again; that collision is S5"
    )
    for cls in ("key-Training", "status-Training", "state-Queued"):
        rule = re.search(r"\." + cls + r"\s*\{([^}]*)\}", CSS)
        assert rule, f".{cls} is gone -- did the training classes move?"
        assert "var(--link)" not in rule.group(1), (
            f".{cls} paints a training state in --link, the outbound-link token"
        )


# ---- the control vocabulary --------------------------------------------


def test_every_action_control_shares_one_disabled_state():
    """Round 3's B2 asked for one shared disabled state and found three
    answers plus two omissions.

    `.linkbtn` and `.bindbtn` had no `:disabled` rule at all, and their
    `:hover` rules did not exclude `:disabled` either -- so a control the
    page had switched off still lifted its background under the pointer
    and still looked live. That is the exact state B2 wants `Clear` put
    into on a keybind reading `Not set`, so the omission was on the path
    of its own fix.

    Both halves are checked: one declaration covers all four selectors,
    and no hover rule for any of them can fire while disabled.
    """
    controls = ("button.btn", ".linkbtn", ".bindbtn", ".ctxmenu button")

    disabled = [
        block
        for block in re.findall(r"([^{}]+)\{([^}]*)\}", CSS)
        if all(f"{c}:disabled" in block[0] for c in controls)
    ]
    assert disabled, (
        "no single rule disables all of "
        + ", ".join(controls)
        + " -- one disabled state means one declaration, not four"
    )
    body = disabled[0][1]
    for prop in ("opacity", "cursor"):
        assert re.search(rf"\b{prop}\s*:", body), (
            f"the shared disabled rule does not set {prop}"
        )

    for control in controls:
        hovers = list(
            re.finditer(re.escape(control) + r"[^,{}]*:hover([^,{}]*)[,{]", CSS)
        )
        # Asserted rather than assumed: this loop is the whole second half
        # of the check, and deleting the rule it inspects would otherwise
        # make it pass by matching nothing -- which is precisely the state
        # `.linkbtn` and `.bindbtn` were in when B2 was written.
        assert hovers, f"{control} has no :hover rule left to check"
        for hover in hovers:
            assert ":not(:disabled)" in hover.group(1), (
                f"{control}:hover can fire on a disabled control -- a dead "
                f"button that lights up under the pointer is B2's own bug"
            )


def test_shared_focus_and_selected_rail_states_stay_distinct():
    """Selection owns the rail fill; keyboard focus is an outline only.

    The group manager bypasses the shared button selector because its
    interactive summary is not a button. It once referenced undefined
    `--focus`, so keyboard focus had no authored indicator at all.
    """
    manager = re.search(
        r"\.preview-group-manager > summary:focus-visible\s*\{([^}]*)\}", CSS
    )
    assert manager, "the group-manager summary has no focus-visible rule"
    assert "var(--focus-ring)" in manager.group(1)
    assert "var(--focus)" not in manager.group(1)

    active = re.search(r"[^{}]*\.rail-item\.active[^{}]*\{([^}]*)\}", CSS)
    assert active and "background: var(--row-active)" in active.group(1), (
        "the selected rail item must keep the declared current-location fill"
    )
    assert "border-left-color: var(--brand)" in active.group(1), (
        "the selected rail item must keep its existing brand edge"
    )

    focus = re.search(r"([^{}]*\.rail-item:focus-visible[^{}]*)\{([^}]*)\}", CSS)
    assert focus and "outline:" in focus.group(2), (
        "the Settings rail is missing the shared keyboard focus outline"
    )
    assert "background:" not in focus.group(2), (
        "rail focus paints a competing fill instead of an outline-only state"
    )


def test_enabled_subordinate_actions_have_readable_resting_contrast():
    """Quiet actions still have to read as live before hover.

    `--text-faint` is appropriate for explanatory text, but on a compact
    row it made Clear/Edit and Skills' group actions resemble disabled
    controls. `--text-dim` keeps the documented link-button taxonomy while
    giving every enabled subordinate action, including compact Preview row
    actions, a readable resting state.
    """
    linkbtn = re.search(r"\.linkbtn\s*\{([^}]*)\}", CSS)
    assert linkbtn, "the shared .linkbtn treatment is missing"
    assert "color: var(--text-dim)" in linkbtn.group(1)
    assert "color: var(--text-faint)" not in linkbtn.group(1)


def test_the_destructive_treatment_is_a_button_and_restates_its_hover():
    """`.btn.danger` is the ONE destructive treatment (round 3, B3/S4/P2).

    Two failure modes, both already shipped elsewhere in this sheet.

    The first is `button.btn.acc`'s hover trap. It is NOT a specificity
    race -- `button.btn.danger:hover:not(:disabled)` is (0,4,1) against the
    generic rule's (0,3,1), so it wins outright, and the sibling accent
    test's source-order premise is over-stated for the same reason. What
    actually bit was declaration coverage: a hover rule that names only
    `background` lets the generic rule supply `color`, and --text on the
    filled red is the failure. So only the declarations are asserted here.

    The second is the vocabulary itself: `red text, no button` was retired.
    L5 kept `.linkbtn.danger` alive for one site, R3 converted that site
    (`Forget character`) and deleted the pair with it, so the rule now has
    no exceptions -- any `linkbtn danger` in a page module re-opens S4.
    """
    danger = CSS.index("button.btn.danger:hover:not(:disabled)")
    block = CSS[danger : CSS.index("}", danger)]
    for prop in ("background", "color"):
        assert re.search(rf"\b{prop}\s*:", block), (
            f"button.btn.danger:hover must restate {prop}: the generic "
            f"button hover rule sets it at the same specificity"
        )

    rest = re.search(r"button\.btn\.danger\s*\{([^}]*)\}", CSS)
    assert rest and rest.group(1).count("var(--danger)") == 2, (
        "button.btn.danger must take BOTH its border and its label from "
        "--danger -- an outline in one red and a label in another is not a "
        "treatment"
    )

    users = {
        path.name
        for path in sorted(WEB.glob("*.js"))
        if "linkbtn danger" in _strip_js_comments(path.read_text(encoding="utf-8"))
    }
    # Was `users <= {"skills.js"}` while R3 was outstanding, with a note
    # saying to tighten it to empty once that lane converted the site. R3
    # did, so this is that tightening -- and the CSS half is checked too,
    # because a rule with no users is an invitation to acquire one.
    assert not users, (
        "`red text, no button` is not in the control vocabulary; there is "
        f"one destructive treatment and it is .btn.danger, but found: "
        f"{sorted(users)}"
    )
    assert ".linkbtn.danger {" not in CSS, (
        "the .linkbtn.danger pair is back; R3 deleted it with its last user"
    )


def test_disabled_danger_buttons_return_to_neutral_control_tokens():
    """A disabled destructive action is unavailable, not an active warning.

    Its scoped override follows the red treatment so neutral border and
    text win, while the shared disabled declaration continues to own
    opacity and cursor for every action control.
    """
    danger = re.search(r"button\.btn\.danger\s*\{([^}]*)\}", CSS)
    disabled = re.search(r"button\.btn\.danger:disabled\s*\{([^}]*)\}", CSS)
    assert danger and disabled, "disabled danger buttons need a scoped neutral state"
    assert disabled.start() > danger.end(), "the neutral disabled state must follow red"
    assert re.search(
        r"\bborder-color\s*:\s*var\(--control-border\)\s*;", disabled.group(1)
    )
    assert re.search(r"\bcolor\s*:\s*var\(--text-faint\)\s*;", disabled.group(1))
    assert "opacity" not in disabled.group(1) and "cursor" not in disabled.group(1), (
        "danger-disabled must retain the shared opacity and cursor behavior"
    )


def test_a_destructive_confirm_does_not_take_the_accent_button():
    """The affirming button of a destructive confirm is .btn.danger.

    Round 6, P0-1. `panel.js` hard-coded `btnOk.className = isConfirm ?
    'btn acc' : 'btn'` under a comment reading "Upload is the app's only
    irreversible action". Delete and the EVE settings copy had both
    falsified that premise by the time anyone re-read it, so the dialog
    that overwrites 34 characters' settings rendered its Confirm in the
    same encouraging purple as `Upload` -- auto-focused, so it carried the
    focus ring too -- while the .btn.danger trigger that opened it sat
    behind the overlay in red.

    Three things are asserted, because the bug can come back three ways.
    """
    panel = _strip_js_comments((WEB / "panel.js").read_text(encoding="utf-8"))

    # 1. The class is chosen from item.destructive, not from isConfirm alone.
    assert "item.destructive" in panel, (
        "panel.js must read item.destructive when picking the affirming "
        "button's class; without it every confirm is .btn.acc again"
    )
    assert re.search(r"'btn danger'", panel), (
        "panel.js must be able to render the affirming button as "
        "'btn danger' -- .btn.danger is the app's one destructive treatment"
    )

    # 2. Python must be ABLE to say so, or the four workers that destroy
    #    something have no way to ask for it.
    api = (WEB.parent / "ui" / "api.py").read_text(encoding="utf-8")
    assert '"destructive": destructive' in api, (
        "_ask must put `destructive` in the onDialog payload; the page "
        "cannot read a flag that never crosses the bridge"
    )

    # 3. Every Python confirm whose body says the action is final must
    #    pass the flag. Walked with ast, NOT matched with a regex: the
    #    first version of this guard used one, matched 3 of the 4 call
    #    sites, and passed while `Confirm Copy` -- the dialog that
    #    overwrites 34 characters' settings, and the whole reason for this
    #    test -- was silently outside it. A call site is a call node.
    tree = ast.parse(api)
    seen = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not (
            isinstance(fn, ast.Attribute) and fn.attr in ("_confirm", "_eve_confirm")
        ):
            continue
        if not (isinstance(fn.value, ast.Name) and fn.value.id == "self"):
            continue
        title = (
            node.args[0].value
            if node.args and isinstance(node.args[0], ast.Constant)
            else "<computed>"
        )
        source = ast.get_source_segment(api, node) or ""
        final = (
            "cannot be undone" in source
            or "Permanently delete" in source
            or "format_eve_copy_confirm" in source
        )
        flagged = any(
            kw.arg == "destructive"
            and isinstance(kw.value, ast.Constant)
            and kw.value.value is True
            for kw in node.keywords
        )
        seen[(title, node.lineno)] = (final, flagged)

    # The count is asserted so this cannot go quiet the way the regex did.
    assert len(seen) >= 4, (
        f"expected at least 4 self._confirm/_eve_confirm call sites, "
        f"walked {len(seen)}: {sorted(seen)}"
    )
    unflagged = sorted(
        f"{title} (api.py:{line})"
        for (title, line), (final, flagged) in seen.items()
        if final and not flagged
    )
    assert not unflagged, (
        "these confirms say the action is final but do not pass "
        f"destructive=True, so their Confirm renders as .btn.acc: {unflagged}"
    )
    # And the converse, so the treatment keeps meaning something: Upload
    # is irreversible in that a video becomes public, but it destroys
    # nothing and it is the one action the Uploader exists to perform.
    upload = [
        flagged
        for (title, _), (_, flagged) in seen.items()
        if title == "Confirm Upload"
    ]
    assert upload == [False], (
        "Confirm Upload must keep .btn.acc -- a destructive treatment on "
        f"every confirm says nothing (found {upload})"
    )


def test_dialog_keyboard_behavior_follows_focus_and_contains_it():
    panel = _strip_js_comments((WEB / "panel.js").read_text(encoding="utf-8"))
    show = re.search(r"function show\(item\) \{(.*?)\n  \}", panel, re.DOTALL)
    assert show
    assert re.search(
        r"else if \(destructive\) \{\s*btnCancel\.focus\(\);", show.group(1)
    )

    document_keys = re.search(
        r"document\.addEventListener\('keydown'.*?\n  \}, true\);",
        panel,
        re.DOTALL,
    )
    assert document_keys
    assert "ev.key === 'Tab'" in document_keys.group(0)
    assert "ev.key === 'Enter'" not in document_keys.group(0)
    assert "dlgInput.addEventListener('keydown'" in panel
    assert "active.kind === 'prompt'" in panel


def test_dialog_heading_and_scrim_are_safe_exit_paths():
    html = _strip_html_comments(HTML)
    assert '<h2 id="dlg-title"></h2>' in html
    assert '<h3 id="dlg-title">' not in html
    assert re.search(r"\.dialog h2 \{", CSS)
    assert not re.search(r"\.dialog h3(?::|\s|\{)", CSS), (
        "the corrected dialog heading must retain its visual treatment"
    )

    panel = _strip_js_comments((WEB / "panel.js").read_text(encoding="utf-8"))
    assert "var scrimPressStarted = false;" in panel
    down = re.search(
        r"overlay\.addEventListener\('mousedown'.*?\n  \}\);", panel, re.DOTALL
    )
    up = re.search(
        r"overlay\.addEventListener\('mouseup'.*?\n  \}\);", panel, re.DOTALL
    )
    assert down and up, "the app-owned dialog scrim has no complete exit gesture"
    assert "scrimPressStarted = ev.target === overlay" in down.group(0)
    assert "scrimPressStarted && ev.target === overlay" in up.group(0), (
        "a drag that starts or ends inside the dialog must not dismiss it"
    )
    assert "ev.button !== 0" in up.group(0), (
        "only a primary-button scrim click may dismiss the dialog"
    )
    assert "answer(false)" in up.group(0), (
        "the scrim must cancel an answerable dialog, never affirm it"
    )


def test_dialog_restores_the_invoker_after_the_queue_empties():
    panel = _strip_js_comments((WEB / "panel.js").read_text(encoding="utf-8"))
    assert "var returnFocus = null;" in panel
    assert "var lastPageFocus = null;" in panel
    assert "returnFocus = document.activeElement;" in panel
    assert "lastPageFocus" in panel
    assert "if (queue.length)" in panel
    assert "document.contains(target)" in panel
    assert "target.focus();" in panel
    assert "button:not([hidden]):not(:disabled)" in panel


def test_confirm_dialog_accepts_a_specific_affirming_label():
    panel = _strip_js_comments((WEB / "panel.js").read_text(encoding="utf-8"))
    api = (WEB.parent / "ui" / "api.py").read_text(encoding="utf-8")
    assert "item.confirm_label || 'Confirm'" in panel
    assert '"confirm_label": confirm_label' in api


def test_choice_dialog_uses_a_labelled_select_and_cancels_safely():
    panel = _strip_js_comments((WEB / "panel.js").read_text(encoding="utf-8"))
    html = _strip_html_comments(HTML)

    assert 'for="dlg-select"' in html
    assert 'id="dlg-select"' in html
    assert "WM.choose = function" in panel
    assert "var isChoice = item.kind === 'choice';" in panel
    assert "dlgSelect.focus();" in panel
    assert "active.kind === 'choice'" in panel
    assert "dlgSelect.value" in panel

    document_keys = re.search(
        r"document\.addEventListener\('keydown'.*?\n  \}, true\);",
        panel,
        re.DOTALL,
    )
    assert document_keys
    assert "select:not([hidden]):not(:disabled)" in document_keys.group(0)
    escape = (
        document_keys.group(0)
        .split("ev.key === 'Escape'", 1)[1]
        .split("ev.key === 'Tab'", 1)[0]
    )
    assert "active.kind === 'choice'" in escape


def test_the_previews_table_names_the_configure_disclosure():
    src = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
    head = src.split("function makeHeadRow(", 1)[1].split("return row;", 1)[0]
    assert "'Configure'" in head
    assert "'Size'" not in head


def test_state_shapes_do_not_add_soft_halos_on_the_dark_surface():
    outward_halo = re.compile(r"box-shadow:\s*0 0 (?!0(?:px)?\b)")
    assert not outward_halo.search(CSS)


def test_determinate_progress_animates_transform_not_layout():
    panel = _strip_js_comments((WEB / "panel.js").read_text(encoding="utf-8"))
    bar = re.search(r"\.bar\s*\{([^}]*)\}", CSS)
    assert bar
    assert "transition: transform" in bar.group(1)
    assert "transition: width" not in bar.group(1)
    assert "bar.style.transform" in panel
    assert "bar.style.width" not in panel
    reduced = re.search(
        r"@media \(prefers-reduced-motion: reduce\) \{\s*"
        r"\.track\.indeterminate \.bar \{([^}]*)\}",
        CSS,
    )
    assert reduced and "transform: scaleX(1)" in reduced.group(1)


def test_every_offered_alert_colour_has_a_name():
    """Round 6, P2-5. The swatches carried their hex as the accessible name.

    `#4dd2ff` does not read aloud as anything, does not tell a sighted
    user what they are picking, and -- the reason it mattered -- left the
    collision note above with nothing to call the colour it is about.

    COLOUR_NAMES is indexed against COLOURS, so the pair has to stay the
    same length or a colour silently falls back to its hex. That is the
    designed behaviour for the SIXTH swatch (an out-of-palette colour from
    a hand-edited settings.json, which has no name) and a bug for the
    five, so nothing in the code can tell the two cases apart. This can.
    """
    alerts = _strip_js_comments((WEB / "alerts.js").read_text(encoding="utf-8"))

    colours = re.search(r"var COLOURS = \[(.*?)\];", alerts, re.DOTALL)
    names = re.search(r"var COLOUR_NAMES = \[(.*?)\];", alerts, re.DOTALL)
    assert colours and names, "the palette or its names are gone"

    n_colours = len(re.findall(r"'#[0-9a-fA-F]{6}'", colours.group(1)))
    n_names = len(re.findall(r"'[^']+'", names.group(1)))
    assert n_colours == 5, f"the palette is no longer five colours ({n_colours})"
    assert n_names == n_colours, (
        f"{n_colours} colours but {n_names} names: COLOUR_NAMES is indexed "
        "against COLOURS, so the extra colour would fall back to its hex "
        "and look like the out-of-palette case"
    )

    # The name is what the control announces; the hex may accompany it.
    assert "input.setAttribute('aria-label', name)" in alerts, (
        "the swatch must announce its NAME, not its hex"
    )


def test_alert_swatches_do_not_render_a_redundant_colour_name_readout():
    """Round 7. The five dots plus the accessible name on each radio (see
    test_every_offered_alert_colour_has_a_name) already say what a sighted
    user is picking; a sixth, visible "selected colour" word underneath the
    row wrapped onto its own line and made the row two lines tall, breaking
    the centerline every other control in the row (checkbox/name, Sound,
    Test) shared. The fix removes the readout entirely -- not merely hides
    it -- while keeping every accessible name in place.
    """
    alerts = _strip_js_comments((WEB / "alerts.js").read_text(encoding="utf-8"))
    assert "swatch-name" not in alerts, (
        "the dead .swatch-name readout element must be removed, not hidden"
    )
    assert "WM.make" not in alerts, (
        "alerts.js used WM.make only to build the removed readout span"
    )

    style = re.search(r"\.alert-events \.swatch-name[^{]*\{(.*?)\}", CSS, re.DOTALL)
    assert style is None, "the dead .swatch-name CSS rule must be removed too"

    # The accessible name itself must survive: every radio still announces
    # its colour by name, and the collision note still has a word to use.
    assert "input.setAttribute('aria-label', name)" in alerts, (
        "removing the visible readout must not remove the accessible name"
    )
    assert "function colourName(hex)" in alerts, (
        "colourName must survive: the collision note and the swatch tooltip "
        "both still need to name a colour"
    )


def test_alert_palette_is_one_line_with_the_rest_of_its_row():
    """Without the second-line readout, the swatches container has nothing
    left to wrap onto a line of its own -- the flex-wrap that existed only
    to host that line must go too, or a future addition could silently
    reintroduce a second line under the same now-dead hook."""
    assert not re.search(r"\.alert-events \.swatches\s*\{[^}]*flex-wrap", CSS), (
        "the swatches row no longer has a second line to wrap; flex-wrap is dead"
    )


def test_the_alert_volume_note_finishes_its_thought():
    assert re.search(
        r"alerts only interrupt for a client you are not\s+looking at\.", HTML
    )


def test_alert_event_controls_share_deliberate_box_and_text_rails():
    """Flashes and Speed used to be the fourth rail checked here -- a
    second grid line beginning at the same 48px text rail as the event
    name. Task 1 moved both out of the row entirely, into the shared
    #alert-advanced disclosure, so that rail no longer describes anything
    inside `.alert-events .alert-row`.
    `test_flash_and_speed_share_one_collapsed_advanced_disclosure` is the
    guard for where they went instead; this one keeps checking the three
    rails that are still inside the row.
    """
    event_box = re.search(
        r"\.alert-events \.alert-row > \.check \{(.*?)\}", CSS, re.DOTALL
    )
    assert event_box and "margin-left: 24px" in event_box.group(1), (
        "event boxes must align with the modifier checkbox rail"
    )

    event_head = re.search(r"\.alert-head > span:first-child \{(.*?)\}", CSS, re.DOTALL)
    assert event_head and "padding-left: 48px" in event_head.group(1), (
        "the Event header must align with event label text, not hang over its box"
    )

    message = re.search(
        r"\.alert-events \.alert-row > \.field-msg \{(.*?)\}", CSS, re.DOTALL
    )
    assert message and "padding-left: 48px" in message.group(1), (
        "an event write outcome must align with the event text it describes"
    )


def test_flash_and_speed_share_one_collapsed_advanced_disclosure():
    """Task 1. Flashes and Speed used to be a second grid line under every
    event row -- two label/select pairs beneath four tracks already tight
    at the 840 floor (`.alert-events`' own comment: "the sound column is
    the only one allowed to give"). Both are secondary to the row's
    primary decision -- is this event on, what colour, what sound, does it
    work -- so they move into one shared native `<details>` disclosure,
    collapsed by default, below the table, rather than repeating a second
    line three times.

    A row in the primary table is atomic after this: one enable box, one
    swatch group, one sound select, one Test button, and its own status
    line (still visible outside the disclosure, since a write outcome must
    stay readable without opening anything first).
    """
    events_block = re.search(
        r'<div class="alert-events">(.*?\n\s*</div>\s*\n)\s*<!-- A colour collision',
        HTML,
        re.DOTALL,
    )
    assert events_block, "the alert-events table markup has moved or been renamed"
    table = events_block.group(1)

    assert "alert-flash" not in table, (
        "Flashes/Speed still render inside the primary event table; they "
        "must move into the shared advanced disclosure so a row stays one "
        "enable box, one swatch group, one sound and one Test button"
    )
    for event in _ALERT_EVENT_IDS:
        assert f'id="alert-event-{event}-msg"' in table, (
            f"the {event} row's status line must stay in the primary table, "
            "outside the collapsed disclosure, so a write outcome stays "
            "visible without opening anything"
        )
        assert f'id="alert-event-{event}-flashes"' not in table, (
            f"{event}'s Flashes select must move out of the primary table"
        )
        assert f'id="alert-event-{event}-speed"' not in table, (
            f"{event}'s Speed select must move out of the primary table"
        )

    disclosures = re.findall(r'<details id="alert-advanced"[^>]*>', HTML)
    assert len(disclosures) == 1, (
        f"expected exactly one #alert-advanced disclosure, found {len(disclosures)}"
    )
    assert "open" not in disclosures[0], (
        "the advanced disclosure must be collapsed by default"
    )

    advanced = re.search(
        r'<details id="alert-advanced"[^>]*>(.*?)</details>', HTML, re.DOTALL
    )
    assert advanced, "the #alert-advanced disclosure markup is missing"
    body = advanced.group(1)

    summary = re.search(r"<summary>([^<]*)</summary>", body)
    assert summary and summary.group(1).strip() == "Advanced pulse behavior", (
        "the disclosure must be titled exactly 'Advanced pulse behavior'"
    )

    for event in _ALERT_EVENT_IDS:
        assert f'id="alert-event-{event}-flashes"' in body, (
            f"{event}'s Flashes select is missing from the advanced disclosure"
        )
        assert f'id="alert-event-{event}-speed"' in body, (
            f"{event}'s Speed select is missing from the advanced disclosure"
        )
        # Each row must visibly and accessibly name its event -- a named
        # group heading before the pair, not just position in a list a
        # screen reader flattens. Structural (a name element immediately
        # precedes the pair), not the display text itself, which stays
        # the checkbox label's job to own -- see alerts.js's eventLabel().
        row = re.search(
            rf'<span class="bind-group-name">[^<]+</span>\s*'
            rf'<span class="alert-flash">.*?'
            rf'id="alert-event-{event}-flashes"',
            body,
            re.DOTALL,
        )
        assert row, (
            f"{event}'s advanced row must visibly name its event immediately "
            "before its Flashes/Speed controls"
        )

    # The old grid-row alignment is gone with the row it used to sit in;
    # the disclosure lays Flashes/Speed out as a plain flex line instead.
    assert not re.search(r"\.alert-events \.alert-row > \.alert-flash \{", CSS), (
        "a grid-row rule for .alert-flash survives inside .alert-events, but "
        "it no longer renders there"
    )
    advanced_flash = re.search(
        r"\.alert-advanced-row > \.alert-flash \{(.*?)\}", CSS, re.DOTALL
    )
    assert advanced_flash and "display: flex" in advanced_flash.group(1), (
        "Flashes/Speed must still lay out as one flex line inside the disclosure"
    )


def test_advanced_select_aria_labels_start_with_their_visible_labels():
    """Each Advanced select needs its visible label plus its owning event.

    `aria-label` replaces the associated `<label>` in the accessible-name
    computation, so it starts with the same word a sighted voice-control
    user sees, then adds the event needed to distinguish three otherwise
    identical controls. This satisfies WCAG 2.5.3 Label in Name and keeps
    the spoken order consistent across Flashes and Speed.
    """
    advanced = re.search(
        r'<details id="alert-advanced"[^>]*>(.*?)</details>', HTML, re.DOTALL
    )
    assert advanced, "the #alert-advanced disclosure markup is missing"
    body = advanced.group(1)
    owners = {
        "combat": "Combat",
        "decloak": "Decloak",
        "warp_scramble": "Warp scramble",
    }

    for event in _ALERT_EVENT_IDS:
        for control in ("flashes", "speed"):
            visible = control.title()
            select = re.search(
                rf'<select class="field" id="alert-event-{event}-{control}"\s+'
                rf'aria-label="([^"]*)"',
                body,
            )
            assert select, f"{event}'s {visible} select or its aria-label is missing"
            assert select.group(1) == f"{visible}: {owners[event]}", (
                f"{event}'s {visible} select must start its accessible name "
                "with the visible label, then disambiguate it by event"
            )


def test_alert_advanced_rows_share_deliberate_fixed_columns():
    """Round 7 (Task 6). The three Advanced rows used to be independent
    flex rows: `.bind-group-name` sat beside `.alert-flash` with only a
    gap between them, so a longer name pushed its own Flashes/Speed pair
    further right than its neighbours' -- "Warp scramble" (114.75px,
    measured at the 840x625 floor) versus "Combat" (56.58px) and "Decloak"
    (62.30px). One grid over all three rows, with the rows themselves
    display:contents, is the same fix `.alert-events` and `#preview-binds`
    already apply to the identical problem.

    The name column is a measured PX width, not `max-content`: unlike
    `.alert-events`' own first track (which is deliberately max-content --
    see that rule's own comment), this one is asked to own a number rather
    than resolve today's three known strings, so a fourth, longer event
    name cannot silently resize the whole disclosure.
    """
    advanced_body = re.search(r"\.alert-advanced-body \{(.*?)\}", CSS, re.DOTALL)
    assert advanced_body, (
        "the Advanced disclosure's rows must share one grid container "
        "(.alert-advanced-body), the same technique .alert-events and "
        "#preview-binds use for identical misalignment"
    )
    body_rule = advanced_body.group(1)
    assert "display: grid" in body_rule, (
        "the Advanced rows' shared container must be a grid"
    )
    columns = re.search(r"grid-template-columns:\s*([^;]+);", body_rule)
    assert columns, "the shared grid must declare its column tracks"
    first_track = columns.group(1).strip().split()[0]
    assert first_track != "max-content", (
        "the Advanced name column must be a measured px width, not "
        "max-content -- a longer future event name must not silently "
        "resize the whole disclosure"
    )
    assert re.search(r"^\d+px$", first_track), (
        f"the Advanced name column ({first_track!r}) must be a fixed, measured px width"
    )

    row_display = re.search(r"\.alert-advanced-row \{(.*?)\}", CSS, re.DOTALL)
    assert row_display and "display: contents" in row_display.group(1), (
        "each Advanced row must be display:contents so its name and its "
        "Flashes/Speed pair become the shared grid's own items"
    )

    # .alert-flash itself must still lay out as one flex line -- the
    # existing test_flash_and_speed_share_one_collapsed_advanced_disclosure
    # already pins this selector; this test only adds the column it now
    # sits in, so the two must agree rather than one silently undoing
    # the other.
    advanced_flash = re.search(
        r"\.alert-advanced-row > \.alert-flash \{(.*?)\}", CSS, re.DOTALL
    )
    assert advanced_flash and "display: flex" in advanced_flash.group(1)

    # The wrapper must exist in the markup around all three rows, inside
    # the one shared #alert-advanced disclosure -- not a fourth copy of it.
    advanced = re.search(
        r'<details id="alert-advanced"[^>]*>(.*?)</details>', HTML, re.DOTALL
    )
    assert advanced, "the #alert-advanced disclosure markup is missing"
    assert advanced.group(1).count('class="alert-advanced-body"') == 1, (
        "expected exactly one shared .alert-advanced-body grid wrapper "
        "inside the one #alert-advanced disclosure"
    )
    for event in _ALERT_EVENT_IDS:
        assert f'id="alert-event-{event}-flashes"' in advanced.group(1), (
            f"{event}'s Flashes select must still be inside #alert-advanced"
        )


def test_two_enabled_alerts_on_one_colour_are_flagged():
    """Round 6, P1-1. Two alerts the same colour are one alert with two
    meanings, and nothing said so.

    The card already narrowed 16.7M colours to five for this exact reason
    -- COLOURS' own comment ends "and nothing ever told you" -- which made
    a near-miss unreachable and left an EXACT match five clicks away,
    still silent. The round-6 captures caught a live install with Combat
    and Decloak both on #4dd2ff and both on Notify.

    Lexical, like everything else in this file, so it checks the wiring a
    regression would break rather than the rendering (which was verified
    by hand in the ?dev=1 harness over CDP, for all four states: both on,
    colour-only, one disabled, all distinct).
    """
    alerts = _strip_js_comments((WEB / "alerts.js").read_text(encoding="utf-8"))

    assert "function flagCollisions()" in alerts, (
        "the collision check is gone; two alerts can share a colour again"
    )

    # It must run on every path that can make or clear a collision. Missing
    # any one of these leaves a stale note or a silent collision.
    body = alerts[alerts.index("function flagCollisions()") :]
    del body
    calls = alerts.count("flagCollisions();")
    assert calls == 3, (
        "flagCollisions must run after a repaint, a colour change and an "
        f"enable toggle, but not a sound-only change -- found {calls} call sites"
    )

    # THE BUG THIS TEST EXISTS FOR, found in the harness rather than here:
    # a disabled Combat is absent from the colour map, but an enabled
    # Decloak on the same colour still puts that colour IN the map, so
    # Combat found a peer and warned about an alert it cannot raise. The
    # `other !== id` filter does not cover it; an enabled check does.
    assert "!row.enabled || !row.enabled.checked" in alerts, (
        "flagCollisions must exclude a disabled event before grouping: "
        "a disabled event cannot collide with anything"
    )

    # One relationship-level warning, not the same relationship repeated
    # under every row. Its dedicated slot cannot overwrite a refused write.
    html = (WEB / "index.html").read_text(encoding="utf-8")
    collision = re.search(r'<[^>]+id="alerts-collision"[^>]*>', html)
    assert collision and "hidden" not in collision.group(0)
    assert "WM.el('alerts-collision')" in alerts
    assert "collision.hidden" not in alerts
    assert "dataset.collision" not in alerts
    assert "sayRow(row, text, 'warn')" not in alerts
    assert "Their preview pulses are indistinguishable." in alerts


def test_the_alert_rows_offer_exactly_the_sounds_that_exist():
    """index.html hand-writes nine <option>s for three events, and
    settings.py owns the list they must match.

    settings.py:20-22 states the failure this prevents: "An id present in
    the UI dropdown but missing here normalises to silence, which is
    indistinguishable from a broken alert." The guard it asks for existed
    only for the ASSETS -- tests/test_alerts_sound.py checks a .wav exists
    per VALID_SOUNDS -- and nothing tied the page's options to the same
    set. A fourth sound, or a renamed one, shipped a card that could
    silently select an id the backend drops.
    """
    from wingman.settings import VALID_SOUNDS

    for event in _ALERT_EVENT_IDS:
        select = re.search(
            rf'<select[^>]*id="alert-event-{event}-sound".*?</select>',
            HTML,
            re.DOTALL,
        )
        assert select, f"no sound select for {event!r}"
        offered = set(re.findall(r'<option value="([^"]+)"', select.group(0)))
        assert offered == VALID_SOUNDS, (
            f"the {event} sound options are {sorted(offered)}, but "
            f"settings.VALID_SOUNDS is {sorted(VALID_SOUNDS)} -- an id the "
            f"page offers and settings drops normalises to silence"
        )


def test_the_alert_rows_name_the_events_settings_actually_has():
    """The row ids are a hand-kept copy of _ALERT_EVENT_DEFAULTS' keys.

    api.py's set_alert_event refuses an unknown event outright, so a
    renamed key does not corrupt anything -- it just makes every control
    in that row fail silently, on a card whose whole failure mode is
    silence. alerts.js carries the same three ids for the same reason and
    is checked here too, so the three copies cannot drift apart.
    """
    from wingman.settings import _ALERT_EVENT_DEFAULTS

    expected = set(_ALERT_EVENT_DEFAULTS)
    assert set(_ALERT_EVENT_IDS) == expected, (
        f"index.html has alert rows for {sorted(_ALERT_EVENT_IDS)}, but "
        f"settings defines {sorted(expected)}"
    )

    js = _strip_js_comments((WEB / "alerts.js").read_text(encoding="utf-8"))
    listed = re.search(r"var EVENTS = \[(.*?)\]", js, re.DOTALL)
    assert listed, "alerts.js no longer declares a flat EVENTS list"
    assert set(re.findall(r"'([^']+)'", listed.group(1))) == expected, (
        "alerts.js's EVENTS has drifted from settings._ALERT_EVENT_DEFAULTS"
    )


def test_every_default_alert_colour_is_offered_by_the_swatches():
    """The colour control is a fixed palette now, not <input type="color">.

    A default that is not in the palette would render as an unlabelled
    sixth swatch on every fresh install -- paintSwatches appends any stored
    colour it does not recognise, precisely so a hand-edited settings.json
    is not silently rewritten, and that escape hatch would quietly become
    the normal case for a shipped default.
    """
    from wingman.settings import _ALERT_EVENT_DEFAULTS

    js = _strip_js_comments((WEB / "alerts.js").read_text(encoding="utf-8"))
    listed = re.search(r"var COLOURS = \[(.*?)\]", js, re.DOTALL)
    assert listed, "alerts.js no longer declares a COLOURS palette"
    palette = set(re.findall(r"'(#[0-9a-fA-F]{6})'", listed.group(1)))

    defaults = {spec["color"] for spec in _ALERT_EVENT_DEFAULTS.values()}
    missing = defaults - palette
    assert not missing, (
        f"settings defaults {sorted(missing)} are not in the swatch palette "
        f"{sorted(palette)}, so a fresh install shows an extra swatch"
    )


def test_no_native_colour_input_survives_anywhere():
    """style.css has called this control removed since round 5; it wasn't.

    <input type="color"> opens the native Win32 ChooseColor dialog -- the
    last unstyled system chrome reachable from a frameless dark app that
    restyled its own scrollbar precisely because native chrome was a tell.
    Alerts replaced it with a fixed palette and wrote that up in the sheet
    ("the last unstyled system chrome reachable from this app"), and the
    Previews selection ring went on shipping one for two more releases, one
    rail item away from its own replacement.

    The general failure is worth the test more than the one control is: a
    thing documented as removed, but only removed from the screen someone
    happened to be working on.
    """
    assert 'type="color"' not in _strip_html_comments(HTML), (
        "a native colour input is back; the swatch palette in alerts.js / "
        "settings.js is what replaced it, and style.css's .swatches block "
        "has the reason"
    )
    for path in sorted(WEB.glob("*.js")):
        src = _strip_js_comments(path.read_text(encoding="utf-8"))
        assert not re.search(r"""\.type\s*=\s*['"]color['"]""", src), (
            f"{path.name} builds a native colour input in JS, which the "
            f"markup guard above cannot see"
        )


def test_the_selection_ring_default_is_offered_by_its_swatches():
    """Same rule as the alert palette above, for the other palette.

    paint() appends any stored colour it does not recognise, so that a
    hand-edited settings.json is not silently rewritten. A shipped default
    outside the palette would turn that escape hatch into the normal case:
    every fresh install would draw an unlabelled sixth swatch.

    Also pins the pairing of hexes to names, because the name is the
    accessible one -- an unnamed colour falls back to its hex by design,
    and a palette one entry longer than its name list would do that
    silently for the last swatch.
    """
    from wingman.settings import _preview_defaults

    js = _strip_js_comments((WEB / "settings.js").read_text(encoding="utf-8"))
    block = js.split("set_preview_selection_color", 1)[0]
    listed = re.search(r"var COLOURS = \[(.*?)\]", block, re.DOTALL)
    assert listed, "settings.js no longer declares a ring COLOURS palette"
    palette = re.findall(r"'(#[0-9a-fA-F]{6})'", listed.group(1))

    named = re.search(r"var COLOUR_NAMES = \[(.*?)\]", block, re.DOTALL)
    assert named, "settings.js no longer declares COLOUR_NAMES"
    assert len(re.findall(r"'([^']+)'", named.group(1))) == len(palette), (
        "the ring palette and its names are different lengths, so a swatch "
        "announces its hex instead of its name"
    )

    # Round 6's P2-5 for the other palette: the swatches carried their HEX
    # as the accessible name, which does not read aloud as anything and
    # tells a sighted user nothing about what they are picking. The name is
    # what identifies the choice; the hex identifies the pixel and belongs
    # in the tooltip. Without this the length check above passes while the
    # names go unused.
    assert "input.setAttribute('aria-label', name)" in block, (
        "a ring swatch must announce its NAME, not its hex -- the hex is "
        "the fallback for an out-of-palette colour only"
    )

    default = _preview_defaults()["selection_color"]
    assert default in palette, (
        f"settings.py's default ring colour {default} is not in the swatch "
        f"palette {palette}, so a fresh install shows an extra swatch"
    )


def test_the_dense_bind_column_can_hold_a_whole_control_line():
    """Round 5, C8. A named bind group renders as a multi-column block
    (`.bind-dense`), and its column width is set by the CONTROL line, not
    by the label -- .bindbtn's min-width plus Clear and Edit... and two
    gaps. A column narrower than .bindbtn alone would clip the one control
    in the row that has a floor of its own, at every window width, with no
    media query to look for.

    Only the relationship is asserted, because it is the only half of the
    sum that can be read out of the stylesheet: the two .linkbtn widths are
    text, and B6's Type... -> Edit... rename already moved that figure once
    (see the comment on the block, which carries the measurement).
    """
    dense = re.search(r"\.bind-dense \{([^}]*)\}", CSS)
    assert dense, ".bind-dense has no rule block"
    column = re.search(r"columns:\s*(\d+(?:\.\d+)?)px", dense.group(1))
    assert column, ".bind-dense no longer declares a px column width"

    btn = re.search(r"\.bindbtn \{([^}]*)\}", CSS)
    assert btn, ".bindbtn has no rule block"
    floor = re.search(r"min-width:\s*(\d+(?:\.\d+)?)px", btn.group(1))
    assert floor, ".bindbtn no longer declares a min-width"

    assert float(column.group(1)) >= float(floor.group(1)), (
        f".bind-dense's column ({column.group(1)}px) is narrower than "
        f".bindbtn's min-width ({floor.group(1)}px), so every finisher's "
        f"bind button is clipped by its own column"
    )


def test_the_previews_grid_declares_exactly_one_template():
    """`.no-nm` existed because the Never-minimize cell rendered only while
    the global minimize toggle was on, so makeRow appended a different
    number of cells in each state and the stylesheet needed two templates
    whose difference was maintained by hand.

    That control now lives in its own disclosure under the toggle, so the
    row's cell count no longer varies and the second template is gone. A
    reintroduced conditional cell must bring back a guard for its own
    difference rather than reusing this one.
    """
    assert ".no-nm" not in CSS, (
        "#preview-binds.no-nm is back -- a conditional cell needs a guard "
        "on the difference between the two templates, not just a template"
    )
    body = _makerow_body()
    assert "minimizeInactive" not in body, (
        "makeRow appends a conditional cell again, so its cell count "
        "varies with a setting and one template cannot describe both"
    )


def _makerow_body() -> str:
    """previews.js's makeRow, comments stripped, up to its `return row`.

    Comments first: the prose around this function names the very controls
    the counts below are derived from, and a naive scan would count the
    sentences describing an append as appends.
    """
    src = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
    return src.split("function makeRow(", 1)[1].split("return row;", 1)[0]


def _preview_binds_cell_tracks() -> int:
    """How many CELL-BEARING tracks #preview-binds declares -- the name
    track plus the repeated control tracks -- checking as it goes that the
    name track still refuses to consult its own content.

    NOT every track: the template ends with `minmax(0, 1fr)`, which exists
    to absorb the leftover width so the controls stay packed at the start,
    and no row appends a cell for it. The counts this feeds compare
    against makeRow's appends and makeHeadRow's array literal, so the
    trailing track has to stay out of them -- as it did in the regex this
    replaces.

    Both callers below used to inline `(\\d+)px\\s+repeat\\((\\d+),`, which
    pinned the SPELLING of a deliberate first track rather than the
    property that makes it deliberate. Round 6 widened the name column to
    `minmax(210px, 320px)` -- still two lengths, still never sized by
    whoever is logged in, which is all round 3's B1 ever asked for -- and
    both guards failed on the shape while the rule they exist for held.

    So the check is the rule: every part of the first track has to be a
    LENGTH. `max-content`, `min-content`, `auto` and `fit-content()` are
    rejected wherever they appear in it, which also closes the hole the
    old regex left open at the other end -- `minmax(max-content, 260px)`
    is B1 exactly, and a first-token test cannot see it.
    """
    rule = re.search(r"#preview-binds \{(.*?)\}", CSS, re.DOTALL)
    assert rule, "#preview-binds has no rule block"
    template = re.search(r"grid-template-columns:\s*([^;]+);", rule.group(1))
    assert template, "#preview-binds declares no grid-template-columns"

    tracks = _tracks(template.group(1))
    assert tracks, "#preview-binds declares an empty template"

    first = tracks[0]
    for keyword in ("max-content", "min-content", "auto", "fit-content"):
        assert keyword not in first, (
            f"#preview-binds' first track is {first!r}, which sizes the "
            f"character name from its own content -- that is round 3's B1, "
            f"where the bind button moved between sessions with whoever was "
            f"logged in. Both ends of the track must be lengths"
        )
    assert re.search(r"\d", first), (
        f"#preview-binds' first track is {first!r} and names no length at "
        f"all; B1 requires a track the roster cannot move"
    )

    repeat = re.search(r"repeat\((\d+),", template.group(1))
    assert repeat, (
        "#preview-binds no longer declares its control tracks as "
        "repeat(N, ...), which is what the cell counts below are derived "
        "from"
    )
    return 1 + int(repeat.group(1))


def test_the_previews_grid_has_one_track_per_cell_makeRow_appends():
    """The invariant the delta test above cannot see.

    `.row` is display:contents, so the grid reads one flat stream of cells.
    Adding a control means editing a track count in style.css AND an append
    in previews.js -- two files -- and the delta test passes happily when
    BOTH templates are wrong by the same amount. This derives the cell
    count from makeRow itself rather than restating it.

    The label USED to be excluded, because `#preview-binds .row > .lab` was
    `grid-column: 1 / -1` and spanned the row instead of sitting in a
    track. It sits in track 1 now, so it is a cell like any other and the
    `-1` that discounted it is gone. Every collapsed cell is now appended
    unconditionally: character-specific controls live in the full-grid
    detail, and the two cycle rows use the same ternary fillers as every
    other row.
    """
    body = _makerow_body()
    assert "} else {" not in body, (
        "makeRow has a dead character/cycle branch instead of one unconditional "
        "collapsed-row shape"
    )
    # The label is COUNTED now: it sits in track 1 rather than spanning the
    # row, so it is a cell like any other. Every row.appendChild() here is
    # one of the collapsed grid cells.
    cells = body.count("row.appendChild(")

    tracks = _preview_binds_cell_tracks()

    assert cells == tracks, (
        f"makeRow appends {cells} cells per character row but #preview-binds "
        f"declares {tracks} tracks -- every row after the first is "
        f"pulled into the previous row's leftover columns"
    )


def test_the_roster_heading_owns_the_focus_fallback():
    """The focus fallback and narrow screenshot target the actual roster header."""
    html = _strip_html_comments(HTML)
    assert 'id="preview-roster-heading"' not in html

    src = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
    head = src.split("function makeHeadRow(", 1)[1].split("return row;", 1)[0]
    assert "preview-roster-heading" in head
    assert "tabindex', '-1'" in head


def test_the_previews_header_row_names_one_column_per_track():
    """The header row is a grid row like any other, and gets the same trap.

    makeHeadRow is deliberately NOT part of makeRow -- the count above
    derives from makeRow's own appends, so a header built there would be
    counted as extra controls on every row. That keeps the two counts
    honest but leaves the header itself unguarded, which is what this
    closes.

    WHAT A MISMATCH ACTUALLY COSTS, measured for every cell rather than
    for one: the header's captions land over the wrong controls, AND the
    rows below shift. Measured against the SEVEN-column layout, before
    Lock and Never minimize moved out of the row into their own
    disclosures and before the name came inline. The table is left as it
    was taken: the mechanism it demonstrates outlived the layout it was
    measured on. Deleting each heading in turn in the ?dev=1 harness at
    840x625 moves the first character row's controls to

        Preview        209/265/425/477/531/587/685
        Keybind        209/264/424/476/530/586/684
        either blank   209/264/424/476/530/586/684
        Size           209/264/424/476/530/586/684
        Lock           209/264/424/476/530/586/684
        Never minimize 209/264/424/476/530/586/624   (unchanged)
        intact         209/264/424/476/530/586/624

    -- six of seven push every row's last column 60px right, because the
    columns are shared `max-content` tracks and a displaced heading falls
    into a narrower one and grows it. Only the last cell is free, and an
    earlier version of this docstring tested exactly that one and
    concluded the damage was local.

    Vertical placement really does not cascade: y was identical in all
    seven runs. The reset to a fresh row is now
    `#preview-binds .row > :first-child { grid-column-start: 1 }`. The
    spanning `.lab` used to do it for free, which is why the hazard is
    newer than the grid -- it arrived with the inline name, and
    test_every_previews_row_starts_a_fresh_grid_line is what holds the
    replacement in place.

    Counted from the array literal rather than from `row.appendChild(`:
    makeHeadRow appends inside a forEach, so the literal-substring trick
    the makeRow guard uses would count one cell however many it emits.
    """
    src = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
    assert "function makeHeadRow(" in src, "previews.js has no makeHeadRow"
    body = src.split("function makeHeadRow(", 1)[1].split("return row;", 1)[0]

    literal = re.search(r"var cells = \[(.*?)\];", body, re.DOTALL)
    assert literal, "makeHeadRow no longer builds its cells from an array literal"
    base = len([part for part in literal.group(1).split(",") if part.strip()])
    assert "cells.push(" not in body, (
        "makeHeadRow names a conditional column again, so the header's cell "
        "count varies with a setting and one template cannot describe both"
    )

    m = re.search(r"#preview-binds \{(.*?)\}", CSS, re.DOTALL)
    assert m, "#preview-binds has no rule block"
    tracks = _preview_binds_cell_tracks()
    assert base == tracks, (
        f"makeHeadRow names {base} columns but #preview-binds declares "
        f"{tracks} tracks -- the headings sit over the wrong controls, and "
        f"a heading falling into a narrower shared track widens it for "
        f"every row below"
    )


def test_the_previews_header_stays_above_rows_while_settings_scrolls():
    """The one Settings pane scrolls, so the column labels must stay with it."""
    rule = re.search(r"\.bind-head > span \{(.*?)\}", CSS, re.DOTALL)
    assert rule, "the Preview column headers have no CSS rule"
    for prop in (
        "position: sticky",
        "top: 0",
        "z-index:",
        "background: var(--panel)",
    ):
        assert prop in rule.group(1), (
            f"Preview header cells need `{prop}` so their labels remain visible "
            "and opaque while the Settings pane scrolls"
        )


def test_the_sticky_offline_heading_clears_the_sticky_preview_header():
    host = re.search(r"#preview-binds \{(.*?)\}", CSS, re.DOTALL)
    assert host and "--preview-bind-head-height:" in host.group(1), (
        "#preview-binds must own the measured sticky-header height"
    )
    offline = re.search(
        r"#preview-binds \.bind-group:not\(:empty\) \{(.*?)\}", CSS, re.DOTALL
    )
    assert offline and re.search(
        r"top:\s*var\(--preview-bind-head-height\)", offline.group(1)
    ), "the Offline heading must stick below, not on top of, the column header"


def test_the_previews_headings_are_in_the_order_makeRow_builds():
    """Counting columns is not the same as naming the right one.

    The guard above compares two NUMBERS. Reorder makeRow's appends --
    moving makeExcludedCheck ahead of the name cell is an entirely
    plausible edit -- and every heading is over the wrong control while
    both counts still agree. Nothing in this suite renders the page, so
    that would ship looking exactly like a correct table.

    So: each named heading is tied to the append that fills its column,
    and the two sequences must run in the same order.
    """
    body = _makerow_body()
    src = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
    head = src.split("function makeHeadRow(", 1)[1].split("return row;", 1)[0]

    # heading -> the token in makeRow that builds the cell it labels.
    owners = (
        ("Character", "'lab'"),
        ("Preview", "makeExcludedCheck"),
        ("Keybind", "'bindbtn'"),
        ("Configure", "'Configure'"),
    )

    for heading, token in owners:
        assert f"'{heading}'" in head, (
            f"makeHeadRow no longer names a {heading!r} column, so the "
            f"control {token} has no heading over it"
        )
        assert token in body, (
            f"makeRow no longer builds {token}, but makeHeadRow still "
            f"names a {heading!r} column over it"
        )

    # The blank cell is the `.rowacts` track (Clear + Edit... share it).
    # It carries no word, so the loop above cannot see it -- and reordering
    # the literal to ['Character', 'Preview', 'Keybind', 'Size', ''] keeps
    # both sequences below sorted and the count at 5, while `Size` would
    # sit over the actions cell and the blank over Size.
    cells = re.search(r"var cells = \[([^\]]*)\]", head)
    assert cells, "makeHeadRow no longer declares its headings as one literal"
    names = [c.strip().strip("'") for c in cells.group(1).split(",")]
    assert names.index("") == 3, (
        f"makeHeadRow's blank heading is at index {names.index('')}, not 3: "
        f"{names}. The blank labels `.rowacts`, which makeRow appends "
        f"fourth; anywhere else and every heading from there on is over "
        f"the wrong control with the count still agreeing"
    )

    heading_order = [head.index(f"'{h}'") for h, _ in owners]
    append_order = [body.index(t) for _, t in owners]
    assert heading_order == sorted(heading_order), (
        "makeHeadRow's headings are no longer in column order"
    )
    assert append_order == sorted(append_order), (
        "makeRow builds its cells in a different order from the headings "
        f"makeHeadRow names: {[t for _, t in owners]} appear at "
        f"{append_order}. Every heading below the swap labels the wrong "
        f"control, and the cell COUNTS still agree, so nothing else here "
        f"would catch it."
    )


def test_only_the_previews_name_is_allowed_to_ellipsize():
    """The name yields inside its track; nothing else in the cell may.

    A character is identifiable from a prefix and the whole string is in
    the cell's `title`, so clipping the NAME costs nothing.

    THE CELL HELD TWO THINGS UNTIL ROUND 6. The second was an `offline`
    tag, and the split below existed to stop a long name taking it with
    it: putting the ellipsis on `.lab` itself clips the pair. Measured in
    the harness at the 840x625 floor before the split, a 14-character name
    left the tag 19.6px of headroom and a 37-character one pushed its
    right edge to 500.41 against a track ending at 359 -- the word gone
    entirely, with no width at which the reader is told.

    The tag is gone (see the offline-heading test below) and the split
    STAYS, which is the part worth asserting. `display: flex` plus
    `min-width: 0` on the name is also what lets it ellipsize inside a
    fixed track at all, and that half was never about the tag. Collapse
    the cell back to a plain block and long names clip with no marker.

    Reads the non-media `.lab` block, not the first one in the file, for
    the reason test_each_keybind_list_declares_a_deliberate_first_track
    spells out: this host declares two and a first-match read would answer
    from whichever the stylesheet happens to list first.
    """
    narrow = _media_spans(720)
    labs = [
        b
        for b in re.finditer(r"#preview-binds \.row > \.lab \{(.*?)\}", CSS, re.DOTALL)
        if not any(lo <= b.start() < hi for lo, hi in narrow)
    ]
    assert labs, "#preview-binds no longer overrides the shared label column"
    lab = "\n".join(b.group(1) for b in labs)
    assert re.search(r"display:\s*flex", lab), (
        "#preview-binds's label cell is no longer a flex row, so `min-width: "
        "0` on the name has nothing to act inside and the ellipsis stops "
        "working"
    )
    assert "text-overflow" not in lab, (
        "#preview-binds's label cell ellipsizes as a whole again, which "
        "truncates the cell rather than the name inside it"
    )

    name = re.search(
        r"#preview-binds \.row > \.lab > \.lab-name \{(.*?)\}", CSS, re.DOTALL
    )
    assert name, "the previews name span has no rule of its own to ellipsize in"
    # `overflow: hidden` is in this list because `text-overflow` is INERT
    # without it -- the name would spill out of the cell instead of
    # truncating, which is the same clipped name by a different route.
    for prop in (
        "min-width: 0",
        "overflow: hidden",
        "text-overflow: ellipsis",
        "white-space: nowrap",
    ):
        assert prop in name.group(1), (
            f".lab-name must declare `{prop}` -- without all four the name "
            f"either refuses to shrink inside the flex row, spills out of "
            f"the cell, or wraps instead of ellipsizing"
        )

    src = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
    body = src.split("function makeRow(", 1)[1].split("return row;", 1)[0]
    assert "'lab-name'" in body, (
        "makeRow no longer builds a .lab-name span, so the CSS above has "
        "nothing to apply to and the name is a bare text node again"
    )


def test_the_offline_state_is_a_heading_over_its_block_not_a_colour():
    """Offline is TEXT, and the text may not be able to leave the rows it
    describes. Both halves have been got wrong here before, differently.

    Round 5 wrote it as a legend above the first row. That failed for two
    reasons: dimness alone carried the state for any row the legend had
    scrolled past (WCAG 1.4.1), over a list ~780px tall where that was
    most of them.

    The fix was a word per row, which cured the encoding and created a
    third problem nobody had measured: on a typical fleet ELEVEN OF
    THIRTEEN rows are offline, so the word sat on the majority and the two
    rows that mattered were the ones without it.

    Round 6 is a heading over the offline block, which `rows()` already
    returns contiguously. That is the legend again in every respect but
    the one that broke it -- so `position: sticky` is not a flourish here,
    it is the whole difference. A heading that can scroll off its own
    block is round 5's defect wearing a different word.
    """
    src = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))

    assert "off-tag" not in src, (
        "the per-row `offline` tag is back alongside the heading, so the "
        "word is stated twice for every row in the block"
    )
    assert "'bind-group-name', 'Offline'" in src, (
        "previews.js no longer builds an `Offline` heading -- with the "
        "per-row tag gone that leaves `.lab.dim`'s colour as the only "
        "encoding of the state, which is WCAG 1.4.1"
    )
    # Guarded because the split is what makes the heading contiguous. Sort
    # the list some other way and the heading would sit above a block that
    # is no longer all-offline.
    assert "filter(function (e) { return !e.online; })" in src, (
        "the offline rows are no longer selected as their own block, so "
        "the heading no longer describes everything under it"
    )

    # Matches the selector loosely on purpose. The rule is written against
    # `.bind-group:not(:empty)` -- an EMPTY .bind-group of the same class
    # draws the rule that opens the table, and pinning a bare hairline to
    # the top of the pane would leave a stray line over the rows. An
    # anchored `\.bind-group \{` would answer "no sticky rule at all" for
    # a sheet that has a perfectly good one, which is a false alarm rather
    # than a caught defect.
    rule = re.search(
        r"#preview-binds \.bind-group(?::[a-z-]+(?:\([^)]*\))?)* \{(.*?)\}",
        CSS,
        re.DOTALL,
    )
    assert rule, (
        "#preview-binds's group heading has no rule of its own, so it is "
        "not sticky and can scroll off the block it explains"
    )
    for prop in ("position: sticky", "top:", "background:"):
        assert prop in rule.group(1), (
            f"the offline heading must declare `{prop}`: without sticky and "
            f"a top it leaves its own block, and without a background the "
            f"rows scroll through the word"
        )


def test_every_previews_row_starts_a_fresh_grid_line():
    """With the name inline each row contributes fewer cells than the grid
    has tracks, because the trailing minmax(0, 1fr) holds no control. Grid
    auto-placement then puts the NEXT row's first cell in that leftover
    track, and every row after it walks one column left -- measured in the
    harness as the second character's name landing in the far-right column
    while its own controls slid under the wrong headings.

    A definite column-start resets auto-placement to a fresh row. The
    spanning label used to do this for free, which is why the hazard is
    new: it arrived with the inline name, not with the grid.

    Read outside the narrow blocks, like the two sibling guards. A scan of
    the whole stylesheet would go green with this rule moved inside
    `@media (max-width: 720px)` -- a width the window can never reach,
    since the CSS floor is 840x625 -- while every row after the first
    walked a column left at every width that IS reachable.

    `1\\s*;` rather than `1`, so the search cannot be satisfied by a
    `grid-column-start: 10` or `: 12` that happens to start with the right
    digit.
    """
    narrow = _media_spans(720)
    pinned = [
        b
        for b in re.finditer(
            r"#preview-binds \.row > :first-child \{[^}]*grid-column-start:\s*1\s*;",
            CSS,
            re.DOTALL,
        )
        if not any(lo <= b.start() < hi for lo, hi in narrow)
    ]
    assert pinned, (
        "#preview-binds rows no longer pin their first cell to column 1 at "
        "full width, so the trailing flexible track swallows the next row's "
        "first cell"
    )


def test_the_character_detail_gates_size_and_copy_on_backend_payloads():
    """The disclosure owns geometry actions without duplicating backend rules."""
    body = _makerow_body()
    assert "makeGeometryActions" not in body

    src = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
    detail = src.split("function makeCharacterDetail(", 1)[1].split("\n  function ", 1)[
        0
    ]
    assert "makeGeometryActions(characterName, off)" in detail

    geometry_actions = src.split("function makeGeometryActions(", 1)
    assert len(geometry_actions) == 2
    geometry_actions = geometry_actions[1].split("\n  }", 1)[0]
    assert "isSizable(name)" in geometry_actions
    assert "makeSizeButton" in geometry_actions
    assert "makeSizeFiller" in geometry_actions
    assert "makeCopyButton" in geometry_actions

    sizable = src.split("function isSizable(", 1)
    assert len(sizable) == 2
    assert "state.sizable" in sizable[1].split("}", 1)[0]
    sources = src.split("function copySources(", 1)
    assert len(sources) == 2
    assert "state.layout_sources" in sources[1].split("}", 1)[0]


def test_copy_picker_groups_sources_and_disarms_capture_before_opening():
    src = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
    picker = src.split("function makeCopyButton(", 1)
    assert len(picker) == 2
    picker = picker[1].split("\n  }", 1)[0]

    assert picker.index("endCapture();") < picker.index("WM.choose(")
    assert "'Online'" in picker and "'Offline'" in picker
    assert "'Saved placements'" in picker
    assert "source.online === true" in picker
    assert "source.online === false" in picker
    assert "copy_preview_layout" in picker
    assert "data-copy-target" in picker
    assert "restoreCopyFocusAfterRefresh(name, interaction, attempt)" in picker
    assert "state.characters" not in picker
    assert "It applies next time" not in picker
    assert "source.name !== name" in src


def test_copy_picker_has_collapsing_empty_and_status_lines():
    html = _strip_html_comments(HTML)
    assert 'id="preview-copy-empty"' in html
    assert 'id="preview-copy-status"' in html
    status = html.split('id="preview-copy-status"', 1)[1][:100]
    assert 'role="status"' in status
    assert "hidden" in status
    src = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
    assert "preview-copy-empty" in src
    assert "preview-copy-status" in src
    assert "status.classList.toggle('err', !!error)" in src
    assert "status.hidden = !status.textContent" in src
    assert "function restoreCopyFocusAfterRefresh(name, interaction, attempt)" in src

    section = src.split("document.addEventListener('wm:section'", 1)
    assert len(section) == 2
    assert "copyStatus('', false)" in section[1].split("});", 1)[0]


def test_clear_is_not_drawn_where_it_could_only_refuse():
    """D6's rule -- do not draw a control in a state where it can only
    refuse -- applied to the control that broke it worst. `Clear` used to
    be rendered on every row and disabled wherever there was no chord to
    clear, which on a fresh install is every row. It is a .linkbtn, so the
    shared disabled opacity makes it intentionally quieter than the enabled
    subordinate treatment, while still holding a grid track on thirteen rows.

    Only the render-at-all gate moved. `Clear` still goes through
    WM.setEnabled against the row's own opted-out state once it exists --
    an opted-out row otherwise leaves the destructive control as the only
    LIVE one beside a bind button, Edit... and Size... that are all inert,
    directly contradicting that button's own tooltip ("is still saved, and
    comes back when you tick Preview again"). A first version of this test
    asserted `WM.setEnabled(clear` was gone entirely and that shipped
    briefly before review caught it; the docstring above is what changed,
    not the fix.

    Its function is not lost either way. Edit... with an empty submission
    clears, and that path predates this change.
    """
    body = _makerow_body()
    assert "if (gesture) {" in body, (
        "makeRow no longer chooses whether to build Clear -- it is back to "
        "rendering a control that can only refuse on every unbound row"
    )
    assert re.search(r"WM\.setEnabled\(clear,[^)]*\boff\b", body), (
        "Clear is built without going through WM.setEnabled against the "
        "row's opted-out state -- it is live on a row where every other "
        "control is inert, deleting the chord that row's own tooltip just "
        "promised was kept"
    )
    # Drawing Clear conditionally is only half of it. Clear and Edit... share
    # ONE grid cell now, so a row that skips Clear would otherwise slide
    # Edit... left into the space Clear had -- the same verb at two x
    # positions down the column, keyed on something the reader cannot see.
    # Right-aligning inside the cell pins Edit... to one edge and turns a
    # missing Clear into an empty slot. That is one declaration, and
    # deleting it left the whole suite green until a review looked for it.
    acts = re.search(r"\.rowacts\s*\{([^}]*)\}", CSS)
    assert acts, "`.rowacts` has no rule -- Clear and Edit... share its cell"
    assert "justify-content: flex-end" in acts.group(1), (
        "`.rowacts` no longer right-aligns its contents, so Edit... sits at "
        "one x position on a bound row and another on an unbound one"
    )


def test_an_opted_out_character_row_disables_its_own_controls():
    """The chosen shape for a character opted out of previews: the row
    stays visible -- there has to be somewhere to turn it back on -- but
    the controls that can no longer do anything are inert.

    What this pins is that they go through WM.setEnabled against the row's
    own opted-out state, rather than merely being dimmed in CSS: a control
    that only LOOKS dead still fires on click.

    `clear` belongs in this loop even though it is no longer drawn
    unconditionally (test_clear_is_not_drawn_where_it_could_only_refuse):
    the render-at-all gate and the opted-out gate are two different
    questions, and only the first one changed. Once `Clear` exists it
    still has to be inert on an opted-out row -- otherwise it is the one
    LIVE control left beside a bind button, Edit... and Size... that have
    all gone dark, deleting a chord its own row's tooltip just promised was
    kept.
    """
    body = _makerow_body()
    for control in ("button", "clear", "typed"):
        assert re.search(rf"WM\.setEnabled\({control},[^)]*\boff\b", body), (
            f"makeRow does not gate `{control}` on the row's opted-out state"
        )
    # Geometry now lives in the inline detail, but it must retain the
    # opted-out state that keeps Size and Copy inert for a disabled preview.
    src = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
    detail = src.split("function makeCharacterDetail(", 1)[1].split("\n  function ", 1)[
        0
    ]
    assert re.search(r"makeGeometryActions\(characterName,[^)]*\boff\b", detail), (
        "makeCharacterDetail does not pass the opted-out state to geometry actions"
    )
    # Lock left the row for its own disclosure, and took this invariant with
    # it: with no window there is nothing to lock, so the block must pass
    # each character's opted-out state the way the row used to. Asserted on
    # the CALL, not inside the builder, because the call site is what
    # decides -- the same reasoning the never-minimize guard below gives.
    src = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
    assert re.search(r"makeLockCheck\(name,[^)]*isExcluded\(name\)", src), (
        "the Lock block does not pass each character's opted-out state, so "
        "an opted-out character gets a live control over a window that is "
        "not there"
    )


def test_never_minimize_stays_live_on_an_opted_out_row():
    """The one control that must NOT go inert with the rest of an
    opted-out character's row.

    Opting a character out stops their PREVIEW. It does not stop
    minimize_inactive_clients: `_activate_client` resolves `previous_key`
    from `_clients`, which deliberately still holds opted-out characters,
    so switching away from that character's real EVE window still consults
    `_is_never_minimize`. Greying the checkbox would leave a setting in
    force with no way to change it -- the same shape as the roster
    eviction hazard `LayoutStore._protected` exists for.

    The invariant used to be asserted against makeRow's call, but that call
    is gone -- Never minimize now renders once, in its own disclosure, the
    same as Lock's. Asserted on the block's own call site rather than
    inside the builder, because the builder is shared and it is the call
    site that decides.

    A bare ``makeNeverMinimizeCheck(name)`` search over the whole file is
    NOT enough, and shipped that way once: ``function
    makeNeverMinimizeCheck(name) {`` satisfies it by itself, so mutating
    the call site to pass ``isExcluded(name)`` left the guard green. The
    Lock counterpart never had that hole because a second argument is what
    it looks for. This one is anchored on the append instead.
    """
    src = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
    assert "list.appendChild(makeNeverMinimizeCheck(name));" in src, (
        "the Never-minimize block no longer appends "
        "`makeNeverMinimizeCheck(name)` verbatim -- if it gained an "
        "argument it is being passed an opted-out state, which would grey "
        "a checkbox whose setting is still enforced"
    )
    # Belt and braces, and the half that survives a reformat of the line
    # above: the block's body must not consult the opt-out roster at all.
    block = src.split("function renderNeverMinimizeBlock(", 1)[1]
    block = block.split("\n  }", 1)[0]
    assert "isExcluded" not in block, (
        "renderNeverMinimizeBlock consults isExcluded -- whatever it does "
        "with the answer, this control is not allowed to vary on it"
    )


def test_the_disclosure_rosters_do_not_relabel_their_own_checkboxes():
    """The character name is VISIBLE text inside each roster label, so an
    accessible name already exists. Re-adding the `aria-label` the row
    checkboxes carry -- which is what the row versions of these two builders
    did, and what an edit restoring "consistency" would reach for first --
    overrides that visible name, which is the failure WCAG 2.5.3 names.

    What the tick MEANS ("locked", "never minimized") reaches the reader
    once, through the roster container's `aria-labelledby` pointing at its
    own `<summary>`, rather than being restated on every row. The row's own
    opt-out box keeps its `aria-label` and must: its label has no text at
    all.
    """
    src = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
    for builder in ("makeLockCheck", "makeNeverMinimizeCheck"):
        body = src.split(f"function {builder}(", 1)[1].split("\n  }", 1)[0]
        assert "aria-label" not in body, (
            f"{builder} sets an aria-label. Its label carries the character "
            f"name as visible text, so that overrides the visible name "
            f"instead of adding to it (WCAG 2.5.3)"
        )
        assert re.search(r"WM\.make\('label', 'check[^']*', name\)", body), (
            f"{builder} no longer builds its label with the character name "
            f"as its text, so the checkbox has no accessible name at all"
        )

    html = (WEB / "index.html").read_text(encoding="utf-8")
    for block in ("preview-lock-exceptions", "preview-nm-exceptions"):
        assert f'aria-labelledby="{block}-summary"' in html, (
            f"#{block}-list does not point at its own summary, so a "
            f"screen reader announces the character name with nothing to "
            f"say whether the tick is about locking or about minimizing"
        )


def test_a_shared_chord_ignores_opted_out_characters():
    """`sharers()` decides two user-visible claims, and Python has already
    stopped both being true for an opted-out character.

    `_registerable` drops them before `plan_registrations`, so they neither
    win a chord nor share one. Without this filter the page paints a
    `duplicate` clash on the CYCLE row -- which is live and undimmed --
    saying the cycle keybind loses a chord it has in fact just won, and
    offers "Shared with <name>. Pressing it goes to whichever of them is
    logged in" for a character it will never reach.
    """
    src = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
    halves = src.split("function sharers(", 1)
    assert len(halves) == 2, "previews.js has no sharers()"
    body = halves[1].split("\n  }", 1)[0]
    assert "isExcluded" in body, (
        "sharers() does not exclude opted-out characters, so the page "
        "reports conflicts and sharing that Python has already filtered away"
    )


def test_the_opt_out_box_itself_is_never_gated_on_being_enabled():
    """The one control that has to stay live on an opted-out row. Gating
    it with the rest would opt a character out permanently, the only way
    back being a hand-edited settings file."""
    src = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
    halves = src.split("function makeExcludedCheck(", 1)
    assert len(halves) == 2, "previews.js has no makeExcludedCheck"
    body = halves[1].split("return label;", 1)[0]
    assert "WM.setEnabled" not in body, "the opt-out box gates itself"
    assert "set_preview_excluded" in body


def test_range_controls_use_token_driven_track_thumb_and_value_styles():
    """Chromium's native blue slider must not escape the dark control system."""
    base = re.search(r'input\[type="range"\]\s*\{([^}]*)\}', CSS)
    assert base, "range inputs have no shared base rule"
    assert "appearance: none" in base.group(1)
    assert "background: transparent" in base.group(1)

    track = re.search(
        r'input\[type="range"\]::-webkit-slider-runnable-track\s*\{([^}]*)\}',
        CSS,
    )
    assert track, "range inputs have no authored WebKit track"
    assert "background: var(--track)" in track.group(1)
    assert "border:" in track.group(1) and "var(--control-border)" in track.group(1)

    thumb = re.search(r'input\[type="range"\]::-webkit-slider-thumb\s*\{([^}]*)\}', CSS)
    assert thumb, "range inputs have no authored WebKit thumb"
    assert "background: var(--control)" in thumb.group(1)
    assert "border:" in thumb.group(1) and "var(--brand-edge)" in thumb.group(1)

    focus = re.search(
        r'input\[type="range"\]:focus-visible::-webkit-slider-thumb\s*\{([^}]*)\}',
        CSS,
    )
    assert focus and "var(--focus-ring)" in focus.group(1), (
        "the authored range thumb has no shared keyboard focus indicator"
    )

    value = re.search(r"\.range-value\s*\{([^}]*)\}", CSS)
    assert value, "range controls have no adjacent value treatment"
    assert "background: var(--sunken)" in value.group(1)
    assert "border:" in value.group(1) and "var(--control-border)" in value.group(1)


def test_preview_opacity_reads_on_input_and_commits_on_change():
    """Dragging is local feedback; only release crosses the settings bridge."""
    js = _strip_js_comments((WEB / "settings.js").read_text(encoding="utf-8"))
    body = js[js.index("var box = WM.el('preview-opacity')") :]
    input_handler = re.search(r"box\.addEventListener\('input', ([A-Za-z]+)\)", body)
    assert input_handler and input_handler.group(1) == "show"
    change = body.index("box.addEventListener('change'")
    send = body.index("WM.send('set_preview_opacity'")
    assert change < send
    assert "set_preview_opacity" not in body[:change]


def test_the_opacity_slider_can_still_reach_the_stored_floor():
    """Round 5, C2. `#preview-opacity` is a PERCENTAGE now; the setting it
    writes is still the DWM thumbnail's 0-255 alpha byte, and
    settings.validated_preview owns the range.

    The slider's `min` is therefore that floor expressed in the control's
    own units, and 8 is not a rounded-off 10: it is the largest percentage
    that still converts down to the stored floor. A min that converted to
    anything higher would make the lowest value the backend keeps
    unreachable, and would render a stored floor back as a number the
    slider cannot show.

    Derived from settings.py on both ends rather than restated here, since
    a change to either range is exactly what this is watching for.
    """
    from wingman.settings import validated_preview

    floor = validated_preview({"opacity": -1})["opacity"]
    ceiling = validated_preview({"opacity": 10**6})["opacity"]

    slider = re.search(r'<input type="range" id="preview-opacity"([^>]*)>', HTML)
    assert slider, "#preview-opacity is no longer a range input"
    attrs = dict(re.findall(r'(\w+)="([^"]*)"', slider.group(1)))
    assert attrs.get("max") == "100", (
        f"#preview-opacity's max is {attrs.get('max')!r}, not a percentage"
    )
    low = int(attrs["min"])
    assert round(low * ceiling / 100) == floor, (
        f"#preview-opacity's min ({low}%) converts to "
        f"{round(low * ceiling / 100)}, not settings' floor of {floor}"
    )


# ---- the uploader's columns -------------------------------------------
#
# The list is the one place on the page where three files have to agree
# about the same ordered set of columns: index.html names them, list.js
# builds a cell per row, and style.css sizes them with a single template
# shared by the header and the body. Nothing checked that agreement until
# the Age column was restored, and the failure mode is quiet -- a header
# with no cell under it draws a heading over the NEXT column's values,
# which reads as the data being wrong rather than the markup.


def _grid_row_columns() -> list[str]:
    """The `c-*` classes named by the list header, in document order."""
    head = re.search(
        r'<div class="grid-row list-head".*?>(.*?)</div>', HTML, flags=re.DOTALL
    )
    assert head, "the list header block moved; this guard cannot find it"
    return re.findall(r'class="(c-[a-z]+)"', head.group(1))


def _row_node_cells() -> list[str]:
    """The `c-*` classes list.js builds per row, in the order it appends
    them. Read from the source rather than listed here, because a hand-kept
    copy is the drift this test exists to catch."""
    js = _strip_js_comments((WEB / "list.js").read_text(encoding="utf-8"))
    body = re.search(r"function rowNode\(row\)\s*\{(.*?)\n  \}", js, flags=re.DOTALL)
    assert body, "rowNode() moved or changed shape; this guard cannot find it"
    return re.findall(r"WM\.make\(\s*'span',\s*'(c-[a-z]+)'", body.group(1))


def _tracks(template: str) -> list[str]:
    """Split a grid-template-columns value into tracks, respecting the
    commas inside minmax()."""
    tracks, depth, current = [], 0, ""
    for char in template:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char.isspace() and depth == 0:
            if current:
                tracks.append(current)
                current = ""
            continue
        current += char
    if current:
        tracks.append(current)
    return tracks


def _base_template() -> list[str]:
    """The tracks in .grid-row's own rule -- the base layout, not a tier."""
    rule = re.search(r"\.grid-row\s*\{([^}]*)\}", CSS)
    assert rule, "the .grid-row rule moved; this guard cannot find it"
    template = re.search(r"grid-template-columns:\s*([^;]+);", rule.group(1))
    assert template, ".grid-row no longer sets grid-template-columns"
    return _tracks(template.group(1))


def test_the_list_says_how_old_each_recording_is():
    """A recording's age is a column, not a fact the reader derives from
    the filename.

    It was dropped in round 3 as "Modified", on the argument that OBS names
    every recording after its own timestamp so the column printed the same
    fact twice. That argument was overturned: reading a timestamp and
    knowing whether something is recent are different acts, and the cell
    answers the second one. Python has carried the value throughout --
    RowSnapshot has never stopped sending `date` -- so what shipped for two
    rounds was a payload field no one rendered, which is precisely the kind
    of thing that gets deleted as dead on the next pass.
    """
    assert "c-date" in _grid_row_columns(), "the list header names no age column"
    assert "c-date" in _row_node_cells(), "rowNode() builds no age cell"
    head = re.search(
        r'<div class="grid-row list-head".*?>(.*?)</div>', HTML, flags=re.DOTALL
    )
    assert ">Age<" in head.group(1), (
        "the age heading should read 'Age' -- 'Modified' was the absolute "
        "column this replaced, and library.format_date renders a relative "
        "string, so the old heading would mislabel the values under it"
    )


def test_the_header_the_rows_and_the_grid_template_name_the_same_columns():
    """One template sizes the header and every row, so a column that exists
    in only two of the three files is a silent misalignment rather than an
    error: the header draws its heading over the next column's values.

    Derived from all three sources rather than compared against a list
    typed here, per the repo's rule that anything derived is derived or
    asserted, never retyped.
    """
    header = _grid_row_columns()
    cells = _row_node_cells()
    assert header == cells, (
        f"the list header names {header} but rowNode() builds {cells}; "
        "the shared grid template makes any disagreement a misalignment"
    )
    tracks = _base_template()
    assert len(tracks) == len(header), (
        f"{len(header)} columns ({header}) but {len(tracks)} tracks in "
        f".grid-row's template ({tracks}); a short template silently packs "
        "the trailing columns into the last track"
    )


def test_a_column_dropped_at_a_narrow_width_takes_its_heading_with_it():
    """Hiding a cell must be qualified with `.grid-row >`.

    `.c-date` on its own is (0,1,0) and loses to `.list-head > span`, which
    is (0,1,1) -- so an unqualified rule hides the body cell and KEEPS the
    heading, which is the exact header/row disagreement the shared template
    exists to make impossible. style.css warns about this in prose; this is
    the same rule as a test.
    """
    offenders = []
    for selector, block in re.findall(r"([^{}]+)\{([^}]*)\}", CSS):
        if not re.search(r"display:\s*none", block):
            continue
        for part in selector.split(","):
            part = part.strip()
            if re.search(r"\.c-[a-z]+", part) and ".grid-row >" not in part:
                offenders.append(part)
    assert not offenders, (
        "these rules hide a list column without qualifying through "
        f"`.grid-row >`, so the heading survives the cell: {offenders}"
    )


def test_every_element_id_in_the_page_is_unique():
    """Duplicate ids are the failure mode a rebase produces and no other
    guard here can see.

    This branch shipped one: resolving a conflict re-added a line that was
    shared context ABOVE the `<<<<<<<` marker, so
    `preview-minimize-inactive-status` existed twice. The suite stayed
    green, and the visible symptom was a hint reading "Applies Applies the
    next time...", an unclosed `<span>`, and `WM.el()` resolving to the
    outer of the two -- so the first `say()` deleted the inner one.

    Every screen is one document here, so this is a whole-page invariant
    rather than anything to do with previews: `WM.el` is
    `getElementById`, and with two matches it silently picks the first.
    """
    index = (WEB / "index.html").read_text(encoding="utf-8")
    ids = re.findall(r'\bid="([^"]+)"', index)
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    assert not dupes, f"these ids appear more than once in index.html: {dupes}"


def test_the_previews_dependence_line_is_stated_once_and_reads_the_switch():
    """One line for a block, not one per control -- and it must be able to
    read the switch it speaks for.

    The Previews card carried this sentence in SEVEN blocks, six of them
    word for word, each with its own previewsOn/sayDependence/
    refreshDependence to place it; one copy had already drifted to spelling
    its local `enabled`. Round 3's R4 caught three of them colliding in one
    view and shortened one, which fixed that view and left six. Nothing
    counted them, which is what this closes.

    THE ORDERING HALF IS THE PART THAT FAILS SILENTLY. Both the master
    switch's block and the dependence block listen on `wm:settings`; the
    first sets `#preview-enabled` from the payload and the second reads
    `.checked` back off it. Listeners fire in registration order and these
    IIFEs run in source order, so the dependence block has to come SECOND.
    Move it up and the line reports the previous payload's state -- on a
    screen where every control still works and nothing else looks wrong.
    Verified over CDP against a dispatched payload; asserted here because
    nothing in this suite renders the page.
    """
    js = _strip_js_comments((WEB / "settings.js").read_text(encoding="utf-8"))
    index = (WEB / "index.html").read_text(encoding="utf-8")

    assert 'id="preview-depends"' in index, "the shared dependence slot is gone"
    assert index.count('id="preview-depends"') == 1

    # The sentence lives in exactly one place.
    assert js.count("in effect yet") == 1, (
        "the dependence sentence is written more than once in settings.js -- "
        "that is the state this replaced, six copies of one sentence"
    )
    for dead in ("sayDependence", "refreshDependence", "previewsOn"):
        assert dead not in js, (
            f"{dead} is back: the per-control dependence machinery was "
            f"duplicated into seven blocks and is what the shared line "
            f"replaced"
        )

    master = js.index("WM.el('preview-enabled')")
    shared = js.index("WM.el('preview-depends')")
    assert master < shared, (
        "the #preview-depends block is registered BEFORE the master "
        "switch's, so its wm:settings listener reads #preview-enabled "
        "before that payload has been written into it -- the line reports "
        "the previous payload's state and nothing on the screen looks wrong"
    )


def test_hide_on_lost_focus_is_wired_end_to_end():
    """The three ends of one checkbox have to agree by NAME, and nothing
    else here checks that.

    Nothing in this suite renders the page, so a settings.js that sends a
    method api.py does not define fails the way every bridge typo fails:
    the box ticks, the promise resolves to undefined, `!res.applied` sends
    it straight back, and the only symptom is a checkbox that will not
    stay ticked. Same for an id that does not match the markup -- the
    IIFE returns at its `if (!box || !status)` guard and the control is
    simply inert.

    This is deliberately per-feature rather than a sweep over every
    WM.send target in the web sources. That general guard would be worth
    having and does not exist; it is not this change's to add.
    """
    index = (WEB / "index.html").read_text(encoding="utf-8")
    js = _strip_js_comments((WEB / "settings.js").read_text(encoding="utf-8"))
    api = (WEB.parent / "ui" / "api.py").read_text(encoding="utf-8")

    assert 'id="preview-hide-on-lost-focus"' in index
    assert 'id="preview-hide-on-lost-focus-status"' in index
    assert "WM.el('preview-hide-on-lost-focus')" in js
    assert "WM.el('preview-hide-on-lost-focus-status')" in js
    assert "WM.send('set_preview_hide_on_lost_focus'" in js
    assert "def set_preview_hide_on_lost_focus(self" in api

    # Absent must read as OFF. `!== false` -- the read show_labels, snap
    # and lock_aspect use, because their defaults are on -- would tick this
    # one for every install whose settings file predates the key, and the
    # symptom is every preview vanishing on upgrade with a ticked box to
    # explain it only after the fact. The off-by-default checkboxes
    # (preview-enabled, lock_default, minimize_inactive_clients) all read
    # truthy like this one does.
    body = js.split("WM.el('preview-hide-on-lost-focus')", 1)[1].split("}());", 1)[0]
    assert "hide_on_lost_focus === true" in body, (
        "the wm:settings read must treat an absent key as off; "
        "`!== false` would hide previews on every upgrading install"
    )


# ---- the probe formation editor ----------------------------------------


def test_the_formation_editor_is_a_route_the_title_bar_never_shows():
    """A sub-screen of Profiles, implemented as a route of its own.

    DESIGN.md makes title-bar space the scarce resource and WM.EVE_ROUTES
    already holds two entries, so the editor gets a route id and no nav
    button: it is reached from the Profiles tool row. The two halves
    that would silently break it are a missing entry in WM.route's map (the
    route element never gets `active`, so the screen is blank) and a
    missing entry in WM.EVE_ROUTES (with the EVE gate off you could still
    be standing on it, with the nav hidden and no way out -- the exact bug
    app.js's last_destination comment records).
    """
    app = _strip_js_comments((WEB / "app.js").read_text(encoding="utf-8"))
    assert 'id="route-formations"' in HTML
    assert (
        '<select id="fm-account" class="field" aria-label="Account"></select>' in HTML
    )
    assert "formations: 'route-formations'" in app
    assert 'data-route="formations"' not in HTML, (
        "the editor is reached from Profiles, not the title bar"
    )
    routes = re.search(r"WM\.EVE_ROUTES = \[([^\]]*)\]", app)
    assert routes and "'formations'" in routes.group(1), (
        "the editor hides with the other EVE destinations"
    )


def test_every_bridge_handler_has_exactly_one_owner():
    """WM.handle assigns window[name]; a second registration silently wins.

    formations.js must NOT register onEveSettingsDone -- Profiles owns it,
    and a second registration would replace the Profiles handler outright,
    leaving copy, backup and restore stuck busy for the rest of the
    session with nothing in the console to say so.
    """
    owners: dict[str, list[str]] = {}
    for path in sorted(WEB.glob("*.js")):
        if path.name == "dev.js":
            continue
        text = _strip_js_comments(path.read_text(encoding="utf-8"))
        for name in re.findall(r"WM\.handle\('([A-Za-z0-9_]+)'", text):
            owners.setdefault(name, []).append(path.name)
    doubled = {n: o for n, o in owners.items() if len(o) > 1}
    assert not doubled, f"handlers registered twice: {doubled}"
    assert owners.get("onEveSettingsDone") == ["evesettings.js"], (
        "Profiles must be the sole owner of onEveSettingsDone -- "
        "formations.js must not register it"
    )
    js = _strip_js_comments((WEB / "evesettings.js").read_text(encoding="utf-8"))
    assert "WM.formationsDone" in js, (
        "Profiles must forward onEveSettingsDone to the editor, which has "
        "no handler of its own"
    )


def test_the_formation_editor_converts_units_only_at_the_boundary():
    """The bridge speaks meters; the editor's fields are km and AU.

    Both conversions live in load() and save(), so a third one anywhere
    else is a double conversion -- and the failure is silent, because a
    formation that comes back 1000x out still renders as a formation.
    """
    js = _strip_js_comments((WEB / "formations.js").read_text(encoding="utf-8"))
    assert js.count("* KM") >= 1 and js.count("/ KM") >= 1
    assert js.count("* AU") >= 1 and js.count("/ AU") >= 1
    assert "149597870700" in js


def test_the_formation_editor_guards_both_of_its_async_windows():
    """A save is two round trips, and an edit can land in either gap.

    `save()` sends and returns; the answer arrives later as a push. The
    push then triggers a RE-READ, because Python mints a new formation's
    id at write time and the page is still holding `null` -- without
    reading it back the next save mints a second id and drops the first.

    So there are two windows in which the pane is live and an edit can be
    made: send -> push, and push -> re-read. Both end in code that
    overwrites what the user is looking at, and both failures are silent:
    the edit is on screen, then it is not, and nothing is logged. The
    first window was closed on review; the second was opened by that same
    fix and closed on the next one.

    This cannot prove the logic -- nothing here executes JavaScript -- so
    it pins the MECHANISM: each window's handler consults `revision`, the
    counter every edit bumps. A guard deleted or a third window added
    without one fails here rather than in a user's settings file.
    """
    js = _strip_js_comments((WEB / "formations.js").read_text(encoding="utf-8"))

    assert "revision += 1" in js, (
        "formations.js no longer counts edits, so neither guard below can "
        "tell an edit from no edit"
    )

    load = js[js.index("function load(") : js.index("function save(")]
    assert re.search(r"revision\s*!==\s*\w+", load), (
        "load()'s reply handler does not compare `revision` against what "
        "it captured on entry, so a reload after a save paints over an "
        "edit made while it was in flight"
    )
    assert re.search(r"=\s*revision\s*;", load), (
        "load() never captures `revision` on entry, so the comparison "
        "above cannot be against the edit count it started with"
    )

    done = js[js.index("WM.formationsDone") :]
    done = done[: done.index("\n  };")]
    assert re.search(r"revision\s*!==\s*savingAt", done), (
        "the completion push clears `dirty` without checking whether an "
        "edit landed since the send"
    )


def test_the_alert_rows_offer_exactly_the_flash_speeds_that_exist():
    """The same trap as the sound options above, one column over.

    alerts.state.FLASH_MS is what turns a speed into a duration, and
    settings.validated_alerts refuses anything not in it. A preset the
    page offers and the backend drops leaves the <select> showing a speed
    the alert does not flash at, with nothing said.
    """
    from wingman.alerts.state import FLASH_MS

    for event in _ALERT_EVENT_IDS:
        select = re.search(
            rf'<select[^>]*id="alert-event-{event}-speed".*?</select>',
            HTML,
            re.DOTALL,
        )
        assert select, f"no speed select for {event!r}"
        offered = set(re.findall(r'<option value="([^"]+)"', select.group(0)))
        assert offered == set(FLASH_MS), (
            f"the {event} speed options are {sorted(offered)}, but "
            f"alerts.state.FLASH_MS is {sorted(FLASH_MS)}"
        )


def test_every_flash_count_the_page_offers_survives_the_settings_clamp():
    """alerts.js builds the Flashes options from FLASH_COUNTS. An entry
    outside settings.validated_alerts' 1-16 range would be clamped on
    write and read back as a different number than the one clicked."""
    from wingman import settings

    js = _strip_js_comments((WEB / "alerts.js").read_text(encoding="utf-8"))
    listed = re.search(r"var FLASH_COUNTS = \[(.*?)\];", js, re.DOTALL)
    assert listed, "alerts.js no longer declares a FLASH_COUNTS list"
    counts = [int(n) for n in re.findall(r"\d+", listed.group(1))]
    assert counts, "FLASH_COUNTS is empty; the Flashes control offers nothing"
    for count in counts:
        out = settings.validated_alerts({"events": {"combat": {"pulses": count}}})
        assert out["events"]["combat"]["pulses"] == count, (
            f"the page offers {count} flashes and settings clamps it to "
            f"{out['events']['combat']['pulses']}"
        )


def test_the_volume_slider_spans_exactly_what_settings_will_keep():
    """Round 5's C2 rule, applied to a new slider: the control's units are
    the stored units, and its ends are the clamp's ends. A slider that can
    reach past the clamp reports a value the app silently changed."""
    from wingman import settings

    tag = re.search(r'<input[^>]*id="alert-volume"[^>]*>', HTML)
    assert tag, "the alert volume slider is gone"
    assert 'type="range"' in tag.group(0)
    low = int(re.search(r'min="(\d+)"', tag.group(0)).group(1))
    high = int(re.search(r'max="(\d+)"', tag.group(0)).group(1))
    kept = settings.validated_alerts({"volume": low})["volume"]
    assert kept == low, f"the slider floor {low} is clamped to {kept}"
    assert settings.validated_alerts({"volume": high})["volume"] == high
    assert settings.validated_alerts({"volume": high + 1})["volume"] == high, (
        "the slider can reach the top of the stored range, but the range "
        "does not end there"
    )


def test_the_volume_slider_commits_on_change_not_on_input():
    """A range fires `input` per pixel dragged. settings.js's opacity
    slider carries the same split for the same reason: one settings write
    per pixel is what this rule exists to prevent."""
    js = _strip_js_comments((WEB / "alerts.js").read_text(encoding="utf-8"))
    body = js[js.index("var volumeBox = WM.el('alert-volume')") :]
    input_handler = re.search(
        r"volumeBox\.addEventListener\('input', ([A-Za-z]+)\)", body
    )
    assert input_handler, "the volume readout no longer follows the thumb"
    assert input_handler.group(1) == "showVolume", (
        "the `input` handler does something other than update the readout"
    )
    assert "set_alert_volume" not in body[: body.index("'change'")], (
        "the volume commits before `change`, which is a settings write per "
        "pixel dragged"
    )


# ---------------------------------------------------------------------------
# Task 4: Group keybind rows, assignment placement, and management UI
# ---------------------------------------------------------------------------


def test_group_select_does_not_add_row_appendchild():
    """makeGroupSelect must never call row.appendChild -- that would add a
    sixth grid cell and break the five-track layout.  The cell-count guard
    (test_the_previews_grid_has_one_track_per_cell_makeRow_appends) reads
    makeRow's `row.appendChild(` calls, so a row.appendChild inside
    makeGroupSelect that is called from makeRow would silently inflate the
    count even though the selector body is in a different function."""
    src = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
    assert "function makeGroupSelect" in src, (
        "makeGroupSelect is not defined in previews.js"
    )
    body = src.split("function makeGroupSelect", 1)[1].split("\n  function ", 1)[0]
    assert "row.appendChild" not in body, (
        "makeGroupSelect calls row.appendChild; that is a sixth grid cell "
        "and breaks the five-track layout"
    )


def test_group_select_is_owned_by_the_character_detail():
    """Assignment is an infrequent per-character setting, not a roster cell."""
    body = _makerow_body()
    assert "makeGroupSelect" not in body

    src = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
    detail = src.split("function makeCharacterDetail(", 1)[1].split("\n  function ", 1)[
        0
    ]
    assert "groups().length" in detail
    assert "makeGroupSelect(characterName)" in detail


def test_group_select_is_styled_inside_the_detail_without_a_new_track():
    """The detail preserves the five collapsed-row tracks."""
    assert ".preview-character-detail .preview-group-select" in CSS
    assert _preview_binds_cell_tracks() == 5


def test_character_roster_rows_keep_configuration_out_of_the_scan_line():
    """Collapsed rows expose only identity, Preview, keybind actions, Configure."""
    src = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
    body = src.split("function makeRow(", 1)[1].split("return row;", 1)[0]
    assert "makeGroupSelect" not in body
    assert "makeGeometryActions" not in body
    assert "'Configure'" in body
    assert "aria-expanded" in body
    assert "aria-controls" in body


def test_character_detail_and_conflict_siblings_span_the_preview_grid():
    """Secondary detail and conditional copy cannot consume a data track."""
    src = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
    assert "function makeCharacterDetail(" in src
    detail = src.split("function makeCharacterDetail(", 1)[1].split("\n  function ", 1)[
        0
    ]
    assert "makeGroupSelect" in detail
    assert "makeGeometryActions" in detail

    for selector in (".preview-character-detail", ".preview-bind-conflict"):
        rule = re.search(rf"{re.escape(selector)}\s*\{{(.*?)\}}", CSS, re.DOTALL)
        assert rule and "grid-column: 1 / -1" in rule.group(1), (
            f"{selector} must span the Preview grid rather than add a row cell"
        )


def test_character_conflict_copy_excludes_supported_direct_sharers():
    """A shared direct bind is supported, so a character's warning names
    only the incompatible cycle owner rather than other sharing characters.
    """
    js = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
    block = js.split("function makeBindConflict", 1)[1].split("\n  function ", 1)[0]
    character_duplicate = block.split("if (character && clash === 'duplicate')", 1)[
        1
    ].split("} else", 1)[0]
    assert "cycleOwners(gesture)" in character_duplicate
    assert "sharers(gesture)" not in character_duplicate, (
        "character conflict copy calls sharers(), so it blames supported "
        "direct-character sharing for a cycle collision"
    )


def test_character_detail_precedes_its_conflict_copy():
    """A character's detail belongs directly below its row; any warning
    follows the detail so it cannot split the row from the controls it explains.
    """
    js = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
    append = js.split("function appendBindRow", 1)[1].split("function render()", 1)[0]
    row = append.index("host.appendChild(makeRow")
    detail = append.index("host.appendChild(makeCharacterDetail")
    conflict = append.index("host.appendChild(conflict)")
    assert row < detail < conflict


def test_bind_conflict_names_its_owner_so_it_survives_a_sticky_scroll():
    """A conflict is a full-span sibling directly after the row it explains
    (appendBindRow), and that row can scroll out from under the sticky
    column or Offline heading while the warning below it is still on
    screen. Every text-producing branch must therefore open with the
    owning character, cycle command, or named group by name, rather than
    counting on the reader having just seen the row above.
    """
    js = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
    block = js.split("function makeBindConflict", 1)[1].split("\n  function ", 1)[0]
    assert block.count("label + ': ' + gesture") == 4, (
        "makeBindConflict must open every conflict sentence with its own "
        "label -- the owning character, cycle command, or named group -- "
        "so the message names its owner even once the row it explains has "
        "scrolled under a sticky header"
    )


def test_bind_conflict_gets_a_stable_id_for_its_bind_button_to_reference():
    """The warning and the control it explains must be associated by a
    stable id, not by DOM adjacency, so the association survives a
    rerender and a scroll alike. The id is assigned in appendBindRow from
    the SAME ownerKey makeBindConflict filters genuine owners by --
    computed once, so the id a reader's aria-describedby follows and the
    identity makeBindConflict excludes itself by can never drift apart.
    """
    js = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
    assert "function bindConflictId(ownerKey)" in js
    id_fn = js.split("function bindConflictId", 1)[1].split("\n  function ", 1)[0]
    assert "encodeURIComponent(ownerKey)" in id_fn

    append = js.split("function appendBindRow", 1)[1].split("function render()", 1)[0]
    assert "var ownerKey = character ? 'character:' + character : ownerKind;" in append
    assert "conflict.id = bindConflictId(ownerKey)" in append


def test_cycle_owners_carry_a_stable_key_beside_their_rendered_text():
    """cycleOwners must expose the same owner key each row's own conflict
    id is built from (bindConflictId/appendBindRow) alongside the rendered
    text, so makeBindConflict can tell a genuinely different owner apart
    from itself by identity -- never by comparing rendered label text,
    which a named group is free to share with a fixed cycle label or with
    a character.
    """
    js = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
    body = js.split("function cycleOwners(gesture)", 1)[1].split("\n  function ", 1)[0]
    assert "key: 'cycle:next'" in body
    assert "key: 'cycle:prev'" in body
    assert "key: 'group:' + group.id" in body
    assert "text: 'All forward'" in body
    assert "text: 'All back'" in body
    assert "text: 'cycle group ' + group.name" in body


def test_makebindconflict_filters_conflicting_owners_by_key_not_by_label():
    """A named group may legally be named exactly "All forward"/"All
    back", or share a name with a character -- create/rename_preview_cycle_
    group enforce uniqueness only among groups, never against a character
    or the two fixed cycle labels. Filtering cycleOwners()/sharers() by
    comparing rendered TEXT against this row's own `label` therefore drops
    a genuine conflicting owner whenever its rendered text happens to
    match this row's label: rendering the fixed All-forward cycle row lost
    a genuinely conflicting group actually named "All forward", and
    rendering any cycle/group row lost a genuinely sharing character
    actually named after that row's own label. makeBindConflict must
    instead filter by comparing each owner's stable `.key` against the
    caller's own `ownerKey`.
    """
    js = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
    block = js.split("function makeBindConflict", 1)[1].split("\n  function ", 1)[0]
    assert "owner.key !== ownerKey" in block, (
        "makeBindConflict must filter cycleOwners()/sharers() entries by "
        "comparing owner.key against this row's own ownerKey"
    )
    assert "owner !== label" not in block, (
        "filtering by `owner !== label` drops a genuine conflicting owner "
        "whenever its rendered text matches this row's own label -- a "
        "named group or character is free to share that label"
    )
    assert "'cycle group ' + label" not in block, (
        "filtering by a label-derived 'cycle group ' + label string drops "
        "a genuinely different group whenever it happens to share this "
        "row's own label -- e.g. a group literally named 'All forward'"
    )
    # Sharer characters must be wrapped with their own stable owner key
    # ('character:NAME'), not compared as bare name strings, so a
    # character sharing a cycle/group row's own label is excluded (or
    # kept) by identity and never dropped for a text coincidence.
    assert "key: 'character:' + name" in block, (
        "sharer characters must be wrapped with their own stable owner "
        "key before being filtered, not compared as bare name strings"
    )


def test_bind_conflict_id_keys_off_owner_kind_not_display_label():
    """A named group may legally be named exactly "All forward" or "All
    back" -- create_preview_cycle_group and rename_preview_cycle_group only
    enforce uniqueness among groups, never against the two fixed cycle
    labels. A label-derived conflict id would then collide with the real
    All-forward or All-back row's id, leaving aria-describedby pointing at
    an ambiguous target. bindConflictId must therefore key off an explicit
    owner kind supplied by each call site -- never off `label` at all --
    and the fixed cycle rows and named-group rows must each pass a token
    that cannot collide with the other kind's, whatever a group is named
    or however its id is generated.
    """
    js = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))

    assert "function bindConflictId(" in js, "bindConflictId is not defined"
    id_fn = js.split("function bindConflictId(", 1)[1].split("\n  function ", 1)[0]
    params = id_fn.split(") {", 1)[0]
    assert "label" not in params, (
        "bindConflictId must not accept the display label at all -- a "
        "label-keyed id cannot distinguish a fixed cycle row from a named "
        "group sharing its exact label"
    )

    # Each non-character row passes an explicit, fixed owner-kind token --
    # not anything derived from `label` or `group.name` -- so a group
    # named "All forward"/"All back" cannot alias the real cycle row.
    assert "'cycle:next'" in js, (
        "the All-forward row must pass a fixed owner-kind token distinct "
        "from any group's own key"
    )
    assert "'cycle:prev'" in js, (
        "the All-back row must pass a fixed owner-kind token distinct "
        "from any group's own key"
    )
    assert "'group:' + group.id" in js, (
        "a named-group row must key off its own stable group.id, not its "
        "user-chosen (and therefore collidable) group.name"
    )


def test_bind_row_button_references_its_conflict_via_aria_describedby():
    """The bind button -- not a wrapper, and not the row -- carries the
    programmatic association, wired only while a conflict is actually
    rendered so a fresh button never points at a warning this render did
    not append.
    """
    body = _makerow_body()
    params = body.split(") {", 1)[0]
    assert params == "label, gesture, online, onSet, character, conflict", (
        "makeRow must accept the conflict element so its bind button can "
        "reference the exact node id rendered for this row"
    )
    assert "if (conflict) {" in body
    assert "button.setAttribute('aria-describedby', conflict.id)" in body

    append = (
        _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
        .split("function appendBindRow", 1)[1]
        .split("function render()", 1)[0]
    )
    conflict_computed = append.index("var conflict = makeBindConflict(")
    row_built = append.index("host.appendChild(makeRow")
    assert conflict_computed < row_built, (
        "the conflict element must exist before makeRow builds the button "
        "that references its id"
    )
    assert "makeRow(label, gesture, online, onSet, character, conflict)" in append


def test_geometry_focus_intent_is_scoped_to_the_copy_refresh():
    """Size has no authoritative redraw, and Copy's intent is installed only
    inside its refresh response. Cancellation and a failed copy therefore cannot
    leave intent for a later unrelated push to consume.
    """
    js = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
    size = js.split("function makeSizeButton", 1)[1].split("\n  function ", 1)[0]
    assert "rememberDetailFocus" not in size, (
        "Size patches local state without rerendering; it must not retain a "
        "detail focus intent across cancellation or parse/save failure"
    )

    copy = js.split("function makeCopyButton", 1)[1].split("\n  function ", 1)[0]
    cancelled = copy.split("if (source === null)", 1)[1].split("}", 1)[0]
    assert "clearDetailFocus(name, 'copy')" in cancelled
    assert (
        copy.count("restoreCopyFocusAfterRefresh(name, interaction, attempt)") == 2
    ), (
        "both the refused and successful copy paths must refresh with the initiating "
        "detail interaction and Copy attempt"
    )

    restore = js.split("function restoreCopyFocusAfterRefresh", 1)[1].split(
        "\n  function ", 1
    )[0]
    assert "refresh(function ()" in restore
    assert "rememberDetailFocus(name, 'copy')" in restore
    assert "interaction !== detailInteraction" in restore
    assert "openDetailName !== name" in restore
    assert "attempt !== copyAttempt" in restore


def test_preview_roster_heading_is_a_programmatic_focus_fallback():
    """Removing an open character focuses the generated roster header, not the card."""
    src = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
    head = src.split("function makeHeadRow", 1)[1].split("return row;", 1)[0]
    assert "cell.id = 'preview-roster-heading'" in head
    assert "cell.setAttribute('tabindex', '-1')" in head


# ---- Final-review fixes: disclosure, roster, busy guard, minor ----


def test_makeGroupManager_is_a_details_element():
    """Finding #2: makeGroupManager must build a <details>, not a plain
    div.  A plain div is always expanded and inherits the sticky
    bind-group heading CSS that can overlay rows."""
    src = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
    block = src.split("function makeGroupManager", 1)[1].split("\n  function ", 1)[0]
    assert (
        "document.createElement('details')" in block or "WM.make('details'" in block
    ), (
        "makeGroupManager does not create a <details> element; it must use a "
        "real HTML disclosure so the panel can be collapsed"
    )


def test_makeGroupManager_has_summary_with_derived_count():
    """Finding #2: the <summary> must show a derived group count, not a
    static label.  Count derivation must read groups().length or an
    equivalent expression."""
    src = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
    block = src.split("function makeGroupManager", 1)[1].split("\n  function ", 1)[0]
    assert (
        "document.createElement('summary')" in block or "WM.make('summary'" in block
    ), "makeGroupManager does not create a <summary> element"
    # The summary text must be derived from the group count, not static.
    # Any of: groups().length, groups.length, state.hotkeys.groups.length
    assert re.search(r"groups\(\)\.length|groups\.length|\.groups\.length", block), (
        "makeGroupManager summary does not derive a count from the group list"
    )


def test_makeGroupManager_open_state_is_preserved_across_rerenders():
    """Finding #2: the open state must be saved across rerenders so
    Add/Rename/Delete focus restoration targets an attached visible
    field.  A module-level flag (or equivalent) must track whether the
    details is open."""
    src = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
    # A variable holding the open state must exist at module scope (outside
    # any function) and be read when building the manager.
    # Common name patterns: _groupManagerOpen, groupManagerOpen, managerOpen
    assert re.search(
        r"^\s*var\s+(groupManagerOpen|_groupManagerOpen|managerOpen|groupsOpen)\b",
        src,
        re.MULTILINE,
    ), (
        "No module-level open-state variable found for the group manager "
        "disclosure; open state cannot survive a rerender"
    )
    # The makeGroupManager block must reference that variable.
    block = src.split("function makeGroupManager", 1)[1].split("\n  function ", 1)[0]
    assert re.search(
        r"groupManagerOpen|_groupManagerOpen|managerOpen|groupsOpen", block
    ), (
        "makeGroupManager does not read the open-state variable; the details "
        "panel will collapse on every rerender"
    )


def test_makeGroupManager_does_not_use_bind_group_class():
    """Finding #2: the manager must NOT use the bind-group class, which
    carries sticky-positioning CSS that can overlay rows."""
    src = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
    block = src.split("function makeGroupManager", 1)[1].split("\n  function ", 1)[0]
    # The top-level element must not be a 'bind-group', but child rows may
    # still use whatever class they need.  We test only the creation call
    # for the outermost element.
    first_make = re.search(
        r"(?:WM\.make|document\.createElement)\s*\(['\"](?:details|div)['\"]"
        r"(?:,\s*['\"]([^'\"]*)['\"])?",
        block,
    )
    assert first_make, "makeGroupManager creation call not found"
    outer_class = first_make.group(1) or ""
    assert "bind-group" not in outer_class.split(), (
        "makeGroupManager outer element uses bind-group class, which inherits "
        "sticky positioning and can overlay rows"
    )


def test_group_manager_css_does_not_apply_sticky_positioning():
    """Finding #2: the dedicated manager class must not carry position:sticky,
    since the manager is a full-grid-span disclosure, not a section header."""
    assert "preview-group-manager" in CSS or "group-manager" in CSS, (
        "no .preview-group-manager rule found in style.css"
    )
    # Find the preview-group-manager block.
    m = re.search(r"\.preview-group-manager\s*\{([^}]*)\}", CSS)
    if m:
        assert "sticky" not in m.group(1), (
            ".preview-group-manager has position:sticky which would overlay rows"
        )


def test_rows_includes_group_by_character_keys():
    """Finding #3: rows() must include every key in
    hotkeys.group_by_character so persisted offline assignments always
    have a select that can clear them."""
    src = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
    block = src.split("function rows()", 1)[1].split("function sharers", 1)[0]
    assert "group_by_character" in block, (
        "rows() does not consult hotkeys.group_by_character; a character with "
        "a persisted assignment but no running/seen/bind entry has no row and "
        "no way to clear the assignment"
    )


def test_every_group_mutation_handler_has_synchronous_busy_guard():
    """Finding #4: setGroupBind, makeGroupSelect's change handler, doAdd,
    renameGroup, and deleteGroup must all check `if (groupBusy) { return; }`
    synchronously before sending anything, so a second click during capture
    cannot submit twice."""
    src = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))

    # setGroupBind
    gb_block = src.split("function setGroupBind", 1)[1].split("\n  function ", 1)[0]
    assert re.search(r"if\s*\(\s*groupBusy\s*\)\s*\{?\s*return", gb_block), (
        "setGroupBind lacks a synchronous groupBusy early-return guard"
    )

    # makeGroupSelect's change handler
    sel_block = src.split("function makeGroupSelect", 1)[1].split("\n  function ", 1)[0]
    assert re.search(r"if\s*\(\s*groupBusy\s*\)\s*\{?\s*return", sel_block), (
        "makeGroupSelect change handler lacks a synchronous groupBusy guard"
    )

    # doAdd inside makeGroupManager
    mgr_block = src.split("function makeGroupManager", 1)[1].split("\n  function ", 1)[
        0
    ]
    assert re.search(r"if\s*\(\s*groupBusy\s*\)\s*\{?\s*return", mgr_block), (
        "makeGroupManager (doAdd) lacks a synchronous groupBusy guard"
    )

    # renameGroup
    ren_block = src.split("function renameGroup", 1)[1].split("\n  function ", 1)[0]
    assert re.search(r"if\s*\(\s*groupBusy\s*\)\s*\{?\s*return", ren_block), (
        "renameGroup lacks a synchronous groupBusy early-return guard"
    )

    # deleteGroup
    del_block = src.split("function deleteGroup", 1)[1].split("\n  function ", 1)[0]
    assert re.search(r"if\s*\(\s*groupBusy\s*\)\s*\{?\s*return", del_block), (
        "deleteGroup lacks a synchronous groupBusy early-return guard"
    )


def test_group_focus_restoration_delegates_to_the_current_detail_intent():
    """A group response must never independently focus a closed detail."""
    src = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
    block = src.split("function focusGroupSelect", 1)[1].split("\n  function ", 1)[0]
    assert "detailFocusIntent.name !== characterName" in block
    assert "restoreDetailFocus()" in block
    assert "querySelector" not in block


def test_refusal_handler_applies_authoritative_hotkeys_on_generation_match():
    """Minor finding: on a refused group write where res.hotkeys exists and
    no newer push won, the handler must apply res.hotkeys to state.hotkeys
    directly rather than relying solely on a full refresh() round-trip.
    A sole refresh() leaves a stale/deleted group visible for an extra
    round-trip."""
    src = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
    gb_block = src.split("function setGroupBind", 1)[1].split("\n  function ", 1)[0]
    # Isolate the refusal arm: after '!res.applied' up to the first 'return;'
    if "!res.applied" in gb_block:
        after_guard = gb_block.split("!res.applied", 1)[1]
        refusal_arm = after_guard.split("return;", 1)[0]
        only_refresh = (
            "res.hotkeys" not in refusal_arm
            and "state.hotkeys" not in refusal_arm
            and "refresh()" in refusal_arm
        )
        assert not only_refresh, (
            "setGroupBind refusal arm calls only refresh(); when res.hotkeys "
            "exists and no newer push won, it must apply res.hotkeys directly "
            "to avoid showing a stale group during the refresh round-trip"
        )


# ---------------------------------------------------------------------------
# Final-fix wave 2 tests
# ---------------------------------------------------------------------------


def test_closed_details_hides_group_manager_body():
    """Fix wave 2 - closed-details display: the .group-manager-body rule sets
    display:flex, but that overrides Chromium's UA rule that hides non-summary
    children of a closed <details>.  A rule scoped to
    .preview-group-manager:not([open]) must set display:none on the body so
    the panel actually collapses.

    The rule must exist because without it the body remains visible even when
    the <details> element is closed, making the 'collapse' feature inoperable
    in WebView2.
    """
    # Check that there is a rule that forces display:none on .group-manager-body
    # (or a direct child) when the manager lacks [open].
    not_open_body_hidden = bool(
        re.search(
            r"\.preview-group-manager:not\(\[open\]\)\s*[>~+\s]"
            r"*[.#\w-]*group-manager-body[^}]*display\s*:\s*none",
            CSS,
            re.DOTALL,
        )
        or re.search(
            r"\.preview-group-manager:not\(\[open\]\)\s*\{[^}]*display\s*:\s*none",
            CSS,
            re.DOTALL,
        )
    )
    assert not_open_body_hidden, (
        ".preview-group-manager:not([open]) does not set display:none on "
        ".group-manager-body.  Without this rule, Chromium's UA stylesheet "
        "cannot hide the body when the <details> is closed because the author "
        "display:flex declaration on .group-manager-body wins."
    )


def _extract_refusal_arm(block):
    """Return the text between '!res.applied' and the first 'return;' that
    follows it -- the refusal arm of a then-callback."""
    if "!res.applied" not in block:
        return ""
    after = block.split("!res.applied", 1)[1]
    arm, _, _ = after.partition("return;")
    return arm


def test_assignment_refusal_applies_authoritative_hotkeys():
    """Fix wave 2 - makeGroupSelect's refusal branch must apply res.hotkeys to
    state.hotkeys when res.hotkeys is present and no newer push has landed
    (generation/before guard).  Without this, a refused assignment leaves the
    page showing stale group membership until the next refresh() round-trip.

    The branch must still clear groupBusy (unconditionally, before any return),
    call requestRender(), and restore focus via focusGroupSelect().
    """
    src = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
    # Isolate makeGroupSelect's then-callback
    ms_block = src.split("function makeGroupSelect", 1)[1].split("\n  function ", 1)[0]
    refusal_arm = _extract_refusal_arm(ms_block)

    # Must apply res.hotkeys under a generation/before guard
    has_hotkeys_assign = "res.hotkeys" in refusal_arm and "state.hotkeys" in refusal_arm
    has_generation_guard = "pushes" in refusal_arm and "before" in refusal_arm
    assert has_hotkeys_assign, (
        "makeGroupSelect refusal arm does not assign res.hotkeys to state.hotkeys; "
        "the authoritative table must be applied on generation match to avoid a "
        "stale-group round-trip"
    )
    assert has_generation_guard, (
        "makeGroupSelect refusal arm applies res.hotkeys without a generation "
        "guard (pushes !== before check); a newer push's table would be "
        "overwritten by the stale response"
    )

    # Cleanup must be unconditional: groupBusy=false, requestRender, focus
    assert "groupBusy = false" in ms_block, (
        "makeGroupSelect callback does not reset groupBusy; busy lock leaks"
    )
    assert "requestRender()" in ms_block, (
        "makeGroupSelect refusal arm does not call requestRender()"
    )
    assert "focusGroupSelect" in ms_block, (
        "makeGroupSelect refusal arm does not restore focus via focusGroupSelect"
    )


def test_add_refusal_applies_authoritative_hotkeys():
    """Fix wave 2 - doAdd's refusal branch must apply res.hotkeys to
    state.hotkeys when res.hotkeys is present and no newer push has landed
    (before guard).  Without this, a refused add leaves the page showing a
    potentially stale groups list until the next refresh().

    groupBusy=false and requestRender() must remain unconditional.
    """
    src = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
    # doAdd is a closure inside makeGroupManager; isolate from doAdd to the
    # next closure-level function definition.
    da_block = src.split("function doAdd()", 1)[1].split("\n    function ", 1)[0]
    refusal_arm = _extract_refusal_arm(da_block)

    has_hotkeys_assign = "res.hotkeys" in refusal_arm and "state.hotkeys" in refusal_arm
    has_generation_guard = "pushes" in refusal_arm and "before" in refusal_arm
    assert has_hotkeys_assign, (
        "doAdd refusal arm does not apply res.hotkeys to state.hotkeys; "
        "refused add should still show the authoritative groups list"
    )
    assert has_generation_guard, (
        "doAdd refusal arm applies res.hotkeys without checking pushes !== before; "
        "a newer push's authoritative table would be overwritten"
    )

    assert "groupBusy = false" in da_block, "doAdd callback does not reset groupBusy"
    assert "requestRender()" in da_block, (
        "doAdd refusal arm does not call requestRender()"
    )


def test_rename_refusal_applies_authoritative_hotkeys():
    """Fix wave 2 - renameGroup's refusal branch must apply res.hotkeys to
    state.hotkeys when res.hotkeys is present and no newer push has landed
    (before guard).  Without this, a refused rename leaves the stale name
    visible until the next refresh().

    groupBusy=false, requestRender(), and focusGroupManager() must be
    unconditional (fire on every refusal, not only when hotkeys is absent).
    """
    src = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
    rg_block = src.split("function renameGroup", 1)[1].split("\n  function ", 1)[0]
    refusal_arm = _extract_refusal_arm(rg_block)

    has_hotkeys_assign = "res.hotkeys" in refusal_arm and "state.hotkeys" in refusal_arm
    has_generation_guard = "pushes" in refusal_arm and "before" in refusal_arm
    assert has_hotkeys_assign, (
        "renameGroup refusal arm does not apply res.hotkeys to state.hotkeys; "
        "a refused rename should show the authoritative (unchanged) name"
    )
    assert has_generation_guard, (
        "renameGroup refusal arm applies res.hotkeys without a generation guard; "
        "a newer push's table would be overwritten"
    )

    assert "groupBusy = false" in rg_block, (
        "renameGroup callback does not reset groupBusy"
    )
    assert "requestRender()" in rg_block, (
        "renameGroup refusal arm does not call requestRender()"
    )
    assert "focusGroupManager" in rg_block, (
        "renameGroup refusal arm does not restore focus via focusGroupManager"
    )


def test_delete_refusal_applies_authoritative_hotkeys():
    """Fix wave 2 - deleteGroup's refusal branch must apply res.hotkeys to
    state.hotkeys when res.hotkeys is present and no newer push has landed
    (before guard).  Without this, a refused delete shows a stale groups list
    until the next refresh().

    groupBusy=false, requestRender(), and focusGroupManager() must be
    unconditional.
    """
    src = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
    dg_block = src.split("function deleteGroup", 1)[1].split("\n  function ", 1)[0]
    refusal_arm = _extract_refusal_arm(dg_block)

    has_hotkeys_assign = "res.hotkeys" in refusal_arm and "state.hotkeys" in refusal_arm
    has_generation_guard = "pushes" in refusal_arm and "before" in refusal_arm
    assert has_hotkeys_assign, (
        "deleteGroup refusal arm does not apply res.hotkeys to state.hotkeys; "
        "a refused delete should show the authoritative groups list"
    )
    assert has_generation_guard, (
        "deleteGroup refusal arm applies res.hotkeys without a generation guard; "
        "a newer push's table would be overwritten"
    )

    assert "groupBusy = false" in dg_block, (
        "deleteGroup callback does not reset groupBusy"
    )
    assert "requestRender()" in dg_block, (
        "deleteGroup refusal arm does not call requestRender()"
    )
    assert "focusGroupManager" in dg_block, (
        "deleteGroup refusal arm does not restore focus via focusGroupManager"
    )


# ---- profile identity: generation-gated staleness (Task 6) -------------


def test_identification_generation_is_retained_from_zero():
    """Task 5 made every identification start/check/cancel response, and
    the onEveSettingsNames push, carry identification_generation. Task 6
    must retain the last one observed so a response or push older than it
    can be told apart from the latest and discarded.
    """
    src = _strip_js_comments((WEB / "evesettings.js").read_text(encoding="utf-8"))
    assert "var identificationGeneration = 0;" in src, (
        "evesettings.js does not retain an identificationGeneration counter "
        "initialized to zero"
    )
    assert "function acceptIdentification(" in src, (
        "evesettings.js has no acceptIdentification helper to reject stale "
        "identification responses/pushes"
    )


def test_generation_is_observed_before_deleted_candidate_inspection():
    """onEveSettingsNames must update the retained generation before
    inspecting deleted_candidate_ids, so event-before-promise and
    promise-before-event both apply the newer of the two in the same
    order: the generation that authorizes the inspection is observed
    first, not derived from the outcome of the inspection.
    """
    src = _strip_js_comments((WEB / "evesettings.js").read_text(encoding="utf-8"))
    handler = src.split("WM.handle('onEveSettingsNames'", 1)[1]
    handler = handler.split("\n  });", 1)[0]
    accept_at = handler.find("acceptIdentification(")
    deleted_at = handler.find("deleted_candidate_ids")
    assert accept_at != -1 and deleted_at != -1, (
        "onEveSettingsNames does not both observe the generation and "
        "inspect deleted_candidate_ids"
    )
    assert accept_at < deleted_at, (
        "onEveSettingsNames inspects deleted_candidate_ids before observing "
        "the generation that authorizes the inspection"
    )


def test_every_render_candidate_call_is_preceded_by_a_generation_check():
    """Every path that paints an identification candidate must first
    confirm the response is not older than one already applied -- a stale
    'candidate' response racing a newer cancel or restart must not repaint
    an offer the user already dismissed.
    """
    src = _strip_js_comments((WEB / "evesettings.js").read_text(encoding="utf-8"))
    calls = [m.start() for m in re.finditer(r"renderCandidate\(result\)", src)]
    assert calls, "no renderCandidate(result) call sites found"
    for pos in calls:
        preceding = src[:pos]
        block_start = preceding.rfind("function (result)")
        block = src[block_start:pos] if block_start != -1 else preceding
        assert "acceptIdentification(result)" in block, (
            "a renderCandidate(result) call site has no preceding "
            "acceptIdentification(result) guard in its enclosing callback"
        )


def test_a_cancelled_identification_check_response_is_idle_with_no_message():
    """Binding ruling from the Task 5 review: a generation-cancelled
    eve_settings_identification_check response must not fall into the
    generic branch, which used to paint 'watching' with the false
    no-changes message. It must be recognized explicitly and treated as
    idle with no message.
    """
    src = _strip_js_comments((WEB / "evesettings.js").read_text(encoding="utf-8"))
    check_block = src.split("WM.el('es-identify-check').addEventListener", 1)[1].split(
        "\n\n    WM.el('es-identify-cancel')", 1
    )[0]
    assert "'cancelled'" in check_block, (
        "the check click handler has no explicit 'cancelled' branch"
    )
    cancelled_arm = check_block.split("'cancelled'", 1)[1].split("}", 1)[0]
    assert "paintIdentification('idle')" in cancelled_arm, (
        "a cancelled check response must return to idle with no message, "
        "not the generic watching/no-changes branch"
    )


def test_a_deleted_candidate_clears_local_state_with_the_approved_message():
    """onEveSettingsNames must clear the offered candidate and repaint
    idle with the approved copy when the pushed deleted_candidate_ids
    intersect the character currently offered.
    """
    src = _strip_js_comments((WEB / "evesettings.js").read_text(encoding="utf-8"))
    assert "That character was deleted. Start account identification again." in src, (
        "the approved deleted-candidate reset message is missing"
    )


def test_account_identity_controls_are_gated_by_the_payload_flag():
    """Design: account identification and manual account-link controls
    are unavailable outside a trusted Tranquility context. The page must
    take that from account_identity_available, never from server/path
    text reimplemented in JavaScript.
    """
    src = _strip_js_comments((WEB / "evesettings.js").read_text(encoding="utf-8"))
    assert "state.account_identity_available" in src, (
        "no identity control is gated on state.account_identity_available"
    )
    can_identify = re.search(r"var canIdentify = ([^;]*);", src, re.DOTALL)
    assert can_identify and "account_identity_available" in can_identify.group(1), (
        "canIdentify does not require account_identity_available"
    )


def test_on_eve_settings_names_handler_remains_the_sole_registration():
    """Task 6 changes onEveSettingsNames's body (it now takes a payload),
    not its name or its owner."""
    app = (WEB / "app.js").read_text(encoding="utf-8")
    assert "'onEveSettingsNames'" in app
    ev = _strip_js_comments((WEB / "evesettings.js").read_text(encoding="utf-8"))
    assert ev.count("WM.handle('onEveSettingsNames'") == 1, (
        "onEveSettingsNames must be registered exactly once, in evesettings.js"
    )
