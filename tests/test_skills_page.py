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

from wingman.eveskills import evaluator

WEB = pathlib.Path(__file__).resolve().parents[1] / "wingman" / "web"
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


def test_the_rail_keeps_its_measured_width():
    """The rail is 214px at every width this window can be.

    This test used to require a SECOND rule as well -- an
    `@media (max-width: 720px)` block narrowing the rail to 168px -- and
    the reason it gave was: "MIN_WIDTH is 840 PHYSICAL pixels and the app
    is system-DPI-aware, so the CSS viewport floor is 672px at 125%
    scaling and 560px at 150%. A 214px rail is 38% of the window at 560."

    That arithmetic is wrong and the correction is now in DESIGN.md and
    PRODUCT.md: MIN_WIDTH / MIN_HEIGHT resolve in LOGICAL units, so the CSS
    viewport floor is 840x625 at EVERY display scaling -- measured 839x621
    at 200%. There is no 560px viewport, the 38% case never existed, and
    the block this test pinned could not fire at any width the window
    reaches. Both the block and the requirement are gone.

    What survives is the half that was always a real invariant: the rail's
    width is a measured number, and moving it means re-checking the roster
    against the 590px it leaves at the real floor.
    """
    block = re.search(r"#route-skills\s*\{(.*?)\}", CSS, re.DOTALL)
    assert block and "214px" in block.group(1), (
        "the default rail width moved; re-measure the roster at the 840x625 floor"
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


# ---- state that must not be retyped ------------------------------------
#
# skills.js cannot ask Python for these at runtime: the payload sends one
# character's readiness and one requirement's state at a time, never the
# orderings behind them. So the page keeps its own copies, and DESIGN.md's
# rule for a copy that cannot be derived is to assert it in a test. Both
# arrays below have been hand-kept since the route shipped.


def test_the_roster_groups_match_the_evaluator_that_produces_them():
    """`GROUPS` is `evaluator.READINESS_ORDER`, and the comment above it
    says so -- but nothing checked, and the failure is silent in the worst
    way. buildRoster() puts any readiness NOT in this array into the OTHER
    bucket, so a readiness added or renamed in Python does not break the
    page: every character carrying it quietly lands under `Unrecognised`,
    below every real group. The roster still renders, the rows are still
    there, and the only symptom is a heading nobody expects.

    The catch-all is deliberately not in the array -- skills.js appends
    OTHER separately, because a bucket for states this page has never heard
    of stops being that the moment it is listed among the known ones.
    """
    match = re.search(r"var\s+GROUPS\s*=\s*\[(.*?)\]", CODE, re.DOTALL)
    assert match, "var GROUPS = [...] not found in skills.js"
    groups = re.findall(r"'([^']+)'", match.group(1))
    assert groups == list(evaluator.READINESS_ORDER), (
        "the roster's group order no longer matches evaluator.READINESS_ORDER"
    )


def test_every_outstanding_requirement_state_has_a_rank():
    """`STATE_RANK` orders the outstanding requirements inside an expanded
    row. Its ORDER is deliberately not READINESS_ORDER -- the comment above
    it explains why, and this test does not second-guess that. What it
    checks is the key SET: every requirement state a plan can produce,
    except Active, which requirementsNode() filters out before sorting.

    A state added in Python and not here falls to stateRank()'s `9`, which
    is the right defensive answer for a state the page has never heard of
    and the wrong one for a state that simply was not added -- it sorts
    below `Queued`, at the bottom of the list, which is the last place a
    reader looks for something new.
    """
    match = re.search(r"var\s+STATE_RANK\s*=\s*\{(.*?)\}", CODE, re.DOTALL)
    assert match, "var STATE_RANK = {...} not found in skills.js"
    ranked = set(re.findall(r"(\w+)\s*:", match.group(1)))
    outstanding = {
        state for state in evaluator._CONTRIBUTION if state != evaluator.ACTIVE
    }
    assert ranked == outstanding, (
        "STATE_RANK and the evaluator's requirement states disagree: "
        f"only in skills.js {ranked - outstanding}, "
        f"only in evaluator.py {outstanding - ranked}"
    )


# ---- round 3: the numbers, the rows, and the two new controls ----------


def test_every_group_count_names_the_noun_it_counts():
    """S1. The group header names REQUIREMENTS and its number counts
    CHARACTERS: `Missing requirements 1` sat 34 CSS px above a row reading
    `Missing 2`, and a plan heading two lines up said `14 requirements` in
    the same vocabulary. Round 2's finding 2 renamed the words and the
    mismatch survived the rename, so this pins the NUMBERS -- each one
    carries the noun it counts, and the plural is derived from the count
    rather than being two hand-kept strings.
    """
    call = re.search(r"'skills-group-count',(.*?)\)\);", CODE, re.DOTALL)
    assert call, "the group head no longer renders a count"
    assert "character" in call.group(1), (
        "the group count is a bare number again; it counts characters and "
        "must say so, beside a header that names requirements"
    )


def test_no_row_restates_the_status_of_the_group_it_is_in():
    """S2. The roster groups BY STATUS, so the row's status column could not
    say anything the header above it had not already said -- each state was
    stated three times over (swatch, group name, row). What survives is only
    what varies inside one group: a Missing row's count and a Training row's
    ETA.

    Checked against GROUP_LABEL, so a group added later cannot quietly
    reintroduce the restatement: no label may appear as a return value of
    statusLine(). `Missing` is the one that would slip through -- the row
    says `2 requirements` and the header says `Missing requirements`, which
    share a word but not a statement -- so the check is on the FULL label.
    """
    body = re.search(r"function statusLine\(ch\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert body, "statusLine() is gone"
    # The RETURNED literals only. The readiness names also appear on the
    # left of every `===` in there, and a naive scan of the whole body
    # would fail on the comparisons that decide the answer.
    returned = [
        literal
        for statement in re.findall(r"return([^;]*);", body.group(1))
        for literal in re.findall(r"'([^']*)'", statement)
    ]
    assert returned, "statusLine() returns no literals at all"

    labels = re.search(r"var GROUP_LABEL = \{(.*?)\};", CODE, re.DOTALL)
    assert labels, "GROUP_LABEL is gone"
    for label in re.findall(r":\s*'([^']+)'", labels.group(1)):
        assert label not in returned, (
            f"a row restates its own group header ({label!r}); the status "
            "column may only carry what varies inside one group"
        )


def test_the_destructive_control_is_the_apps_one_destructive_treatment():
    """S3/S4. `Forget character` was red text with no button -- the fourth
    of four treatments for "this destroys something", and the only one that
    was not a control at all, in the same --err the `Missing` row about 130
    CSS px above it used for an ordinary fact.

    Treatment only: the inline two-step stays, because this row is the only
    surface in the app for forgetting or re-authenticating a character and a
    dialog would cover it.
    """
    forget = re.search(r"'([\w ]*)', 'Forget character'", CODE)
    assert forget, "the Forget control moved or was renamed"
    assert forget.group(1) == "btn danger", (
        "`Forget character` is not the shared destructive treatment: " + forget.group(1)
    )
    assert "confirming = ch.character_id" in CODE, (
        "the inline two-step is gone; R3 was to convert the treatment, not "
        "the confirmation"
    )


def test_the_page_does_not_invent_a_fetch_history_it_was_not_sent():
    """D3/S6. `fetched_label` is Python's, and the page's own
    `|| 'Never fetched'` fallback printed it for every character on every
    render after the first -- beside queue timing from the same payload,
    which is the contradiction the maintainer reported. An absent label is a
    label we do not have, not a claim about history.
    """
    assert "'Never fetched'" not in CODE, (
        "skills.js invents a fetch history again; the label is Python's, "
        "and an absent one renders nothing"
    )


def test_a_character_with_no_snapshot_says_so_and_carries_the_control():
    """S6's surviving half. `Never fetched` explained nothing and had no
    affordance beside it -- `Refresh characters` is ~700 CSS px away in the
    rail with nothing connecting them -- and PRODUCT.md obliges Wingman to
    explain itself.

    The same character is why the requirement list needed its own branch:
    evaluator.evaluate returns an EMPTY tuple before it scores anything when
    there is no snapshot, so the list printed "every requirement is trained
    and active" for a character whose skills had never been read.
    """
    note = re.search(r"function fetchedNode\(ch\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert note, "fetchedNode() is gone"
    assert "skills_refresh" in note.group(1), (
        "the never-fetched note has no affordance beside it again"
    )

    empty = re.search(r"if \(!outstanding\.length\) \{(.*?)\n    \}", CODE, re.DOTALL)
    assert empty and "Unscored" in empty.group(1), (
        "the empty requirement list congratulates a character whose skills "
        "were never read"
    )


def test_the_plan_heading_carries_a_copy_control():
    """S7, and the maintainer's own answer to "what do you end up doing
    twice": retyping a character's missing skills into EVE. They supplied
    the cheap version too -- the whole plan is enough, because the game
    drops already-trained skills on import -- so the control sits on the
    plan heading and needs no per-character diffing.

    A .btn, not a .linkbtn: nothing else on that row acts. Disabled with no
    plan selected, per the vocabulary's disabled-when-the-object-is-absent
    rule.
    """
    head = re.search(r'<header class="skills-head">(.*?)</header>', BODY, re.DOTALL)
    assert head, "the Skills pane header moved"
    tag = re.search(r'<button[^>]*id="skills-copy-plan"[^>]*>', head.group(1))
    assert tag, "the plan heading has no copy control"
    assert 'class="btn"' in tag.group(0), (
        "the copy control is not a plain .btn: " + tag.group(0)
    )
    assert "disabled" in tag.group(0), "the copy control is live with no plan selected"
    assert "navigator.clipboard.writeText" in CODE, (
        "nothing writes the plan text to the clipboard"
    )


# ---- round 5: the roster opens, and its numbers are scoped -------------

# Whitespace-collapsed: the checklist is wrapped prose, so a sentence this
# file needs to match is as likely to arrive with a newline in the middle
# of it as not.
SMOKE = re.sub(
    r"\s+",
    " ",
    (
        pathlib.Path(__file__).resolve().parents[1] / "docs" / "smoke-checklist.md"
    ).read_text(encoding="utf-8"),
)


def test_the_small_roster_expansion_is_one_shot_and_capped():
    """S1. The expanded row is the only surface in the app for forgetting a
    character or re-authenticating it, and it opened behind a chevron above
    ~900 CSS px of void. Three things have to hold together, and each of
    them silently undoes the fix on its own: there IS a cap, the cap gates
    the expansion, and the whole thing runs once rather than on every push
    (which would re-open every row the user had closed).
    """
    cap = re.search(r"var AUTO_EXPAND_MAX = (\d+);", CODE)
    assert cap, "the small-roster expansion no longer states a cap"
    assert re.search(r"chars\.length > AUTO_EXPAND_MAX", CODE), (
        "the cap is declared but nothing is gated on it"
    )
    body = re.search(r"function autoExpand\(\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert body, "autoExpand is gone"
    assert "if (autoExpanded) return;" in body.group(1), (
        "the expansion is no longer one-shot: onSkills is pushed once per "
        "character during a refresh, so this would re-open closed rows"
    )
    assert re.search(r"if \(!chars\.length\) return;", body.group(1)), (
        "the one-shot flag arms on an empty roster, which is the state the "
        "page is in before the first refresh answers"
    )
    # Stated in two places by necessity -- a smoke item cannot read a JS
    # constant -- so the pair is asserted rather than kept by hand.
    spelled = {6: ("six", "seven"), 5: ("five", "six"), 10: ("ten", "eleven")}
    below, above = spelled[int(cap.group(1))]
    assert f"With {below} or fewer characters" in SMOKE, (
        "the cap moved and docs/smoke-checklist.md still names the old one"
    )
    assert f"With {above} or more characters" in SMOKE


def test_the_disclosure_says_whether_it_is_open():
    """S1's other half: the chevron is the entire disclosure, and a glyph is
    not a name. settings.js states the same kind of thing with aria-pressed
    on its reveal toggle."""
    assert "aria-expanded" in CODE, (
        "the row's disclosure button no longer reports its own state"
    )


def test_the_roster_count_is_scoped_and_the_group_count_is_not_its_twin():
    """S3. This line and a group head both rendered the bare words
    `3 characters`, 200 CSS px apart in two panes, counting two different
    sets. The group head is scoped by the group name printed beside it; this
    one had nothing beside it. The noun stays -- every number on this screen
    carries the noun it counts -- and the scope is what was missing.
    """
    line = re.search(r"'skills-counts'\)\.textContent = (.*?);", CODE, re.DOTALL)
    assert line, "the rail's counts line is gone"
    assert "character" in line.group(1), "the roster count dropped its noun"
    assert "added" in line.group(1), (
        "the roster count is unscoped again, and reads word-for-word like a "
        "group head counting one readiness group"
    )


def test_the_plan_list_does_not_take_the_rails_slack():
    """S5. `flex: 1` on the list grew it to the full height of the rail, so
    the format disclosure and the two plan-file actions were pinned to the
    bottom of a ~620px void -- the only onboarding copy on the screen, under
    the emptiest part of it. It must still SHRINK (min-height:0 plus a
    shrink factor) or the eighth plan pushes them off the rail instead.
    """
    rule = re.search(r"\.rail-plans \{([^}]*)\}", CSS)
    assert rule, ".rail-plans lost its rule"
    body = rule.group(1)
    assert "flex: 0 1 auto" in body, (
        "the plan list takes the rail's slack again, which puts a void "
        "between the plans and everything under them"
    )
    assert "min-height: 0" in body, (
        "without this the list cannot shrink past its content and a full "
        "plan folder pushes the disclosure off the bottom of the rail"
    )


def test_the_groups_block_sits_above_the_plans_block():
    """Not decoration. `.rail-plans-block { flex: 1 }` makes Plans absorb
    every pixel of squeeze, so a Groups block BELOW it is pinned to the
    rail floor with a dead gap. Above, the rail also reads in the direction
    the scoping flows: who, then which plans they can fly."""
    assert RAIL.index("skills-groups") < RAIL.index("rail-plans-block")


def test_the_groups_list_is_scroll_capped():
    """At nine groups an uncapped list collapses the Plans list to a single
    row -- the screen's primary list, starved by a secondary one."""
    block = re.search(r"\.rail-groups\s*\{([^}]*)\}", CSS)
    assert block, "no .rail-groups rule in style.css"
    assert "overflow-y" in block.group(1)
    assert "max-height" in block.group(1)


def test_the_group_count_says_what_it_counts():
    """`4` above `1/4` counts MEMBERS above CHARACTERS READY. Every number
    on this screen carries the noun it counts, so the column is keyed."""
    assert "MEMBERS" in RAIL.upper()


def test_the_ratio_denominator_follows_the_selected_group():
    """The numerator is Python's group-scoped ready_count. A denominator
    still counting the whole roster would read `4/9` for a four-character
    crew -- two numbers about different populations in one ratio."""
    body = re.search(r"function renderPlans\(\)\s*\{(.*?)\n  \}", CODE, re.DOTALL)
    assert body, "renderPlans not found"
    assert "characters().length" not in body.group(1)
