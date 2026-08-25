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
COLUMNS = ["c-check", "c-name", "c-date", "c-size", "c-len", "c-link"]


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


def _px(value):
    return int(value.rstrip("px"))


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


def test_the_widest_layout_needs_exactly_the_measured_window_floor():
    """MIN_WIDTH was MEASURED -- ui/window.py calls it "read off the real
    page at 840x625, approached from both directions" and says it could
    not be computed on paper. It can be, and this is the sum: the six
    column tracks, the row padding, the pane's borders and scrollbar, the
    route's padding and gap, and the panel.

    The two agreeing is what makes the rest of this file trustworthy. If
    they ever disagree, either a column changed without the floor moving
    or the floor moved without the columns -- and the first of those is
    invisible in a pane that clips.
    """
    min_width = int(re.search(r"(?m)^MIN_WIDTH = (\d+)", WINDOW_PY).group(1))
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


def test_the_combat_log_box_is_gated_on_a_stored_webhook():
    """Ticked in markup with nothing gating it, this promised a Discord
    post that a fresh install cannot make. The gate is a read of the
    settings payload panel.js already receives; without it the box, the
    confirm dialog and the post itself disagree three ways."""
    assert 'id="f-logs" checked' in HTML, "the box should still default ticked"
    assert 'id="logs-hint"' in HTML
    assert "discord_webhook" in PANEL_JS
    assert re.search(r"\.disabled\s*=\s*!configured", PANEL_JS)


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
