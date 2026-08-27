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


def test_an_id_override_of_the_label_column_still_collapses_at_the_floor():
    """Two bind lists take the shared 118px label column away from their
    rows on purpose, for two different reasons: `#eve-binds` because its
    labels are long action names and it gives them a whole line instead,
    `#preview-binds` because it gives the character name a fixed 150px
    track of its own -- an inline column, not a line. Both do it with an
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
    assert calls >= 4, (
        "flagCollisions must run after a repaint, a colour change, a sound "
        f"change and an enable toggle -- found {calls} call sites"
    )

    # THE BUG THIS TEST EXISTS FOR, found in the harness rather than here:
    # a disabled Combat is absent from the colour map, but an enabled
    # Decloak on the same colour still puts that colour IN the map, so
    # Combat found a peer and warned about an alert it cannot raise. The
    # `other !== id` filter does not cover it; an enabled check does.
    assert re.search(r"row\.enabled && row\.enabled\.checked", alerts), (
        "flagCollisions must skip disabled rows when DISPLAYING, not only "
        "when grouping: a disabled event cannot collide with anything"
    )

    # The note is a warning, not an error: the config is legal, just
    # ambiguous. And it must be tagged so it can be cleared without
    # stamping on a row's own refused-write message.
    assert "dataset.collision" in alerts, (
        "collision notes must be tagged the way clearWhileOffNotes tags "
        "its own, or clearing one will clear a real error instead"
    )
    assert re.search(r"sayRow\(row, text, 'warn'\)", alerts), (
        "a colour collision is a warning, not an error"
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
    `-1` that discounted it is gone. The `else` branch is still excluded,
    because its fillers stand in for the character branch's controls one
    for one -- counting both would double every cell.
    """
    body = _makerow_body()
    halves = body.split("} else {", 1)
    assert len(halves) == 2, "makeRow no longer has the cycle-row filler branch"
    # The label is COUNTED now: it sits in track 1 rather than spanning the
    # row, so it is a cell like any other. That is the whole change, and it
    # is why the -1 that used to discount it is gone.
    cells = body.count("row.appendChild(") - halves[1].count("row.appendChild(")

    m = re.search(r"#preview-binds \{(.*?)\}", CSS, re.DOTALL)
    assert m, "#preview-binds has no rule block"
    fixed = re.search(r"grid-template-columns:\s*(\d+)px\s+repeat\((\d+),", m.group(1))
    assert fixed, (
        "#preview-binds no longer declares a fixed first track followed by "
        "repeat(N, ...) -- a max-content name column is round 3's B1 bug, "
        "where the track followed whoever was logged in"
    )
    tracks = 1 + int(fixed.group(2))

    assert cells == tracks, (
        f"makeRow appends {cells} cells per character row but #preview-binds "
        f"declares {tracks} tracks -- every row after the first is "
        f"pulled into the previous row's leftover columns"
    )


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
    fixed = re.search(r"grid-template-columns:\s*(\d+)px\s+repeat\((\d+),", m.group(1))
    assert fixed, (
        "#preview-binds no longer declares a fixed first track followed by "
        "repeat(N, ...)"
    )
    tracks = 1 + int(fixed.group(2))
    assert base == tracks, (
        f"makeHeadRow names {base} columns but #preview-binds declares "
        f"{tracks} tracks -- the headings sit over the wrong controls, and "
        f"a heading falling into a narrower shared track widens it for "
        f"every row below"
    )


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
        ("Size", "makeSizeButton"),
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
    """The name and the `offline` tag share one 150px cell, and only one of
    them can truncate gracefully.

    A character is identifiable from a prefix and the whole string is in
    the cell's `title`, so clipping the NAME costs nothing. The tag is not
    the same kind of thing: it is the encoding of the offline state, and
    `.lab.dim`'s colour only reinforces it. Lose the word and what is left
    is colour-only state, WCAG 1.4.1 -- the failure the tag was added to
    prevent.

    Putting the ellipsis on `.lab` itself clips the PAIR, so a long enough
    name takes the tag with it. Measured in the harness at the 840x625
    floor before this split: a 14-character name left the tag 19.6px of
    headroom, a 37-character one pushed its right edge to 500.41 against a
    track ending at 359 -- the word gone entirely, with no width at which
    the reader is told.

    So the cell is a flex row: the name yields (`min-width: 0` plus the
    ellipsis) and the tag reserves its width (`flex: none`). Offline rows
    pay about 44px of name width for it and online rows pay nothing, since
    the tag only exists when `online === false`.

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
        "#preview-binds's label cell is no longer a flex row, so the tag "
        "cannot reserve its width against the name"
    )
    assert "text-overflow" not in lab, (
        "#preview-binds's label cell ellipsizes as a whole again, which "
        "clips the `offline` tag along with the name it qualifies"
    )

    name = re.search(
        r"#preview-binds \.row > \.lab > \.lab-name \{(.*?)\}", CSS, re.DOTALL
    )
    assert name, "the previews name span has no rule of its own to ellipsize in"
    # `overflow: hidden` is in this list because `text-overflow` is INERT
    # without it -- the name would spill over the tag instead of
    # truncating, which is the same lost word by a different route.
    for prop in (
        "min-width: 0",
        "overflow: hidden",
        "text-overflow: ellipsis",
        "white-space: nowrap",
    ):
        assert prop in name.group(1), (
            f".lab-name must declare `{prop}` -- without all four the name "
            f"either refuses to shrink inside the flex row, spills over the "
            f"tag, or wraps instead of ellipsizing"
        )

    tag = re.search(
        r"#preview-binds \.row > \.lab > \.off-tag \{(.*?)\}", CSS, re.DOTALL
    )
    assert tag and "flex: none" in tag.group(1), (
        "the `offline` tag no longer reserves its width, so the flex row "
        "shrinks it away and the state goes back to being colour-only"
    )

    src = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
    body = src.split("function makeRow(", 1)[1].split("return row;", 1)[0]
    assert "'lab-name'" in body, (
        "makeRow no longer builds a .lab-name span, so the CSS above has "
        "nothing to apply to and the name is a bare text node again"
    )
    # The tag is appended to the LAB, not the row. Appending it to the row
    # would give offline rows one cell more than online ones, which the
    # cell-count guard cannot see because it counts appends lexically
    # rather than per render.
    assert "lab.appendChild(WM.make('span', 'off-tag'" in body, (
        "the offline tag is no longer appended to the label cell -- in the "
        "row it would be an extra grid cell on offline rows only"
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


def test_the_size_control_is_not_drawn_where_it_could_only_refuse():
    """Size... renders only for a character set_preview_size can succeed
    for, and a filler cell holds the column open where it cannot.

    Two halves, and both matter. The GATE is the D6 rule -- a character
    that is neither running nor already in `layouts` gets a refusal from
    the endpoint ("Start this client once, or drag its preview"), and a
    layouts entry is written on a drag or a resize, not when the client
    starts, so on a fresh install that was every offline character.

    The FILLER is the grid invariant. `.row` is display:contents, so a row
    that skipped this cell would leave its remaining controls one track to
    the left -- Lock under the Size heading, Never minimize under Lock's.
    The damage stays inside that row (every row leads with a full-width
    `.lab`, which forces a fresh grid row; measured in the header guard
    above), but controls sitting under the wrong headings is exactly the
    lie the headings were added to stop. Hence a ternary inside one
    appendChild rather than an `if` around it -- the same shape the opt-out
    box uses, and the same reason.
    """
    body = _makerow_body()
    assert re.search(r"isSizable\(character\)", body), (
        "makeRow no longer gates Size... on whether the character can be "
        "sized, so it is drawn for rows where it can only refuse"
    )
    gate = body.split("isSizable(character)", 1)[1].split(";", 1)[0]
    assert "makeSizeButton" in gate and "makeSizeFiller" in gate, (
        "the Size... gate no longer chooses between the button and a "
        "filler cell -- a missing cell puts every later control on that "
        "row under the wrong heading"
    )

    src = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
    helper = src.split("function isSizable(", 1)
    assert len(helper) == 2, "previews.js has no isSizable"
    assert "state.sizable" in helper[1].split("}", 1)[0], (
        "isSizable no longer reads the payload's own answer, so the page "
        "has its own copy of a rule that belongs to layout.deserialize"
    )


def test_clear_is_not_drawn_where_it_could_only_refuse():
    """D6's rule -- do not draw a control in a state where it can only
    refuse -- applied to the control that broke it worst. `Clear` used to
    be rendered on every row and disabled wherever there was no chord to
    clear, which on a fresh install is every row. It is a .linkbtn, so
    :disabled is opacity .45 over --text-faint: 1.94:1 against the card, a
    control nobody can read holding a grid track on thirteen rows.

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
    # The above is gated INLINE; this receives the state as an argument
    # instead, and was unguarded until a review pointed out that dropping
    # the second argument at the call site leaves the control live and
    # undimmed with the whole suite green -- which is the exact failure
    # this test's docstring claims to prevent.
    for builder in ("makeSizeButton",):
        assert re.search(rf"{builder}\(character,[^)]*\boff\b", body), (
            f"makeRow does not pass the row's opted-out state to {builder}"
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
