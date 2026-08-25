"""The Skills route's page conventions, checked lexically.

Same approach and same reason as test_page_conventions.py: nothing in this
suite renders index.html or executes skills.js, so a screen that regresses
here regresses silently. These rules are narrower than that file's -- they
are about ONE route -- so they live apart from it rather than growing it.

Every rule below is a finding from docs/ui-critique.md's Skills section.
Each one shipped, and each was found by reading the source rather than by
anything failing.
"""

import pathlib
import re

WEB = pathlib.Path(__file__).resolve().parents[1] / "obs_youtube_uploader" / "web"
HTML = (WEB / "index.html").read_text(encoding="utf-8")
SKILLS = (WEB / "skills.js").read_text(encoding="utf-8")
CSS = (WEB / "style.css").read_text(encoding="utf-8")


def _strip_js_comments(text: str) -> str:
    """Line comments and top-of-file blocks. Every rule these tests pin is
    also EXPLAINED in a comment right beside it, so a naive substring
    search would pass on the explanation alone."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"(?m)^\s*//.*$", "", text)


def _strip_html_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


CODE = _strip_js_comments(SKILLS)
BODY = _strip_html_comments(HTML)
RAIL = re.search(r'<aside class="skills-rail">(.*?)</aside>', BODY, re.DOTALL).group(1)


# ---- the rail's two numbers -------------------------------------------


def test_the_plan_ratio_says_what_it_counts():
    """`3/12` in the rail counts CHARACTERS ready for the plan. `12
    requirements` in the pane header beside it counts the plan's SKILLS.
    Both were unlabelled, and on any roster whose size lands near a plan's
    length they are indistinguishable -- a first visitor reads `3/12` as
    "three of twelve requirements met", which is the opposite of what the
    number says on a screen whose whole subject is readiness.

    Two affordances, because they answer at different distances: a column
    header over the ratio for someone scanning the rail, and a title on
    each row for someone who stopped on one.
    """
    assert 'class="rail-head-key"' in RAIL, (
        "the rail's ratio column lost its header; `3/12` is unlabelled again"
    )
    ratio = re.search(r"'rail-ratio',\s*(.*?)\);", CODE, re.DOTALL)
    assert ratio, "skills.js no longer renders a .rail-ratio"
    after = CODE[ratio.end() : ratio.end() + 400]
    assert re.search(r"\.title\s*=", after), (
        "the plan row's ratio has no title spelling both numbers out"
    )


# ---- the rail's width --------------------------------------------------


def test_the_rail_is_not_sized_only_against_100_percent_scaling():
    """MIN_WIDTH is 840 PHYSICAL pixels and the app is system-DPI-aware, so
    the CSS viewport floor is 672px at 125% scaling and 560px at 150%. A
    214px rail is 38% of the window at 560, and the roster -- the thing the
    screen is for -- is the track that absorbs every pixel the rail keeps.

    The stylesheet's own comment did this arithmetic against 626px beside
    the rail, which is the 100% case and the one width where it is fine.
    """
    block = re.search(r"#route-skills\s*\{(.*?)\}", CSS, re.DOTALL)
    assert block and "214px" in block.group(1), (
        "the default rail width moved; re-check the floor arithmetic"
    )
    narrowed = re.search(
        r"@media\s*\(max-width:\s*720px\)\s*\{[^}]*#route-skills[^}]*\}", CSS
    )
    assert narrowed, (
        "#route-skills has no narrow-viewport rail width: the rail keeps "
        "214px of a 560px window at 150% scaling"
    )


def test_the_plan_file_actions_do_not_set_the_rails_width_floor():
    """A full-width `.btn` makes its own label part of the rail's minimum
    width, and `Open plans folder` was one of the two longest labels on the
    screen -- `.skills-rail button.btn { width: 100% }`. As `.linkbtn` they
    cost the rail nothing, which is what lets it narrow at all.

    They also sit with the plan list now rather than in a third block below
    it: the list was the only thing on the rail anyone comes to change, and
    it was between two blocks of setup.
    """
    for ident in ("skills-open-folder", "skills-reload-plans"):
        tag = re.search(r'<button[^>]*id="' + ident + r'"[^>]*>', RAIL)
        assert tag, f"{ident} left the rail"
        assert 'class="linkbtn"' in tag.group(0), (
            f"{ident} is a full-width button again, so its label is back in "
            "the rail's width floor"
        )
    # RAIL is the <aside>'s contents, and the plans block is its last
    # child, so "inside the plans block" is "after that block opens".
    opens = RAIL.find('<div class="rail-block rail-plans-block">')
    assert opens != -1, "the plans block left the rail"
    assert "skills-open-folder" in RAIL[opens:], (
        "the plan-file actions are no longer inside the plans block"
    )


# ---- the words ---------------------------------------------------------


def test_the_unscored_group_does_not_name_one_cause():
    """An empty or broken plans folder makes EVERY character Unscored --
    skills.js says so itself in the lockout-guard comment. `Not yet
    refreshed` named the other cause, so on the most common path into this
    group the heading was false AND pointed at the Refresh button instead
    of at the plans folder. The roster's own hint already says "No local
    plans yet" two lines above it.
    """
    label = re.search(r"Unscored:\s*'([^']*)'", CODE)
    assert label, "the Unscored group lost its label"
    assert "refresh" not in label.group(1).lower(), (
        "the Unscored heading names refreshing as the cause again: " + label.group(1)
    )


def test_the_empty_roster_names_the_control_not_its_location():
    """PRODUCT.md: "Name things the way the user does." The button says
    `Add character`; the empty state said "Add one from the actions on the
    left", which names a location -- and on the narrowest window the rail
    is the part most likely to be scanned past.
    """
    empty = re.search(r"No characters yet\.(.*?)';", CODE, re.DOTALL)
    assert empty, "the empty-roster sentence moved or changed shape"
    assert "Add character" in empty.group(1), (
        "the empty roster does not name the Add character control: " + empty.group(1)
    )


def test_the_plan_file_format_is_stated_before_the_folder_is_empty():
    """The one sentence saying a plan is a .txt file of skill names and
    levels fired only from `!plans().length` -- shown to users who have no
    plans, and so no reason to care yet. A user with one plan and a wish
    for a second had `Open plans folder` and no statement of what to put in
    it. PRODUCT.md: assume fluency in EVE, explain Wingman, and the plan
    file format is Wingman's.
    """
    about = re.search(r'<details class="rail-about">(.*?)</details>', RAIL, re.DOTALL)
    assert about, "the rail no longer states the plan file format at all"
    text = about.group(1)
    assert ".txt" in text and "roman numerals" in text, (
        "the format statement no longer says what a plan file contains"
    )
