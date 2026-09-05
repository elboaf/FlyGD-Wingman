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
DEV_JS = _strip_js_comments((WEB / "dev.js").read_text(encoding="utf-8"))


def _function_body(text: str, name: str) -> str:
    r"""A function's body by brace-matching rather than a first-`}` regex.

    `statusLine` and the two comparators below all nest an `if` block, so a
    naive `\{(.*?)\n  \}` stops at the FIRST closing brace, which belongs to
    the nested `if` rather than the function -- and would silently pass on
    a truncated body that happens to contain what a test is looking for.
    """
    match = re.search(r"function\s+" + re.escape(name) + r"\s*\([^)]*\)\s*\{", text)
    assert match, f"{name} function is missing"
    depth = 1
    index = match.end()
    while index < len(text) and depth:
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
        index += 1
    assert depth == 0, f"{name} function has unbalanced braces"
    return text[match.end() : index - 1]


def _dev_skills_characters():
    """Parses the skills fixture's `characters` array field-by-field.

    Not a JSON/JS parser -- this is a lexical suite and dev.js is not JSON
    (unquoted keys, single quotes, trailing commas would all break one).
    Each character object is split out by its leading `{ character_id:`,
    and every field is read independently by its own regex, so entries are
    free to carry fields in any order or omit optional ones
    (`missing_names`) without breaking the split.
    """
    match = re.search(
        r"var skills = \{.*?characters:\s*\[(.*?)\n    \],\n\s*plan_issues",
        DEV_JS,
        re.DOTALL,
    )
    assert match, "the skills fixture's characters array is missing"
    entries = re.split(r"\{ character_id:", match.group(1))[1:]

    def field(entry, name, pattern=r"'([^']*)'"):
        found = re.search(name + r":\s*" + pattern, entry)
        return found.group(1) if found else None

    parsed = []
    for entry in entries:
        seconds = field(entry, "training_remaining_seconds", r"(null|\d+)")
        queued = field(entry, "queued_count", r"(\d+)")
        missing = field(entry, "missing_count", r"(\d+)")
        parsed.append(
            {
                "name": field(entry, "character_name"),
                "readiness": field(entry, "readiness"),
                "finish": field(entry, "estimated_finish_utc") or "",
                "seconds": None if seconds in (None, "null") else int(seconds),
                "status": field(entry, "training_estimate_status"),
                "queued_count": int(queued) if queued is not None else 0,
                "missing_count": int(missing) if missing is not None else 0,
            }
        )
    return parsed


DEV_CHARACTERS = _dev_skills_characters()


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

    The route's shared workspace rule was moved to a common class
    (.eve-workspace) so both Skills and Fittings share the same sizing.
    This test checks that the shared rule still reserves a 214px rail.
    """
    block = re.search(r"(?<![\w-])\.eve-workspace\s*\{(.*?)\}", CSS, re.DOTALL)
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


def test_the_plan_file_actions_sit_directly_below_the_plan_list():
    """They act on the folder the visible list reads from, so they belong
    immediately under it -- not after \"What is a plan?\", an explanation
    almost nobody opens, and not after the block's own flexible slack
    (.rail-plans-block's comment: the slack is the block's own, at its
    foot). Reordering the two costs nothing: both `<details>` and the
    actions row are `flex: none` siblings of the same shrinkable list, so
    the block's total height, and the four-plan-row floor measured against
    it, do not move either way.
    """
    opens = RAIL.find('<div class="rail-block rail-plans-block">')
    assert opens != -1, "the plans block left the rail"
    scoped = RAIL[opens:]
    list_at = scoped.find('id="skills-plans"')
    actions_at = scoped.find('id="skills-open-folder"')
    about_at = scoped.find('<details class="rail-about">')
    assert list_at != -1 and actions_at != -1 and about_at != -1, (
        "the plan list, its actions, or its disclosure left the plans block"
    )
    assert list_at < actions_at < about_at, (
        "the plan-file actions must sit directly below the plan list and "
        "before the explanatory disclosure that used to precede them"
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


def test_skills_hands_character_management_off_to_settings():
    """Task 9: Skills no longer owns character authorization or forgetting.
    Its one rail action is a handoff to Settings > Characters, where the
    approved global Authenticate action lives.
    """
    assert 'id="skills-manage-characters"' in RAIL
    assert 'id="skills-add"' not in RAIL
    assert "Manage characters…" in RAIL
    assert "WM.openSettingsSection('characters')" in CODE
    for removed in (
        "skills_add_character",
        "skills_cancel_auth",
        "skills_forget_character",
    ):
        assert removed not in CODE


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


def test_skills_empty_and_reauth_copy_name_settings_without_row_actions():
    """The route still reports that a row needs another sign-in, but it no
    longer offers its own row buttons. Recovery and first-run copy point to
    Settings, the canonical authorization surface.
    """
    empty = re.search(r"No characters yet\.(.*?)';", CODE, re.DOTALL)
    assert empty, "the empty-roster sentence moved or changed shape"
    assert "Manage characters…" in empty.group(1)
    assert "Settings" in empty.group(1)
    assert "This character needs to sign in to EVE again." in CODE
    assert "Re-authenticate" not in CODE
    assert "Forget character" not in CODE
    assert "confirming = ch.character_id" not in CODE
    assert "STATE.auth_in_progress" not in CODE


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


def test_route_uses_shared_eve_workspace_class():
    """Both Skills and Fittings routes must use the shared .eve-workspace
    parent grid so their layout is identical and driven by a single rule.

    The assertion is class-token-aware: it accepts any ordering or extra
    class tokens as long as both `route` and `eve-workspace` are present.
    """
    match = re.search(
        r"<div[^>]*\bclass=\"(?=[^\"]*\broute\b)(?=[^\"]*\beve-workspace\b)[^\"]*\"[^>]*\bid=\"route-skills\"",
        BODY,
    )
    assert match, "route-skills does not carry both route and eve-workspace class tokens"


def test_eve_workspace_css_has_required_properties():
    """The shared .eve-workspace rule must declare the five geometry
    properties the design brief specifies.
    """
    block = re.search(r"(?<![\w-])\.eve-workspace\s*\{([^}]*)\}", CSS, re.DOTALL)
    assert block, "no .eve-workspace rule found in style.css"
    body = block.group(1)
    assert "display" in body and "none" in body, ".eve-workspace must default to display: none"
    assert "grid-template-columns" in body and "214px minmax(0, 1fr)" in body, (
        ".eve-workspace must set grid-template-columns: 214px minmax(0, 1fr)"
    )
    assert "gap" in body and "12px" in body, ".eve-workspace must set gap: 12px"
    assert "padding" in body and "12px" in body, ".eve-workspace must set padding: 12px"
    assert "min-height" in body and "0" in body, ".eve-workspace must set min-height: 0"


def test_eve_workspace_active_sets_display_grid():
    match = re.search(r"(?<![\w-])\.eve-workspace\.active\s*\{([^}]*)\}", CSS, re.DOTALL)
    assert match and "display" in match.group(1) and "grid" in match.group(1), (
        ".eve-workspace.active must set display: grid"
    )


def test_primary_action_alignment_shared_rule():
    """Both routes' primary actions must use a shared rule that centers
    them vertically and pushes them to the far edge.
    """
    rule = re.search(r"(?<![\w-])\.skills-head\s*>\s*\.workspace-primary\s*\{([^}]*)\}", CSS, re.DOTALL)
    assert rule, "no .skills-head > .workspace-primary rule found in style.css"
    body = rule.group(1)
    assert "margin-left" in body and "auto" in body, (
        ".skills-head > .workspace-primary must set margin-left: auto"
    )
    assert "align-self" in body and "center" in body, (
        ".skills-head > .workspace-primary must set align-self: center"
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
    # Require the workspace-primary token explicitly on the primary action.
    assert re.search(r'class="[^"]*\bworkspace-primary\b', tag.group(0)), (
        "the copy control must include the workspace-primary token: " + tag.group(0)
    )
    assert "disabled" in tag.group(0), "the copy control is live with no plan selected"
    assert "navigator.clipboard.writeText" in CODE, (
        "nothing writes the plan text to the clipboard"
    )


def test_copy_plan_reports_clipboard_success_and_failure_locally():
    """Copying succeeds or fails in the browser after Python returns text,
    so the Skills pane -- not the global status strip -- must report both.

    This fails if the local live region disappears, a clipboard rejection is
    ignored, or a successful write does not confirm the completed action.
    """
    status = re.search(r'<p[^>]*id="skills-copy-status"[^>]*>', BODY)
    assert status, "Copy plan has no local feedback region"
    assert 'role="status"' in status.group(0)

    handler = re.search(
        r"WM\.el\('skills-copy-plan'\)\.addEventListener\('click', function \(\) \{(.*?)\n  \}\);",
        CODE,
        re.DOTALL,
    )
    assert handler, "Copy plan no longer owns its clipboard result"
    assert "navigator.clipboard.writeText(text).then(" in handler.group(1)
    assert "Plan copied to clipboard." in handler.group(1)
    assert "Could not copy the plan to the clipboard." in handler.group(1)


def test_failed_copy_feedback_belongs_to_the_plan_that_started_the_attempt():
    """A failed plan lookup or clipboard write must not inherit ownership
    from the last successful copy. Otherwise switching plans can leave the
    failure attached to whichever plan happened to succeed previously.
    """
    handler = re.search(
        r"WM\.el\('skills-copy-plan'\)\.addEventListener\('click', function \(\) \{(.*?)\n  \}\);",
        CODE,
        re.DOTALL,
    )
    assert handler
    body = handler.group(1)
    starts_request = body.index("WM.send('skills_plan_text', name)")
    owns_attempt = body.index("resetCopyStatus(name)")
    assert owns_attempt < starts_request, (
        "every copy attempt must claim its plan before either the plan lookup "
        "or clipboard write can fail"
    )
    reset = re.search(
        r"function resetCopyStatus\(plan\) \{(.*?)\n  \}", CODE, re.DOTALL
    )
    assert reset
    assert "copyStatusPlan = plan" in reset.group(1)
    assert "setCopyStatus('', false)" in reset.group(1), (
        "attempt ownership and the old status must be reset together"
    )


def test_pending_copy_completion_is_invalidated_when_the_plan_changes():
    """A plan lookup and clipboard write are both asynchronous. Switching
    away and back must invalidate either completion rather than letting an
    old attempt report success or failure under the newly selected plan.
    """
    assert re.search(r"var copyAttemptSeq = 0;", CODE)
    handler = re.search(
        r"WM\.el\('skills-copy-plan'\)\.addEventListener\('click', function \(\) \{(.*?)\n  \}\);",
        CODE,
        re.DOTALL,
    )
    assert handler
    body = handler.group(1)
    assert "copyAttemptSeq += 1" in body
    assert "var token = copyAttemptSeq" in body
    # One guard after the bridge lookup and one in each clipboard outcome.
    assert body.count("copyAttemptIsCurrent(token, name)") >= 3

    select = re.search(r"function selectPlan\(name\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert select and "resetCopyStatus('')" in select.group(1), (
        "selection must clear feedback and invalidate pending completions immediately"
    )


def test_reloading_plans_invalidates_copy_attempts_even_when_name_survives():
    """Reload is authoritative even when its replacement keeps the same name."""
    reload_handler = re.search(
        r"WM\.el\('skills-reload-plans'\)\.addEventListener\('click', function \(\) \{(.*?)\n  \}\);",
        CODE,
        re.DOTALL,
    )
    assert reload_handler, "Reload plans handler is missing"
    body = reload_handler.group(1)
    assert "copyAttemptSeq += 1" in body, (
        "reload must invalidate a pending copy even when selection name is unchanged"
    )
    assert "resetCopyStatus('')" in body, (
        "reload must clear copy feedback with the invalidated attempt"
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


def test_the_roster_row_names_what_is_missing_from_the_same_tuple():
    """Round 6, P1-2.

    The roster said `9 requirements` beside 420 CSS px of empty pane, so
    the one screen whose job is "which of my characters can fly this" hid
    WHICH nine behind a row expand. The names now ride the roster payload.

    The count and the names must have ONE source. If a row could show `9
    requirements` over a list built from anything but the tuple that 9
    counts, the two would disagree the first time a state name changed --
    and disagree quietly, since nothing renders this page in the suite.
    """
    # Behavioural: the helper filters the SAME tuple missing_count counts.
    reqs = tuple(
        evaluator.RequirementAnalysis(
            skill_name=name,
            required_level=level,
            active_level=None,
            trained_level=None,
            state=state,
            queued_finish_utc=None,
            queue_timing_unknown=False,
        )
        for name, level, state in (
            ("Gunnery", 5, evaluator.MISSING),
            ("Drones", 4, evaluator.ACTIVE),
            ("Heavy Assault Cruisers", 5, evaluator.MISSING),
            ("Motion Prediction", 3, evaluator.MISSING),
            ("Shield Management", 2, evaluator.MISSING),
        )
    )
    analysis = evaluator.PlanAnalysis(
        readiness=evaluator.MISSING,
        estimated_finish_utc=None,
        queue_timing_unknown=False,
        requirements=reqs,
    )
    assert analysis.missing_count == 4
    # Trained requirements are skipped, roman levels, order preserved.
    assert evaluator.missing_names(analysis, 3) == (
        "Gunnery V",
        "Heavy Assault Cruisers V",
        "Motion Prediction III",
    )
    # The cap bounds the payload; it does not change the count.
    assert len(evaluator.missing_names(analysis, 3)) == 3
    assert analysis.missing_count == 4, (
        "the cap must bound the NAMES only -- the row states its remainder "
        "from the count, so a capped count would under-report"
    )

    # Lexical: the page states the remainder rather than truncating, and
    # derives it from missing_count minus what the ROW shows -- not from
    # the payload's own length. See
    # test_the_roster_row_caps_its_own_shown_names_below_the_payload for
    # why those are no longer the same length.
    assert "ch.missing_count - shown.length" in SKILLS, (
        "the remainder must be missing_count minus what the row actually "
        "shows; deriving it from the payload's length instead would make "
        "a payload-cap change silently change the stated remainder"
    )
    assert "' and ' + rest + ' more'" in SKILLS, (
        "a truncation with no stated remainder hides how much is missing"
    )

    # The cap is stated once, in Python, and is smaller than the copy
    # confirm's -- a scanned row is not a modal the reader has stopped at.
    controller = (
        pathlib.Path(__file__).resolve().parents[1]
        / "wingman"
        / "eveskills"
        / "controller.py"
    ).read_text(encoding="utf-8")
    cap = re.search(r"_ROSTER_NAME_CAP = (\d+)", controller)
    assert cap, "the roster name cap is gone"
    assert int(cap.group(1)) >= 1
    copy_py = (
        pathlib.Path(__file__).resolve().parents[1] / "wingman" / "ui" / "copy.py"
    ).read_text(encoding="utf-8")
    copy_cap = re.search(r"_COPY_NAME_CAP = (\d+)", copy_py)
    assert copy_cap and int(cap.group(1)) <= int(copy_cap.group(1)), (
        "the roster cap must not exceed the copy confirm's: a row read by "
        "scanning cannot carry more names than a modal read on purpose"
    )


def test_the_roster_row_caps_its_own_shown_names_below_the_payload():
    """Round 6 sent up to three names per row (controller._ROSTER_NAME_CAP)
    and the row printed every one it received. A collapsed roster's job is
    to be scanned across many rows, not read one at a time -- the same
    reasoning ui/copy.py's _COPY_NAME_CAP already applies to a modal read
    on purpose, and a scanned row can afford fewer names than that, not
    more. ROSTER_ROW_NAME_CAP is the page's OWN, independent cap: smaller
    than the payload's, and free to move without the payload cap moving
    with it, because the two answer different questions -- one bounds an
    evaluation cost, this one bounds a read.
    """
    cap = re.search(r"var ROSTER_ROW_NAME_CAP = (\d+);", CODE)
    assert cap, "the roster row's own name cap is gone"
    assert int(cap.group(1)) == 2

    controller = (
        pathlib.Path(__file__).resolve().parents[1]
        / "wingman"
        / "eveskills"
        / "controller.py"
    ).read_text(encoding="utf-8")
    backend_cap = re.search(r"_ROSTER_NAME_CAP = (\d+)", controller)
    assert backend_cap, "the payload's own name cap is gone"
    assert int(cap.group(1)) <= int(backend_cap.group(1)), (
        "the row must not show more names than the payload can ever carry"
    )

    row = re.search(r"function rowNode\(ch\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert row, "rowNode() is gone"
    body = row.group(1)
    assert "slice(0, ROSTER_ROW_NAME_CAP)" in body, (
        "the row no longer caps how many missing names it shows to ROSTER_ROW_NAME_CAP"
    )
    assert "missing_names.length" not in body and "names.length" not in body, (
        "the remainder must not be derived from the payload's own length "
        "again -- see the constant's comment"
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


def test_the_roster_has_its_own_persistent_heading():
    """Groups and Plans are two of the route's three independent scroll
    regions, and each already carries a persistent `.rail-head` above its
    own scrollbar. The roster -- the third -- carried none: only the
    filter bar sat above it, and Clear filter hides itself until a filter
    is typed. This reuses the exact same class rather than inventing a
    new heading treatment, so it costs no new .14em rule (see
    test_the_uppercase_tracked_labels_split_headings_from_sub_labels,
    which still expects exactly four).

    Inert text, not a control: no tabindex, no click handler, nothing
    skills.js has to wire up.
    """
    heading = re.search(
        r'<h[1-6][^>]*class="[^"]*\brail-head\b[^"]*\bskills-roster-head\b[^"]*"[^>]*>'
        r"([^<]*)</h[1-6]>",
        BODY,
    )
    assert heading, "the roster's persistent heading is gone"
    assert heading.group(0).startswith("<h2"), (
        "Characters is a section under the selected plan's h1, so it must not "
        "skip directly to h3 in the document outline"
    )
    assert heading.group(1).strip() == "Characters", (
        "the roster heading no longer names what it heads, in the same "
        "vocabulary the rest of the route already uses (Add character, "
        "Filter characters, N characters added)"
    )
    assert "tabindex" not in heading.group(0), (
        "the roster heading must stay inert text, not a new keyboard stop"
    )

    # It must sit BEFORE the roster it heads, and before the filter that
    # scopes it -- the heading marks where the plan-scoped pane header ends
    # and the character-scoped region begins.
    head_at = BODY.find(heading.group(0))
    filter_at = BODY.find('class="skills-filterbar"')
    roster_at = BODY.find('id="skills-roster"')
    assert head_at != -1 and filter_at != -1 and roster_at != -1
    assert head_at < filter_at < roster_at, (
        "the roster heading must precede both the filter bar and the roster it names"
    )

    rule = re.search(r"\.skills-roster-head\s*\{([^}]*)\}", CSS)
    assert rule, ".skills-roster-head has no rule of its own"
    assert "var(--panel-border)" in rule.group(1), (
        "the boundary must use the existing panel-border token, not a new "
        "colour or the undefined --border custom property some Profiles "
        "rules carry"
    )
    assert "var(--border)" not in rule.group(1)
    assert "letter-spacing" not in rule.group(1) and "color" not in rule.group(1), (
        "the heading treatment itself belongs to .rail-head alone; this "
        "rule may only add the boundary, not a second copy of the label "
        "styling"
    )


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


def test_the_group_control_uses_the_styled_select_vocabulary():
    """A bare <select> is a white Win32 widget on a dark card. `.field` is
    the app's existing styled vocabulary for one -- #f-privacy, #es-profile
    and #es-source all use it."""
    assert "'select', 'field'" in CODE or '"select", "field"' in CODE


def test_no_two_functions_in_skills_js_share_a_name():
    """A duplicate `function f()` in one scope silently replaces the first.

    It happened: a new group-picker helper was called `groupNode`, which is
    also the readiness-bucket renderer, and the roster broke with every test
    still green -- nothing here executes this file, so a name collision is
    invisible until someone opens the page.
    """
    names = re.findall(r"^\s*function (\w+)\s*\(", CODE, re.MULTILINE)
    duplicates = sorted({n for n in names if names.count(n) > 1})

    assert not duplicates, f"duplicate function declarations: {duplicates}"


def test_missing_plan_is_reported_only_by_python():
    """Python can diagnose a vanished plan; the page cannot add a second warning.

    The page owns clipboard outcomes after it receives text. A falsey plan-text
    result is instead Python's missing-plan warning, so rendering another local
    no-plan message duplicates feedback for one failed action.
    """
    handler = re.search(
        r"WM\.el\('skills-copy-plan'\)\.addEventListener\('click', function \(\) \{(.*?)\n  \}\);",
        CODE,
        re.DOTALL,
    )
    assert handler, "Copy plan handler is missing"
    body = handler.group(1)
    assert "if (!text) { return; }" in body
    assert "The plan is no longer available." not in body


# ---- Task 6: sorting the two live groups by training time -------------
#
# Task 5's payload carries three estimate fields per character:
# `estimated_finish_utc` (EVE's own queue fact, untouched), and
# `training_remaining_seconds` / `training_remaining_label` (the plan's
# whole remaining duration, raw and formatted). The Training group sorts
# on the first; the Missing group sorts on the second. Sorting Missing by
# `missing_count` (a count of REQUIREMENTS) answered a different question
# than the group now claims to answer (how long is left), and sorting
# Training by name told a fleet commander nothing about who finishes soonest.


def test_training_rows_sort_by_real_finish_with_unknown_last():
    """The Training group's whole reason to exist as a sort target: `soonest
    first` is the one ordering a queue timing-unknown row cannot honestly
    join, so it must be excluded from the comparison entirely rather than
    sorting as though its (missing) finish were early or late."""
    assert "function byTrainingFinishThenName" in CODE
    body = _function_body(CODE, "byTrainingFinishThenName")
    assert "estimated_finish_utc" in body
    assert "training_remaining_seconds" not in body, (
        "the Training sort must use EVE's own queue fact, not the plan's "
        "whole remaining duration"
    )


def test_missing_rows_sort_by_raw_training_seconds_with_unavailable_last():
    """The Missing group has no queue fact to sort by -- nothing is queued
    yet -- so it sorts on the plan's own remaining-duration estimate, and
    only the RAW seconds: sorting on the formatted label would sort text
    ("1d 2h" before "9h") rather than time."""
    assert "function byTrainingRemainingThenName" in CODE
    body = _function_body(CODE, "byTrainingRemainingThenName")
    assert "training_remaining_seconds" in body
    assert "training_remaining_label" not in body, (
        "the Missing sort must compare raw seconds, not the printed string"
    )


def test_missing_status_carries_unqueued_count_and_training_work():
    """S2 still holds: the row may not restate `Missing requirements`, its
    own group header. What the header cannot carry is how much is left to
    train and how long that takes -- and `unqueued` rather than `missing`
    is deliberate, because every one of these requirements is about to be
    queued, not merely absent."""
    body = _function_body(CODE, "statusLine")
    assert " unqueued" in body
    assert " training remaining" in body
    assert "training time unavailable" in body


def test_missing_status_never_folds_no_plan_into_training_time_unavailable():
    """`training_estimate_status === ""` means no plan was ever asked about
    (Task 5's ruling) -- controller._character_row cannot produce a
    `Missing` readiness without also producing one of the four real
    estimator statuses, so this never fires from Python today. It is
    guarded anyway: folding "" into the same phrase as a real failure
    would silently start being true the moment that invariant ever moved,
    with nothing here to catch it."""
    body = _function_body(CODE, "statusLine")
    assert "ch.training_estimate_status ?" in body, (
        "the unavailable phrase must be gated on a truthy status, not an "
        "unconditional else that would also fire for the empty ('no plan') "
        "status"
    )


def test_training_rows_use_the_finish_comparator_and_missing_the_remaining_one():
    """buildRoster() must not use one comparator for every group -- a
    Training row sorted by name again would silently undo this task, and a
    Ready/Locked/Unknown row sorted by training time would sort on a field
    those groups do not mean to answer with."""
    body = _function_body(CODE, "comparatorFor")
    assert "byTrainingFinishThenName" in body
    assert "byTrainingRemainingThenName" in body
    assert "byName" in body
    training_at = body.index("'Training'")
    missing_at = body.index("'Missing'")
    assert training_at < body.index("byTrainingFinishThenName"), (
        "the Training comparator is not gated on the Training group name"
    )
    assert missing_at < body.index("byTrainingRemainingThenName"), (
        "the Missing comparator is not gated on the Missing group name"
    )
    assert "comparatorFor(" in CODE and re.search(
        r"rows\.sort\(comparatorFor\(", CODE
    ), "buildRoster no longer selects a comparator per group"


# ---- Task 6: the assumptions behind every estimate ---------------------


def test_the_estimate_info_button_states_its_assumptions_accessibly():
    """Every training ETA and remaining-time figure rests on assumptions
    the payload cannot state per-row -- current attributes at Omega speed,
    with implants and any requirement not explicitly listed in the plan
    excluded from the number -- so one real, keyboard-reachable control
    states them once. A `<span>` with a `title` -- list.js's existing
    tooltip vocabulary -- cannot be reached by keyboard at all, which is
    why this is a `<button>`.

    Fix round 1: the approved copy is pinned VERBATIM, not just by keyword.
    The previous wording ("skip any requirement this build cannot look
    up") was false -- training.estimate() is all-or-nothing, so an
    unresolvable requirement suppresses the WHOLE estimate rather than
    being individually skipped -- and a keyword-only check ("requirement"
    appears in both sentences) would have passed it. The approved sentence
    instead scopes the calculation to what the PLAN explicitly lists
    (excluding implied prerequisites), which is what the estimator
    actually does.
    """
    tag = re.search(r'<button[^>]*id="skills-estimate-info"[^>]*>', BODY)
    assert tag, "the estimate info button is missing"
    markup = tag.group(0)
    assert 'type="button"' in markup, "a button with no explicit type submits a form"
    assert re.search(r"\bhidden\b", markup), (
        "the info button must start hidden -- there is no plan selected on first paint"
    )
    approved = (
        "Estimates use current attributes at Omega speed. Implants and "
        "requirements not listed in this plan are excluded."
    )
    label = re.search(r'aria-label="([^"]*)"', markup)
    assert label, "the info button has no aria-label"
    assert label.group(1) == approved, (
        "the info button's aria-label no longer matches the approved copy "
        "verbatim: " + label.group(1)
    )
    tip = re.search(r'data-tip="([^"]*)"', markup)
    assert tip, "the info button has no data-tip for a mouse user"
    assert tip.group(1) == approved, (
        "the info button's data-tip no longer matches the approved copy "
        "verbatim: " + tip.group(1)
    )
    for text in (label.group(1), tip.group(1)):
        assert "current attributes" in text
        assert "Omega" in text
        assert "Implants" in text or "implant" in text.lower()
        assert "not listed" in text, (
            "the copy must scope the exclusion to what the plan does not "
            "list, not claim to skip individual unresolvable requirements"
        )
        assert "look up" not in text.lower(), (
            "the false 'skip any requirement this build cannot look up' "
            "framing is back -- the estimator withholds the WHOLE estimate "
            "on an unresolved requirement, it does not skip just that one"
        )


def test_the_estimate_info_button_sits_between_the_count_and_copy_plan():
    """It is an attribute of the SELECTED PLAN's numbers, not a general help
    button, so it belongs beside the count those numbers describe rather
    than at either end of the header."""
    head = re.search(r'<header class="skills-head">(.*?)</header>', BODY, re.DOTALL)
    assert head, "the Skills pane header moved"
    count_at = head.group(1).index('id="skills-plan-count"')
    info_at = head.group(1).index('id="skills-estimate-info"')
    copy_at = head.group(1).index('id="skills-copy-plan"')
    assert count_at < info_at < copy_at, (
        "the info button must sit after the plan count and before Copy plan"
    )


def test_render_head_toggles_the_estimate_info_button_with_the_plan():
    body = re.search(r"function renderHead\(\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert body, "renderHead is gone"
    assert "skills-estimate-info" in body.group(1), (
        "renderHead no longer touches the info button at all"
    )
    assert re.search(r"\.hidden = !name", body.group(1)), (
        "the info button does not hide with no plan selected and reveal with one"
    )


def test_missing_status_carries_the_same_tooltip_for_mouse_discovery():
    """The button is the keyboard-reachable affordance; a Missing row's own
    status span carries the identical `data-tip` so resting a mouse on the
    number gets the same explanation without tabbing up to the header. It
    is read off the button rather than retyped, so the two copies of this
    sentence cannot drift apart."""
    assert "skills-estimate-info" in CODE
    assert "getAttribute('data-tip')" in CODE, (
        "the row's tooltip is not derived from the button's own data-tip"
    )


def test_the_tooltip_primitive_opens_on_keyboard_focus_too():
    """Native `title` does not reliably open on keyboard focus, which is
    why the info button is a real `<button>` and not a titled span -- but
    the existing `[data-tip]` primitive itself was hover-only, so it must
    be extended or a keyboard user still cannot read it."""
    assert "[data-tip]:focus-visible::after" in CSS


# ---- Fix round 1: WCAG 1.4.13 dismissal for the focus-visible tooltip --


def test_escape_suppresses_the_tooltip_without_moving_focus():
    """1.4.13 (Content on Hover or Focus) requires a way to dismiss extra
    content shown on focus WITHOUT moving focus -- the persistent-until-
    tab-away tooltip the previous round shipped had no such escape hatch.
    Escape must add the suppression class and must not call `.blur()`;
    calling it would satisfy "dismissable" by cheating -- moving focus is
    exactly what 1.4.13 forbids as the dismissal mechanism."""
    handler = re.search(
        r"estimateInfo\.addEventListener\('keydown', function \(event\) \{"
        r"(.*?)\n  \}\);",
        CODE,
        re.DOTALL,
    )
    assert handler, "the info button has no keydown listener"
    body = handler.group(1)
    assert "event.key === 'Escape'" in body
    assert "estimateInfo.classList.add('tip-dismissed')" in body
    assert ".blur(" not in body, (
        "the Escape handler must not move focus -- 1.4.13 requires "
        "dismissal WITHOUT blurring the element the tooltip is attached to"
    )


def test_blur_resets_the_suppression_so_the_next_focus_shows_the_tooltip():
    """Suppression must not outlive one focus session, or a single Escape
    early in the app's life would silently disable the tooltip for every
    later visit to this control."""
    handler = re.search(
        r"estimateInfo\.addEventListener\('blur', function \(\) \{"
        r"(.*?)\n  \}\);",
        CODE,
        re.DOTALL,
    )
    assert handler, "the info button has no blur listener"
    assert "estimateInfo.classList.remove('tip-dismissed')" in handler.group(1)


def test_the_dismissal_state_is_scoped_to_the_estimate_info_button():
    """Row status tooltips stay hover-only by design (Task 6's own rule --
    the status span is not focusable, so :focus-visible never applies to
    it); this fix must not add keyboard dismissal machinery to `rowNode()`
    or generalise the class to every `[data-tip]` element."""
    assert CODE.count("tip-dismissed") == 2, (
        "tip-dismissed should be set in exactly one place and cleared in "
        "exactly one place, both on the estimate info button"
    )
    row_body = _function_body(CODE, "rowNode")
    assert "tip-dismissed" not in row_body, (
        "the row's Missing status tooltip must stay hover-only -- it has "
        "no keyboard dismissal state to manage"
    )


def test_the_dismissed_rule_outranks_the_shared_tooltip_primitive():
    """CSS specificity, not source order, is what must decide this: the
    dismissal rule needs strictly higher specificity than
    `[data-tip]:focus-visible::after` (an attribute selector plus a
    pseudo-class) so it always wins regardless of where either rule sits
    in the file."""
    rule = re.search(
        r"\.skills-estimate-info\.tip-dismissed:focus-visible::after\s*\{([^}]*)\}",
        CSS,
    )
    assert rule, (
        "no .skills-estimate-info.tip-dismissed:focus-visible::after rule -- "
        "the suppression class has no visual effect"
    )
    body = rule.group(1)
    assert "opacity: 0" in body
    assert "visibility: hidden" in body


def test_the_estimate_info_button_has_a_hidden_override():
    """Its base rule sets `display`, so the [hidden] trap DESIGN.md names
    applies here too: an author rule beats the UA stylesheet's
    `[hidden] { display: none }` regardless of specificity."""
    assert ".skills-estimate-info[hidden] { display: none; }" in CSS


def test_the_estimate_info_button_uses_only_existing_tokens():
    """Restrained treatment: no new colour, no decorative background, and
    the app's own dim-text token rather than a literal."""
    rule = re.search(r"\.skills-estimate-info\s*\{([^}]*)\}", CSS)
    assert rule, ".skills-estimate-info has no rule"
    body = rule.group(1)
    assert "display: inline-flex" in body
    assert "var(--" in body, "the button must reuse an existing token"
    assert "#" not in body, "a literal hex colour would be a new, unreviewed one"


def test_the_estimate_info_button_gets_the_shared_focus_ring():
    """THE focus indicator (style.css) is one shared rule so every
    focusable control gets the same measured contrast; a control left out
    of it falls back to the UA ring, which the same block's own comment
    says resolves near-black on this dark page."""
    rule = re.search(r"\.btn:focus-visible,(.*?)\{", CSS, re.DOTALL)
    assert rule, "the shared :focus-visible rule is gone"
    assert ".skills-estimate-info:focus-visible" in rule.group(1)


# ---- Task 6: the dev fixture exercises every edge ----------------------


def test_the_dev_fixture_gives_every_character_all_three_estimate_fields():
    for character in DEV_CHARACTERS:
        assert character["status"] is not None, (
            f"{character['name']} has no training_estimate_status in the ?dev=1 fixture"
        )


def test_the_dev_fixture_carries_every_training_estimate_status():
    statuses = {c["status"] for c in DEV_CHARACTERS}
    for expected in (
        "available",
        "refresh_required",
        "attributes_unavailable",
        "metadata_unavailable",
    ):
        assert expected in statuses, (
            f"no character in the ?dev=1 fixture carries "
            f"training_estimate_status: {expected!r}, so that estimate "
            "failure mode is not eyeballable in the harness"
        )


def test_the_dev_fixture_has_training_rows_out_of_name_order_plus_unknown():
    training = [c for c in DEV_CHARACTERS if c["readiness"] == "Training"]
    dated = [c for c in training if c["finish"]]
    unknown = [c for c in training if not c["finish"]]
    assert len(dated) >= 2, "need at least two dated Training rows"
    assert len(unknown) >= 1, "need at least one timing-unknown Training row"
    by_name = [c["name"] for c in sorted(dated, key=lambda c: c["name"].lower())]
    by_finish = [c["name"] for c in sorted(dated, key=lambda c: c["finish"])]
    assert by_name != by_finish, (
        "the dated Training rows are already in name order; the fixture "
        "cannot show byTrainingFinishThenName doing anything a name sort "
        "would not"
    )


def test_the_dev_fixture_has_a_missing_tie_break_pair_out_of_name_order():
    missing = [c for c in DEV_CHARACTERS if c["readiness"] == "Missing"]
    by_seconds = {}
    for c in missing:
        by_seconds.setdefault(c["seconds"], []).append(c["name"])
    ties = [
        names
        for seconds, names in by_seconds.items()
        if seconds is not None and len(names) >= 2
    ]
    assert ties, (
        "no two Missing characters share a training_remaining_seconds; the "
        "tie-break by name is not exercised in the harness"
    )
    pair = ties[0]
    assert sorted(pair, key=str.lower) != pair, (
        "the tied pair is already in name order in the fixture array; the "
        "harness could then pass with array order alone standing in for "
        "the tie-break"
    )


def test_the_dev_fixture_has_a_missing_row_with_both_queued_and_unqueued_work():
    assert any(
        c["readiness"] == "Missing" and c["queued_count"] > 0 and c["missing_count"] > 0
        for c in DEV_CHARACTERS
    ), (
        "no Missing character carries both queued_count > 0 and "
        "missing_count > 0, so a mixed queued/unqueued roster row is not "
        "visible in the harness"
    )


def test_the_dev_fixture_has_a_stale_missing_row_with_a_valid_estimate():
    assert any(
        c["readiness"] == "Missing" and c["status"] == "available"
        for c in DEV_CHARACTERS
    )
    assert re.search(r"stale:\s*true,\s*\n\s*readiness:\s*'Missing'", DEV_JS), (
        "the stale Missing character must keep a real training estimate, "
        "not just its stale ESI error"
    )


def test_the_dev_fixture_has_a_long_character_name_and_a_long_missing_skill():
    assert any(len(c["name"] or "") >= 35 for c in DEV_CHARACTERS), (
        "no character name in the fixture is long enough to exercise the "
        "240px name column's ellipsis"
    )
    # The exact skill style.css's own .skills-main comment names as the
    # longest in EVE, so a regression there and here would be caught together.
    assert "Heavy Assault Missile Specialization V" in DEV_JS
