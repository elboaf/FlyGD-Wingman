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


def test_an_id_override_of_the_label_column_still_collapses_at_the_floor():
    """Two bind lists take the shared 118px label column away from their
    rows on purpose -- their labels are long action and character names,
    not "Privacy" -- with an ID selector: `#eve-binds .row > .lab` and
    `#preview-binds .row > .lab`.

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

    # The BODIES of every max-width:720px block, brace-matched. Slicing from
    # the first occurrence to the end is not enough: these rules may sit
    # beside the override they correct, so such a slice also contains the
    # override itself and the assertion passes on the wrong text. That is
    # not hypothetical -- the first version of this test did exactly that
    # and survived deleting the rule it exists to require.
    narrow = []
    for m in re.finditer(r"@media \(max-width: 720px\)\s*\{", CSS):
        i, depth = m.end(), 1
        while i < len(CSS) and depth:
            depth += {"{": 1, "}": -1}.get(CSS[i], 0)
            i += 1
        narrow.append(CSS[m.end() : i - 1])
    body = "\n".join(narrow)

    for host in sorted(overrides):
        assert f"{host} .row > .lab" in body, (
            f"{host} out-specifies the shared label column but never "
            f"restores its collapse below 720px"
        )


def test_the_two_keybind_lists_render_the_same_row():
    """Bookmarks and Previews build a keybind row from the same four
    elements, and for two rounds they rendered it at two geometries.

    Each list is its own grid, and the first track used to be max-content
    over ITS OWN labels -- so the column was 189.6px in Bookmarks ("Convert
    EvE-Scout Bookmarks") and 86.2px in Previews ("Cycle forward"), putting
    the bind button 103.4 CSS px apart in two sections of one screen.
    Previews' half of that is not even stable between sessions: the track
    tracked whichever characters were logged in. Round 3's B1.

    The fix was to stack the name above its controls in both, so the
    geometry depends on no content at all. Nothing renders the page in this
    suite, so what stops the two drifting apart again is this: the two
    grids must declare control tracks of the same KIND and the same
    flexible trailing track, and both must put the name on its own line.
    Both halves are read out of the stylesheet rather than restated here,
    so the test cannot disagree with the file about what the shared value
    is -- only about whether it is shared.

    THIS USED TO BE A BYTE-EQUALITY CHECK on the two templates, and it was
    RELAXED DELIBERATELY -- it did not erode. Previews grew two
    per-character controls, Lock and Never minimize, that Bookmarks has no
    equivalent of, so the two templates now share a prefix and then
    diverge: three control tracks against five. Byte equality could only
    have been restored by giving Bookmarks two tracks holding nothing,
    which would be a lie in the stylesheet about a row that has three
    controls.

    What matters is that byte equality was never the invariant, only a
    proxy for it. B1 was the bind button sitting at two different offsets;
    that offset is decided by `.lab { grid-column: 1 / -1 }`, asserted
    below and untouched, which puts the name on its own line and starts
    the control line at the container edge in both lists. Measured in the
    ?dev=1 harness at 840x625 after the divergence: the bind button is at
    offset 0 in BOTH, and the three shared control tracks compute
    identically at 150 / 40.7969 / 42.4531px. So what is guarded here is
    what is left -- the shared tracks must still be the same KIND of track
    (a content-sized column, not one list switching to a fixed or
    fractional one), and neither list may drop the trailing flexible track
    that lets `grid-column: 1 / -1` reach the card's width instead of the
    control tracks' width.
    """
    hosts = ("#eve-binds", "#preview-binds")

    columns = {}
    for host in hosts:
        m = re.search(re.escape(host) + r" \{(.*?)\}", CSS, re.DOTALL)
        assert m, f"{host} has no rule block at all"
        tracks = re.search(r"grid-template-columns:\s*([^;]+);", m.group(1))
        assert tracks, f"{host} declares no grid-template-columns"
        columns[host] = " ".join(tracks.group(1).split())

    # Split each template into "how many control tracks", "of what kind",
    # and "what trails them". Anchored and whole-string: a template this
    # cannot parse fails here rather than being waved through, which is
    # what stops the relaxation above from widening any further by
    # accident.
    shape = {}
    for host in hosts:
        m = re.fullmatch(r"repeat\((\d+),\s*([^)]+)\)\s+(.+)", columns[host])
        assert m, (
            f"{host} no longer declares its columns as `repeat(N, <kind>) "
            f"<trailing>`, so this test can no longer tell whether the two "
            f"lists still agree: {columns[host]!r}"
        )
        shape[host] = (int(m.group(1)), m.group(2).strip(), m.group(3).strip())

    bookmarks, previews = shape["#eve-binds"], shape["#preview-binds"]

    assert bookmarks[1] == previews[1], (
        "the two keybind lists size their control tracks differently, which "
        f"puts their shared controls back at two geometries -- round 3's B1: "
        f"{bookmarks[1]!r} vs {previews[1]!r}"
    )

    for host in hosts:
        assert shape[host][2] == "minmax(0, 1fr)", (
            f"{host} dropped the flexible trailing track, so its full-width "
            f"name now reaches only as far as its control tracks instead of "
            f"the card: {shape[host][2]!r}"
        )

    # Previews may carry MORE controls than Bookmarks -- Lock and Never
    # minimize are per-character and Bookmarks has no character. It may not
    # carry fewer: that would mean a control went missing from the row
    # rather than being added to it.
    assert previews[0] >= bookmarks[0], (
        f"Previews declares fewer control tracks than Bookmarks "
        f"({previews[0]} < {bookmarks[0]}), so a control its rows build has "
        f"no column to sit in"
    )

    for host in hosts:
        m = re.search(re.escape(host) + r" \.row > \.lab \{(.*?)\}", CSS, re.DOTALL)
        assert m, f"{host} has no .lab override"
        assert "grid-column: 1 / -1" in m.group(1), (
            f"{host}'s name no longer takes its own line, so its bind button "
            f"is back at an offset that depends on that list's own labels"
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
    """
    assert 'style="display:none"' not in HTML, (
        "an element hides with an inline display style; use the `hidden` "
        "attribute so test_every_hidden_element_can_actually_hide sees it"
    )
    for name in (
        "alerts.js",
        "previews.js",
        "settings.js",
        "bookmarks.js",
        "skills.js",
        "list.js",
        "panel.js",
        "app.js",
        "firstrun.js",
        "evesettings.js",
    ):
        src = _strip_js_comments((WEB / name).read_text(encoding="utf-8"))
        assert ".style.display" not in src, (
            f"{name} hides an element by writing style.display; set "
            f"`el.hidden` instead so the [hidden] guard covers it"
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


def test_the_previews_grid_drops_exactly_one_track_with_never_minimize():
    """Decision D6 (round 5, C3): the per-character Never-minimize checkbox
    does not render while the global minimize toggle is off, so
    previews.js appends one fewer cell per row and sets `.no-nm`.

    `.row` is display:contents, so the grid sees one flat stream of cells
    and cannot tell one row from the next: if the template and the cell
    count disagree by even one, every row after the first is pulled into
    the previous row's leftover columns. The two track counts are written
    by hand in two rules, which is the drift this asserts against -- the
    difference, not either number.
    """
    counts = []
    for selector in ("#preview-binds", r"#preview-binds\.no-nm"):
        m = re.search(selector + r" \{(.*?)\}", CSS, re.DOTALL)
        assert m, f"{selector} has no rule block"
        tracks = re.search(r"grid-template-columns:\s*repeat\((\d+),", m.group(1))
        assert tracks, f"{selector} no longer declares repeat(N, ...) tracks"
        counts.append(int(tracks.group(1)))

    full, without = counts
    assert full - without == 1, (
        f"the two #preview-binds templates differ by {full - without} tracks, "
        f"not 1 -- makeRow adds or drops exactly one cell (Never minimize) "
        f"between the two states"
    )


def _makerow_body() -> str:
    """previews.js's makeRow, comments stripped, up to its `return row`.

    Comments first: the prose around this function names the very controls
    the counts below are derived from, and a naive scan would count the
    sentences describing an append as appends.
    """
    src = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
    return src.split("function makeRow(", 1)[1].split("return row;", 1)[0]


def test_the_previews_grid_has_one_track_per_cell_makeRow_appends():
    """The invariant the delta test above cannot see.

    `.row` is display:contents, so the grid reads one flat stream of cells.
    Adding a control means editing a track count in style.css AND an append
    in previews.js -- two files -- and the delta test passes happily when
    BOTH templates are wrong by the same amount. This derives the cell
    count from makeRow itself rather than restating it.

    The label is excluded: `#preview-binds .row > .lab` is
    `grid-column: 1 / -1`, so it spans the row rather than sitting in one
    of the tracks the controls occupy. The `else` branch is excluded
    because its fillers stand in for the character branch's controls one
    for one -- counting both would double every cell.
    """
    body = _makerow_body()
    halves = body.split("} else {", 1)
    assert len(halves) == 2, "makeRow no longer has the cycle-row filler branch"
    cells = body.count("row.appendChild(") - halves[1].count("row.appendChild(") - 1

    m = re.search(r"#preview-binds \{(.*?)\}", CSS, re.DOTALL)
    assert m, "#preview-binds has no rule block"
    tracks = re.search(r"grid-template-columns:\s*repeat\((\d+),", m.group(1))
    assert tracks, "#preview-binds no longer declares repeat(N, ...) tracks"

    assert cells == int(tracks.group(1)), (
        f"makeRow appends {cells} cells per character row but #preview-binds "
        f"declares {tracks.group(1)} tracks -- every row after the first is "
        f"pulled into the previous row's leftover columns"
    )


def test_an_opted_out_character_row_disables_its_own_controls():
    """The chosen shape for a character opted out of previews: the row
    stays visible -- there has to be somewhere to turn it back on -- but
    everything else it offers is inert, because none of it can do anything
    while that character has no window, no registration and no place in
    the cycle.

    What this pins is that the controls go through WM.setEnabled against
    the row's own opted-out state, rather than merely being dimmed in CSS:
    a control that only LOOKS dead still fires on click.
    """
    body = _makerow_body()
    for control in ("button", "clear", "typed"):
        assert re.search(rf"WM\.setEnabled\({control},[^)]*\boff\b", body), (
            f"makeRow does not gate `{control}` on the row's opted-out state"
        )


def test_the_opt_out_box_itself_is_never_gated_on_being_enabled():
    """The one control that has to stay live on an opted-out row. Gating
    it with the rest would opt a character out permanently, the only way
    back being a hand-edited settings file."""
    src = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
    halves = src.split("function makeDisabledCheck(", 1)
    assert len(halves) == 2, "previews.js has no makeDisabledCheck"
    body = halves[1].split("return label;", 1)[0]
    assert "WM.setEnabled" not in body, "the opt-out box gates itself"
    assert "set_preview_disabled" in body


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
