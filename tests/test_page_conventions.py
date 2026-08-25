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

WEB = pathlib.Path(__file__).resolve().parents[1] / "obs_youtube_uploader" / "web"
HTML = (WEB / "index.html").read_text(encoding="utf-8")
# Comments are stripped before any rule parsing below: style.css leads
# almost every rule with a block comment, and a naive selector capture
# swallows it -- which made the [hidden] check miss .evestat[hidden], a
# rule that has been there all along.
CSS = re.sub(
    r"/\*.*?\*/", "", (WEB / "style.css").read_text(encoding="utf-8"), flags=re.DOTALL
)


def _strip_html_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


def _strip_js_comments(text: str) -> str:
    """Line comments only. Every rationale comment in web/*.js is a line
    comment or a /* */ block at the top of a file; a rule quoted inside one
    must not be what fails a test whose whole point is to explain itself."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"(?m)^\s*//.*$", "", text)


# ---- native form controls ---------------------------------------------


def test_no_checkbox_or_radio_renders_as_a_native_control():
    """Nothing in style.css targets input[type=checkbox] or [type=radio].
    The dark appearance comes ENTIRELY from the .check/.radio wrappers --
    .check input is opacity:0 and the styled .box beside it is what you
    see. A bare input is therefore a white Windows widget on a dark card.

    EVE Settings shipped one per character in exactly this way, while
    bookmarks.js already carried a comment warning about it.
    """
    assert "input[type=checkbox]" not in CSS
    assert "input[type=radio]" not in CSS

    body = _strip_html_comments(HTML)
    for match in re.finditer(r'<input[^>]*type="(checkbox|radio)"[^>]*>', body):
        tag = match.group(0)
        after = body[match.end() : match.end() + 120]
        wrapper = "box" if match.group(1) == "checkbox" else "ring"
        assert f'class="{wrapper}"' in after, (
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
            wrapper = "box" if match.group(1) == "checkbox" else "ring"
            assert f"'{wrapper}'" in window or f'"{wrapper}"' in window, (
                f"{path.name}: a generated {match.group(1)} with no "
                f".{wrapper} wrapper renders as a native Windows control"
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
    grids must declare the same columns, and both must put the name on its
    own line. Both halves are read out of the stylesheet rather than
    restated here, so the test cannot disagree with the file about what the
    shared value is -- only about whether it is shared.
    """
    hosts = ("#eve-binds", "#preview-binds")

    columns = {}
    for host in hosts:
        m = re.search(re.escape(host) + r" \{(.*?)\}", CSS, re.DOTALL)
        assert m, f"{host} has no rule block at all"
        tracks = re.search(r"grid-template-columns:\s*([^;]+);", m.group(1))
        assert tracks, f"{host} declares no grid-template-columns"
        columns[host] = " ".join(tracks.group(1).split())

    assert columns["#eve-binds"] == columns["#preview-binds"], (
        "the two keybind lists declare different columns, which is round 3's "
        f"B1 exactly: {columns}"
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


def test_a_readiness_state_is_not_painted_in_the_error_colour():
    """`Missing` / `Not trained` are facts about a character, not failures.

    C2 settled this for `Unknown skill`; round 3's S3 found the same
    mistake still shipping on five rules, where --err painted a readiness
    state, a group swatch AND `Forget character` -- the control that
    deletes the character -- in one colour, about 130 CSS px apart. The
    readiness ramp now ends in --unmet and destructive controls carry
    --danger, so no one token means all three.
    """
    for cls in (
        "key-Missing",
        "key-Unknown",
        "status-Missing",
        "status-Unknown",
        "state-Missing",
        "state-Unknown",
    ):
        rule = re.search(r"\." + cls + r"\s*\{([^}]*)\}", CSS)
        assert rule, f".{cls} is gone -- did the readiness classes move?"
        assert "var(--err)" not in rule.group(1), (
            f".{cls} paints a readiness state in --err; it belongs on --unmet"
        )


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

    The second is the vocabulary itself: `red text, no button` was retired,
    and `.linkbtn.danger` is kept for exactly one site until R3 converts
    `Forget character`. A second user of it re-opens S4.
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
    # A subset rather than an equality, deliberately. skills.js is the one
    # site the treatment is tolerated at, and R3's job is to REMOVE it -- an
    # equality would go red on the lane this rule exists to enable, with a
    # message accusing it of adding a user when it deleted the last one.
    # When `users` is empty, delete the `.linkbtn.danger` pair in style.css
    # and this clause with it.
    assert users <= {"skills.js"}, (
        "`red text, no button` is not in the control vocabulary; the only "
        f"site it is tolerated at is skills.js, but found: {sorted(users)}"
    )
