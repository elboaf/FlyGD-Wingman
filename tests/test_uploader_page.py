"""The Uploader screen (#route-main), checked lexically.

Nothing in this suite renders the page -- the same constraint
test_page_conventions.py and test_bridge_contract.py are written under --
so what is checked here is the source, and what is checked is the set of
facts that are written down in more than one place and would therefore
drift.

The arithmetic is the reason this file exists. The list grid loses
columns off the right-hand edge of a pane whose `overflow` is `hidden`,
so getting it wrong is invisible: no scrollbar appears, nothing is
logged, and the columns are simply not there. It stayed wrong through a
whole release because the smoke item that guards it measures 840 LOGICAL
pixels, which at 100% scaling is the one width where the layout is fine.

So the breakpoints are derived here from the declared column tracks, the
declared panel widths and the declared paddings, rather than trusted.
A column track that changes without its breakpoint moving fails this
file, which is the only thing that would notice.
"""

import itertools
import pathlib
import re

from obs_youtube_uploader import library
from obs_youtube_uploader.ui import copy as copy_mod

WEB = pathlib.Path(__file__).resolve().parents[1] / "obs_youtube_uploader" / "web"
UI = pathlib.Path(__file__).resolve().parents[1] / "obs_youtube_uploader" / "ui"

CSS_RAW = (WEB / "style.css").read_text(encoding="utf-8")
HTML = (WEB / "index.html").read_text(encoding="utf-8")
LIST_JS = (WEB / "list.js").read_text(encoding="utf-8")
PANEL_JS = (WEB / "panel.js").read_text(encoding="utf-8")
API_PY = (UI / "api.py").read_text(encoding="utf-8")
WINDOW_PY = (UI / "window.py").read_text(encoding="utf-8")

# Comments carry example numbers and whole worked sums; a naive parse
# would read them as declarations. Stripped for the same reason
# test_page_conventions.py strips them.
CSS = re.sub(r"/\*.*?\*/", "", CSS_RAW, flags=re.DOTALL)

# Column order, as index.html's header spans declare it and list.js's
# rowNode() builds it. The grid template is shared by both, so a track
# count that disagrees with this wraps every row onto a second line.
COLUMNS = ["c-check", "c-name", "c-size", "c-len", "c-link"]


def _media_blocks():
    """(max_width, block) for each max-width media query, plus the base.

    Returns the base stylesheet with the media blocks removed, and the
    blocks in the order they appear -- which for a cascade is the order
    they take effect in.
    """
    blocks = []
    base = []
    i = 0
    while i < len(CSS):
        m = re.compile(r"@media\s*\(max-width:\s*(\d+)px\)\s*\{").search(CSS, i)
        if not m:
            base.append(CSS[i:])
            break
        base.append(CSS[i : m.start()])
        depth = 1
        j = m.end()
        while depth:
            if CSS[j] == "{":
                depth += 1
            elif CSS[j] == "}":
                depth -= 1
            j += 1
        blocks.append((int(m.group(1)), CSS[m.end() : j - 1]))
        i = j
    return "".join(base), blocks


BASE_CSS, MEDIA = _media_blocks()


def _decl(block, selector, prop):
    """The last value of `prop` in the rule for exactly `selector`."""
    found = None
    for rule in re.finditer(r"([^{}]+)\{([^{}]*)\}", block):
        parts = [p.strip() for p in rule.group(1).split(",")]
        if selector not in parts:
            continue
        # Not line-anchored: most rules in this stylesheet pack several
        # declarations onto one line. The boundaries keep `gap` off
        # `row-gap` and `border` off `border-radius`.
        m = re.search(rf"(?<![-\w]){prop}(?![-\w])\s*:\s*([^;}}]+)", rule.group(2))
        if m:
            found = m.group(1).strip()
    return found


def _tracks(template):
    """The grid tracks, splitting on top-level whitespace so minmax()
    survives."""
    out, depth, cur = [], 0, ""
    for ch in template:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch.isspace() and depth == 0:
            if cur:
                out.append(cur)
            cur = ""
        else:
            cur += ch
    if cur:
        out.append(cur)
    return out


def _floor(track, name_floor):
    """The width a track cannot go below, in px.

    A narrow tier declares the filename as minmax(0, 52ch) so it shrinks
    instead of overflowing. That makes its DECLARED minimum useless for
    working out where the tier stops being comfortable, so the filename is
    measured against the floor the base template declares for it -- which
    is the number the breakpoints are actually placed on.
    """
    if track.startswith("minmax("):
        inner = track[len("minmax(") : -1].split(",")[0].strip()
        return name_floor if inner == "0" else int(inner.rstrip("px"))
    return int(track.rstrip("px"))


# Custom properties resolved rather than re-declared: round 3 moved the
# scrollbar width and .grid-row's padding into :root tokens, because three
# rules have to agree on them (the scrollbar itself, .list-scroll's reserved
# gutter and .list-head's matching padding) and a literal in any one of them
# is how the header stops lining up with its data. This file's whole point
# is deriving the geometry from the sheet, so it follows them there instead
# of pinning a second copy of the number.
_ROOT_VARS = dict(
    re.findall(
        r"(--[\w-]+)\s*:\s*([^;]+);",
        re.search(r":root\s*\{(.*?)\}", BASE_CSS, re.DOTALL).group(1),
    )
)


def _resolve(value):
    """Substitute every var(--x) in a declaration with its :root value."""
    seen = 0
    while "var(" in value and seen < 10:
        value = re.sub(
            r"var\((--[\w-]+)\)",
            lambda m: _ROOT_VARS[m.group(1)].strip(),
            value,
        )
        seen += 1
    return value


def _px(value):
    return int(_resolve(value).strip().rstrip("px"))


def _int_in(text):
    return int(re.search(r"(\d+)", text).group(1))


# ---- the geometry every breakpoint is derived from --------------------

ROUTE_PAD = _px(_decl(BASE_CSS, "#route-main", "padding"))
ROUTE_GAP = _px(_decl(BASE_CSS, "#route-main", "gap"))
GRID_PAD = _px(_decl(BASE_CSS, ".grid-row", "padding").split()[1])
SCROLLBAR = _px(_decl(BASE_CSS, "::-webkit-scrollbar", "width"))
PANE_BORDER = _int_in(_decl(BASE_CSS, ".list-pane", "border"))

BASE_TEMPLATE = _decl(BASE_CSS, ".grid-row", "grid-template-columns")
BASE_PANEL = _px(_decl(BASE_CSS, ".panel", "width"))
NAME_FLOOR = _floor(_tracks(BASE_TEMPLATE)[1], 0)

# The route spends this on itself before either pane gets a pixel.
ROUTE_OVERHEAD = ROUTE_PAD * 2 + ROUTE_GAP
# And the pane spends this before a single column renders.
PANE_OVERHEAD = PANE_BORDER * 2 + SCROLLBAR + GRID_PAD * 2


def _viewport_needed(template, panel):
    tracks = _tracks(template)
    return (
        sum(_floor(t, NAME_FLOOR) for t in tracks)
        + PANE_OVERHEAD
        + ROUTE_OVERHEAD
        + panel
    )


def _tiers():
    """Each tier as it actually cascades: (applies_at_or_below, template,
    panel, hidden columns). The base tier comes first with no ceiling.

    Only blocks that touch THIS screen's geometry count. style.css holds
    breakpoints belonging to other screens -- lane 0's .settings row
    collapse and the status strip's .evestat both sit at 720px -- and the
    five screen lanes are free to add more. A sweep of every max-width
    query in the file would read those as Uploader tiers and fail on
    someone else's work.
    """
    template, panel, hidden = BASE_TEMPLATE, BASE_PANEL, set()
    tiers = [(None, template, panel, set(hidden))]
    for ceiling, block in MEDIA:
        t = _decl(block, ".grid-row", "grid-template-columns")
        p = _decl(block, ".panel", "width")
        dropped = set()
        for rule in re.finditer(r"([^{}]+)\{([^{}]*)\}", block):
            if not re.search(r"(?m)^\s*display\s*:\s*none", rule.group(2)):
                continue
            for col in COLUMNS:
                if f".{col}" in rule.group(1):
                    dropped.add(col)
        if not (t or p or dropped):
            continue
        if t:
            template = t
        if p:
            panel = _px(p)
        hidden |= dropped
        tiers.append((ceiling, template, panel, set(hidden)))
    return tiers


# ---- the parse itself, so nothing below passes vacuously --------------


def test_the_stylesheet_parse_found_the_uploader_geometry():
    """Every assertion in this file is computed from these. A regex that
    quietly matched nothing would make the rest of the file pass while
    checking air."""
    assert ROUTE_PAD == 12 and ROUTE_GAP == 12
    assert GRID_PAD == 10 and SCROLLBAR == 10 and PANE_BORDER == 1
    assert BASE_PANEL > 0 and NAME_FLOOR > 0
    assert len(_tracks(BASE_TEMPLATE)) == len(COLUMNS)
    # The Uploader's own tiers, not the ones lane 0 added for .settings.
    assert len([t for t in _tiers() if t[0]]) >= 2


def test_the_layout_that_renders_at_the_floor_needs_exactly_the_floor():
    """MIN_WIDTH was MEASURED -- ui/window.py calls it "read off the real
    page at 840x625, approached from both directions" and says it could
    not be computed on paper. It can be, and this is the sum: one tier's
    column tracks, the row padding, the pane's borders and scrollbar, the
    route's padding and gap, and the panel.

    The two agreeing is what makes the rest of this file trustworthy. If
    they ever disagree, either a column changed without the floor moving
    or the floor moved without the columns -- and the first of those is
    invisible in a pane that clips.

    The tier that holds the agreement moved in round 2, and the move IS
    Uploader 11. It used to be the six-column base, on a 120px name floor
    -- a number that measured nothing the column had to hold. So six
    columns rendered at the floor with the filename cut to
    "Fight 2026-08-24 17-57-…", losing the seconds that tell one row from
    another, while Modified sat intact beside it carrying the same
    timestamp; and the two tiers that would have dropped Modified sat at
    767px and 607px, under a floor the window can never reach.

    Widening the name track to what a filename actually needs (205px
    measured, 212px afforded) moves the agreement one tier down. The
    layout that renders AT the floor is now the five-column one, and it is
    the one that has to come out at MIN_WIDTH exactly.
    """
    min_width = int(re.search(r"(?m)^MIN_WIDTH = (\d+)", WINDOW_PY).group(1))
    at_floor = [
        (template, panel)
        for ceiling, template, panel, _ in _tiers()
        if ceiling is None or ceiling >= min_width
    ][-1]
    assert _viewport_needed(*at_floor) == min_width
    # And it is the BASE layout that lands there, not a tier stepping down
    # to it. Round 3's finding 8 dropped Modified at every width, which
    # removed the six-column layout that used to sit above this one -- so
    # the widest thing the screen can render is also the thing that has to
    # fit at MIN_WIDTH, and no width-driven column drop happens above the
    # floor at all. If a wider tier is ever reintroduced, this is the
    # assertion that has to be reconsidered rather than deleted.
    assert at_floor == (BASE_TEMPLATE, BASE_PANEL)
    assert _viewport_needed(BASE_TEMPLATE, BASE_PANEL) == min_width


def test_every_breakpoint_sits_where_the_filename_would_be_squeezed():
    """Each tier hands the next one down a layout that still gives the
    filename its declared floor. The breakpoint therefore belongs one
    pixel below the width the tier above it needs -- any higher and a
    tier fires while the wider layout still fit, any lower and there is a
    band of widths where the columns are silently cut off again."""
    for (_, template, panel, _), (ceiling, _, _, _) in itertools.pairwise(_tiers()):
        assert ceiling == _viewport_needed(template, panel) - 1, (
            f"a tier capped at {ceiling}px follows a layout that needs "
            f"{_viewport_needed(template, panel)}px"
        )


def test_the_last_tier_can_never_overflow_the_pane():
    """Below the last breakpoint -- 175% and 200% scaling put the viewport
    at 480 and 420 CSS px -- there is no tier left to shed anything, so
    the filename must be able to shrink past its floor instead.
    .list-scroll's overflow-x is hidden, so a track that cannot shrink
    does not scroll, it disappears.

    Only the LAST tier is held to this. The ones above it still have room
    for the filename's full floor, which is the whole reason they are
    separate tiers.
    """
    ceiling, template, _, _ = _tiers()[-1]
    name = _tracks(template)[1]
    assert name.startswith("minmax(0,"), (
        f"the last tier, capped at {ceiling}px, declares the filename as "
        f"{name!r}, which cannot shrink below its floor"
    )


def test_no_tier_declares_more_tracks_than_it_shows_columns():
    """The header and every row share one grid template. A tier that
    hides a cell without dropping its track leaves an empty column; one
    that drops a track without hiding the cell wraps the surplus cells
    onto a second row, in the header and in every row at once."""
    for ceiling, template, _, hidden in _tiers():
        assert len(_tracks(template)) == len(COLUMNS) - len(hidden), (
            f"the tier capped at {ceiling}px declares "
            f"{len(_tracks(template))} tracks but hides {sorted(hidden)}"
        )


def test_hidden_columns_outrank_the_header_rule():
    """`.list-head > span` is (0,1,1). A bare `.c-size` is (0,1,0) and
    loses to it, so the body cell would go while the HEADER cell stayed --
    the header/row disagreement the shared template exists to prevent,
    showing up as every column under the wrong heading."""
    for ceiling, block in MEDIA:
        for rule in re.finditer(r"([^{}]+)\{([^{}]*)\}", block):
            if not re.search(r"(?m)^\s*display\s*:\s*none", rule.group(2)):
                continue
            for part in rule.group(1).split(","):
                part = part.strip()
                if any(f".{c}" in part for c in COLUMNS):
                    assert part.startswith(".grid-row >"), (
                        f"the tier capped at {ceiling}px hides a column with "
                        f"{part!r}, which does not outrank .list-head > span"
                    )


# ---- the findings that hang on a single line --------------------------


def test_retry_is_hidden_while_it_is_disabled():
    """Retry is enabled only after an upload has failed in this session,
    so its resting state was a dead control beside the only button on the
    screen that deletes files. Nothing in panel.js hides it -- the whole
    of the fix is this one rule reading the `disabled` onRetryAvailable
    already sets, so if it goes, the dead half comes back silently."""
    assert re.search(r"#btn-retry\[disabled\]\s*\{[^}]*display:\s*none", CSS)


def test_the_combat_log_control_is_gone_and_its_sentence_is_not():
    """Uploader 8. The checkbox had no true second state -- "there is no
    scenario where I don't want to upload logs also" -- so logs became
    unconditional and the control went. The SENTENCE had to outlive it:
    with no checkbox and no panel note, a webhook-less install gets no
    statement of the fact anywhere, because Api._post_combat_logs is
    deliberately silent in exactly that case (a strip per upload, forever,
    is the recurring-failure pattern it exists to avoid).

    So the two halves are asserted together. If the note goes, the silence
    downstream becomes a feature that fails without saying so."""
    assert 'id="f-logs"' not in HTML, "the checkbox should be gone"
    assert "start_upload" not in HTML
    assert 'id="logs-note"' in HTML, "the fact still needs a home"
    assert "discord_webhook" in PANEL_JS
    # Read off the payload, not typed into the page: S3 put the app's one
    # voice for an unmet precondition in copy.py so two screens cannot
    # drift. A literal here would be the third copy.
    assert "no_webhook" in PANEL_JS
    assert "no_webhook" in copy_mod.INERT_NOTES


def test_start_upload_is_called_with_what_it_now_accepts():
    """The signature lost its `logs` parameter in the same commit that
    removed the control. Nothing executes this page, so a five-argument
    call against a four-argument method fails at a user's click and
    nowhere else -- this is the only thing that reads both sides."""
    call = re.search(r"WM\.send\('start_upload',(.*?)\);", PANEL_JS, re.DOTALL)
    assert call, "panel.js should still start uploads"
    # title, description, stitch, ids
    assert call.group(1).count(",") == 3

    signature = re.search(r"def start_upload\(self,([^)]*)\)", API_PY)
    assert signature
    params = [p.strip() for p in signature.group(1).split(",") if p.strip()]
    assert params == ["title", "description", "stitch", "ids"]


def test_the_empty_state_names_the_folder_it_watched():
    """The old empty state named neither the folder nor a way to change
    it, on the screen a first-run user reaches straight after nominating
    one. The path comes off the settings payload, so this breaks silently
    if that read goes."""
    assert "recording_dir" in LIST_JS
    assert re.search(r"WM\.make\('span', 'path'", LIST_JS)
    assert "#list-empty .path" in CSS_RAW


def test_the_folder_this_screen_is_about_can_be_opened_from_it():
    """Both existing file affordances act on the YouTube link rather than
    the file. The button, its handler and the bridge method are three
    files that have to agree, and WM.send fails a wrong name to the
    console rather than raising."""
    assert 'id="btn-open-folder"' in HTML
    assert "WM.send('open_recording_dir')" in LIST_JS
    assert "def open_recording_dir(self)" in API_PY


# --- round 2: the panel the maintainer actually uses ------------------------


def test_the_named_folder_is_re_read_when_the_list_is_empty():
    """Uploader 12: "No recordings in D:\\Videos", where D:\\Videos was the
    folder that DID have the recordings.

    S3 confirmed the cause in Api.set_folder -- it persists, rebinds the
    watcher and calls list_rows, but never re-delivers the settings
    payload, so list.js's cached recordingDir keeps naming the previous
    folder while the scan is of the new one. The fix is on the page: read
    it again.

    Deliberately NOT by re-dispatching wm:settings. That event repaints
    every field on the Settings route and list_rows fires on every watcher
    poll, so riding it would rewrite a folder path the user was mid-way
    through typing, several times a minute -- the trap DESIGN.md records
    under "an endpoint whose effect reaches outside its own control".
    """
    assert re.search(r"WM\.send\('get_settings'\)", LIST_JS)
    # Read for its own value only. Listening to wm:settings is fine and
    # predates this; RE-DISPATCHING it from a rows push is the trap.
    assert "dispatchEvent(new CustomEvent('wm:settings'" not in LIST_JS
    assert "window.onSettings" not in LIST_JS
    # And it has to be reached from the rows push, not only at startup.
    assert "refreshRecordingDir()" in LIST_JS.split("WM.handle('onRows'")[1]


def test_the_panel_says_when_there_is_nothing_to_act_on():
    """Uploader 13. With zero recordings the right column was unchanged --
    live Title, live Description, full-strength accent Upload -- so the
    empty and full states read as the same product in the wrong
    direction. Combined with Uploader 1 the accent button was inoperable
    in two different states and dressed identically in both."""
    assert 'id="panel-empty-note"' in HTML
    assert "rowCount()" in PANEL_JS
    assert re.search(r"panel-empty-note'\)\.hidden", PANEL_JS)


def test_upload_goes_inert_without_a_selection():
    """Uploader 1 and X1. The loudest element on the screen was the one
    that could not act; the state blocking it was dim body text at the
    foot of the card ABOVE it, 200px away.

    Through S1's WM.setEnabled rather than a fourth hand-rolled variant.
    The style was never the problem -- button.btn.acc:disabled has always
    worked -- so nothing here may restyle it."""
    assert re.search(r"WM\.setEnabled\('btn-upload', selected > 0\)", PANEL_JS)
    # The blocker moved next to the button, which is the other half of the
    # finding: the summary is now the line directly above the action.
    panel_card = HTML[HTML.index('id="route-main"') : HTML.index('id="ctxmenu"')]
    assert panel_card.index('id="selection-summary"') < panel_card.index(
        'id="btn-upload"'
    )


def test_stitch_is_inert_rather_than_absent_below_two_selected():
    """Uploader 17 proposed revealing Stitch only above one selection, and
    that was declined: a control appearing and disappearing under the
    pointer is a new hazard on the one screen with a recorded mis-click,
    and the height it would have saved is paid for by the card merge and
    the Delete move instead. Disabled says the same thing and stays put.

    The two-line hint that used to sit under it is a separate question and
    a separate answer: round 3's finding 3 deleted it, because it stated
    the mechanism ("select two or more...") in the approach corridor to the
    primary button, where with 0 or 1 selected it merely named the
    precondition the greyed-out label already shows, and with 2 or more it
    was redundant. The CONTROL stays put; the sentence beside it goes."""
    assert re.search(r"WM\.setEnabled\('f-stitch', selected > 1\)", PANEL_JS)
    assert 'id="stitch-hint"' not in HTML, (
        "the stitch hint was deleted in round 3 (finding 3); a new one "
        "needs its own reasoning, not this one's"
    )
    assert "stitch-hint" not in PANEL_JS
    # A box left ticked while inert would still be read at send time.
    assert re.search(r"selected < 2\) WM\.el\('f-stitch'\)\.checked = false", PANEL_JS)


def test_the_upload_button_is_in_the_card_that_names_the_upload():
    """Uploader 2. Two cards, UPLOAD and PUBLISH: one concept under two
    names on one screen, with the Upload button in the one not called
    Upload. The route is also named Uploader, and DESIGN.md forbids a
    screen repeating its own tab name as its first card heading."""
    route = HTML[HTML.index('id="route-main"') : HTML.index('id="ctxmenu"')]
    headings = re.findall(r"<h2>(.*?)</h2>", route)
    assert len(headings) == 1, f"the panel should be one card, got {headings}"
    assert headings[0].strip().lower() != "upload", "must not echo the tab name"
    assert route.index("<h2>") < route.index('id="btn-upload"')


def test_deleting_files_lives_with_the_files():
    """Uploader 2's third seam: a local file deletion filed under a card
    headed PUBLISH, beside the button that sends them to YouTube. It acts
    on the same selection as Select all / Select none and on the files the
    list is showing, so it belongs in the footer and list.js owns it."""
    route = HTML[HTML.index('id="route-main"') : HTML.index('id="ctxmenu"')]
    foot = route[route.index('class="list-foot"') : route.index('id="panel-slot"')]
    assert 'id="btn-delete"' in foot
    assert "WM.send('delete_selected'" in LIST_JS
    assert "WM.send('delete_selected'" not in PANEL_JS


def test_the_sort_arrow_has_a_reserved_slot_on_every_header():
    """Uploader 3, re-measured. The walkthrough reported headers ~16px
    right of their data on every column and blamed the scroll gutter; in
    the harness, unsorted headers agree with their columns to within the
    2px of .list-row's own transparent left border, and the gutter cannot
    move a left-packed track anyway.

    What moves is this arrow: on a flex-end header it takes the right end
    of the column and pushes the label off it, measured at 14px the moment
    that column is sorted. Reserving the width unconditionally is the fix,
    so the header stops moving when the sort changes."""
    assert re.search(r"\.list-head > span::after\s*\{[^}]*visibility:\s*hidden", CSS), (
        "every header needs the slot, not just the sorted one"
    )
    assert re.search(
        r"\.list-head > span\.sorted::after\s*\{[^}]*visibility:\s*visible", CSS
    )
    # The two centred headers need it mirrored or reserving it decentres
    # them by half its own box.
    assert re.search(r"\.c-check::before,\s*\.list-head > span\.c-link::before", CSS)


def test_the_empty_pane_is_centred_rather_than_half_centred():
    """Uploader 14. The message was centred horizontally and top-aligned
    vertically, leaving ~750px of empty pane under it. First run proves the
    app can centre a card, so this was an omission and not a limit."""
    assert re.search(
        r"\.list-scroll:has\(> #list-empty:not\(\[hidden\]\)\)\s*\{[^}]*"
        r"align-items:\s*center",
        CSS,
    )
    # Sets a display, so it needs its own [hidden] override or 25 rows draw
    # underneath a centred sentence (DESIGN.md).
    assert re.search(r"#list-empty\[hidden\]\s*\{\s*display:\s*none", CSS)


def test_a_card_heading_no_longer_claims_the_brand_accent():
    """Uploader 16, settled by S1 and written into DESIGN.md: "Accent marks
    what is selected and what will happen. A card heading is neither." The
    Uploader spent the brand five times -- the checked row's checkbox and
    its left-edge marker, the Upload button, and two card heading bars --
    diluting the signal for the three uses that carry meaning.

    The rule is about .card > h2 generally, so the edit is in the shared
    primitive and reaches every screen.

    ROUND 4: three became two. S1's direction was right and stopped one
    step early -- it counted brand uses ACROSS the screen and did not ask
    what a single row spends. A selected row carried a brand-filled 15px
    checkbox at its left edge, a lifted surface, AND a 2px brand rule
    outside both. The rule was the third signal for one state and the
    weakest of the three; a 2px edge cannot out-say a filled checkbox 30px
    to its right. It is gone, and so is the Upload button's 14px purple
    glow -- the fill was already the only brand-filled surface on that
    screen, so the halo emphasised the element needing it least.

    What must NOT follow is the 2px border itself: .list-head's alignment
    arithmetic is built on .list-row's transparent left border, so the
    width stays whatever the colour does. That is asserted here too, or a
    future tidy-up takes it and moves every Filename cell 2px left."""
    heading_bar = re.search(r"\.card > h2::before\s*\{([^}]*)\}", CSS)
    assert heading_bar, "the heading rule should still exist"
    assert "--brand" not in heading_bar.group(1)
    # Still spent where it means something: the checkbox and the one
    # primary action. Both are FILLS, which is what accent is for.
    assert re.search(r"\.list-row\.sel \.box\s*\{[^}]*var\(--brand\)", CSS)
    assert re.search(r"button\.btn\.acc\s*\{[^}]*var\(--acc-fill\)", CSS)
    # And no longer spent on the row's edge.
    sel = re.search(r"\.list-row\.sel\s*\{([^}]*)\}", CSS)
    assert sel, ".list-row.sel should still exist"
    assert "border-left-color" not in sel.group(1), (
        "the selected row's brand edge marker is back; the checkbox and "
        "the lifted surface already say it"
    )
    # The WIDTH is load-bearing even though the colour is not.
    row = re.search(r"\.list-row\s*\{([^}]*)\}", CSS)
    assert row and "border-left: 2px solid transparent" in row.group(1), (
        "list-head's alignment arithmetic is built on this border; "
        "removing it shifts every Filename cell 2px"
    )


def test_modified_is_gone_at_every_width():
    """Uploader 6 and 11 as one fact, finished in round 3 (finding 8).

    The timestamp was printed twice -- in the filename and in Modified --
    and it was the wider copy that got destroyed, because the name track
    sat on a 120px floor while an OBS filename needs 205px. Round 2 widened
    the track and dropped Modified at the floor; the A/B that shipped
    reported nothing lost, because every recording OBS names embeds its own
    timestamp, so round 3 dropped it everywhere.

    Asserted as an ABSENCE across all three surfaces rather than as a
    hidden column, because that is what changed: there is no width at which
    the app renders Modified, so a tier hiding it would be a tier hiding
    something that does not exist. The column's own CSS rule went with it,
    and so did the media query whose only job was to shed it.

    What this deliberately does NOT assert: that `date` is gone from
    list.js's comparator. It is reachable only through a header that no
    longer exists, but Python still delivers rows in date order and the
    comparator's `date` branch is what defines that order, so removing it
    would change the default sort rather than retire a control.
    """
    assert "c-date" not in HTML
    assert "c-date" not in LIST_JS
    assert "c-date" not in CSS
    # Five columns everywhere, and the header agrees with the row template.
    assert len(_tracks(BASE_TEMPLATE)) == 5
    for _, template, _, _ in _tiers():
        assert len(_tracks(template)) <= 5


def _duration_regex():
    """parseDuration's own regex, read out of list.js.

    Scoped to the function body: parseSize four lines above it is also a
    `var m = /^...$/.exec(String(text` and matched first when this was
    written against the file as a whole.
    """
    source = re.search(r"/(\^.*?\$)/\.exec", _duration_body())
    assert source, "parseDuration no longer parses its cell with a regex"
    return re.compile(source.group(1))


def _duration_body():
    """parseDuration's body text, scoped so the two tests read one thing."""
    body = re.search(
        r"function parseDuration\(text\) \{(.*?)\n  \}", LIST_JS, re.DOTALL
    )
    assert body, "parseDuration is no longer where this test reads it"
    return body.group(1)


def test_the_length_sort_parses_every_string_the_duration_format_emits():
    """list.js sorts Length by parsing its own rendered cell back out.

    That coupling is the whole hazard: a format emitting a field the regex
    rejects does not raise anywhere -- parseDuration returns -1, those rows
    all compare equal at the bottom, and the column silently stops
    sorting. Nothing renders the page in this suite, so this is the only
    place it would be noticed.

    Round 3 gave library.format_duration an hours field (a two-hour
    recording used to render "127:07"), which the m:ss-only regex would
    have rejected for exactly the recordings most worth sorting.

    The regex is read out of list.js rather than restated here, and the
    expected seconds come from format_duration's own input, so this fails
    if either side moves alone.
    """
    pattern = _duration_regex()

    for seconds in (0, 5, 65, 599, 1027, 3599, 3600, 3661, 7627, 360000):
        rendered = library.format_duration(seconds)
        m = pattern.match(rendered)
        assert m, f"list.js cannot parse {rendered!r} ({seconds}s)"
        hours, minutes, secs = m.groups()
        parsed = (int(hours) * 3600 if hours else 0) + int(minutes) * 60 + int(secs)
        assert parsed == seconds, f"{rendered!r} sorts as {parsed}s, not {seconds}s"


def test_the_length_sort_weights_each_field_by_what_it_means():
    """The arithmetic, not just the regex.

    The test above transcribes parseDuration's sum into Python to check
    it, which cannot catch a bug in the JS sum itself: simplify
    `m[1] * 3600` to `m[1] * 60` -- an easy slip, since the next line
    multiplies by 60 -- and the regex is untouched, the Python side does
    its own correct arithmetic, every assertion passes, and 2:07:07 sorts
    as 527 seconds, below a nine-minute recording.

    So the multipliers are read out of the JS and checked against what
    each captured field means. Group 3 is seconds and carries none.
    """
    body = _duration_body()
    weights = {
        int(group): int(mult)
        for group, mult in re.findall(r"parseInt\(m\[(\d)\], 10\) \* (\d+)", body)
    }
    assert weights == {1: 3600, 2: 60}, (
        "group 1 is hours and group 2 is minutes; group 3 is seconds and "
        f"takes no multiplier. Found {weights}"
    )
    assert "m[3]" in body, "the seconds group is no longer summed at all"


def test_the_two_glyph_cells_still_sort_to_the_bottom():
    """The widened regex must not start accepting "…", "?" or "—" as
    measurements -- they are the absence of one, and parseDuration's -1 is
    what they have to keep falling through to."""
    pattern = _duration_regex()
    for glyph in ("…", "?", "—", "", "1:2:3:4"):
        assert not pattern.match(glyph), f"{glyph!r} is not a duration"


def test_the_header_measures_its_columns_in_the_rows_own_font():
    """Round 3, finding 1's second cause, and the subtler of the two.

    `ch` in grid-template-columns resolves against the GRID CONTAINER's own
    font, and the shared template caps the name track at 52ch. With
    font-size on .list-head itself the header computed a 52ch that was
    --fs-muted/--fs-body of the rows', so the moment the track reached that
    cap the header's columns parted company with their data -- measured at
    1280 CSS: name track 377.25 against 426.45, putting Size and Length
    51.20px out.

    Sharing one declaration is therefore NOT enough to make the header and
    the rows agree; they must also measure it in the same font. The size
    lives on the spans, which keeps the muted header text 2.2.0 chose while
    leaving the box that measures the columns in the rows' own font.
    """
    assert "ch" in BASE_TEMPLATE, (
        "if the name track stops being measured in ch, this whole invariant "
        "is moot and the test should go rather than be worked around"
    )
    assert _decl(BASE_CSS, ".list-head", "font-size") == "var(--fs-body)"
    assert _decl(BASE_CSS, ".list-head > span", "font-size") == "var(--fs-muted)"


def test_the_header_reserves_exactly_the_gutter_the_scroller_reserves():
    """Round 3, finding 1's first cause. The scrollbar is drawn inside
    .list-scroll, so an overflowing list has a content box narrower than
    .list-head, which sits outside it -- and .grid-row's name track is
    elastic (52ch is a maximum it does not reach at these widths), so it
    absorbed the difference and carried every column after it 10px left.
    Measured on merged main with the list overflowing: +10.00 on Modified,
    Size and Length at 1027, 900 and 836 CSS; 0.00 with the scrollbar
    suppressed and the same rows in place.

    Both halves are asserted because either alone re-breaks it: the gutter
    must be reserved whether or not the list overflows, and the header must
    reserve the same width as padding.
    """
    assert _decl(BASE_CSS, ".list-scroll", "scrollbar-gutter") == "stable"
    reserved = _decl(BASE_CSS, ".list-head", "padding-right")
    assert reserved == "calc(var(--row-pad) + var(--scrollbar-w))", (
        "the header's reservation must be built from the same two tokens "
        "the scrollbar and the row padding use, not from a third copy of 10"
    )
    # And the tokens really do resolve, so this is not two names agreeing
    # on nothing.
    assert _px("var(--scrollbar-w)") == SCROLLBAR == GRID_PAD


def test_stopping_an_upload_shares_the_slot_it_cannot_be_live_beside():
    """D5. Cancel and Retry are never live together -- Retry recovers from
    a failure, Cancel stops a job still running, and no state is both. The
    page enforces it by hiding each while the other shows, so an inert
    Cancel never sits beside an inert Retry describing two states the panel
    is not in."""
    actions = HTML[
        HTML.index('class="actions"') : HTML.index(
            "</div>", HTML.index('class="actions"')
        )
    ]
    assert 'id="btn-cancel"' in actions and 'id="btn-retry"' in actions
    assert "hidden" in actions[actions.index('id="btn-cancel"') :]
    assert re.search(r"onCancelAvailable", PANEL_JS)
    assert re.search(r"btn-retry'\)\.hidden = on", PANEL_JS)
