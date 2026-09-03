"""The Profiles route, checked lexically.

Same approach and same reason as test_page_conventions.py: nothing in this
suite renders index.html or executes web/*.js, so what this screen depends
on is enforced by reading its source. These are the facts the UI critique's
and the walkthrough's Profiles findings turned into code, each of which
would fail silently rather than loudly if it were undone.

They are mechanical. Whether the collapsed card is the right shape is a
question for docs/smoke-checklist.md; whether the pill still exists at all
after someone edits the card is a question for here.
"""

import pathlib
import re


def _brace_block(text: str, marker: str) -> str:
    """The body of the first `{...}` block whose opening line contains
    `marker`, matched by brace DEPTH rather than by the first `}` -- a
    naive `{([^}]*)}` stops at the first nested rule's own close, which is
    exactly wrong for a block (an `@media` tier) that contains other rules.
    """
    start = text.index(marker)
    open_at = text.index("{", start) + 1
    depth, i = 1, open_at
    while i < len(text) and depth:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1
    return text[open_at : i - 1]


WEB = pathlib.Path(__file__).resolve().parents[1] / "wingman" / "web"
HTML = (WEB / "index.html").read_text(encoding="utf-8")
CSS = (WEB / "style.css").read_text(encoding="utf-8")
JS = (WEB / "evesettings.js").read_text(encoding="utf-8")
APP = (WEB / "app.js").read_text(encoding="utf-8")
FORMATIONS = (WEB / "formations.js").read_text(encoding="utf-8")

# The route's own markup. Every rule below is about this block and would
# otherwise match a sibling screen that happens to use the same class.
ROUTE = re.search(
    r'<div class="route" id="route-evesettings">.*?\n  </div>', HTML, re.DOTALL
).group(0)
ACCOUNT_ROUTE = re.search(
    r'<div class="route" id="route-accountidentity">.*?\n  </div>',
    HTML,
    re.DOTALL,
).group(0)
BACKUPS_ROUTE = re.search(
    r'<div class="route" id="route-backups">.*?\n  </div>',
    HTML,
    re.DOTALL,
).group(0)


def _strip_html_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


def _strip_js_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"(?m)^\s*//.*$", "", text)


BODY = _strip_html_comments(ROUTE)
CODE = _strip_js_comments(JS)


# ---- the keep depth is the payload's, not the page's -------------------


def test_the_backup_note_takes_its_number_off_the_payload():
    """DESIGN.md's "state that must not be retyped". `auto_keep` lives in
    settings.json, is clamped by settings.validated_eve_settings, and is
    already on the eve_settings_state payload for exactly this sentence.
    Four places once carried the bookmark-keybind count and three of them
    drifted; the one a user read was the one guarding an irreversible act.
    """
    note = re.search(r"var note =(.*?);", CODE, re.DOTALL)
    assert note, "the Backups card no longer explains what it prunes"
    assert "state.auto_keep" in note.group(1), (
        "the keep depth must come off the payload: " + note.group(1)
    )
    assert not re.search(r"\b\d+\b", note.group(1).replace("auto_keep", "")), (
        "a count is typed into the backup note: " + note.group(1)
    )

    # Round 6, P1-3: the sentence now has TWO homes -- the Backups card and
    # the commit row above the button it reassures -- and both must render
    # the SAME string. A second hand-written copy is what this test's own
    # rationale warns about, and this one carries auto_keep, which is
    # exactly the kind of number that drifted before.
    assert "WM.el('es-backup-note').textContent = note;" in CODE, (
        "the Backups card no longer renders the shared note"
    )
    assert "WM.el('es-copy-backup-note')" in CODE, (
        "the commit row's mount point is gone, so the reassurance is back "
        "to being two cards below the button it reassures"
    )
    assert "commitNote.textContent" in CODE, (
        "the commit row's element is looked up but never written to"
    )
    # The MARKUP too, not only the JS. Deleting the <p> leaves every
    # assertion above green -- WM.el returns null, the `if (commitNote)`
    # guard swallows it, and the reassurance is silently back to being two
    # cards below the button. Found by mutating exactly that.
    assert 'id="es-copy-backup-note"' in HTML, (
        "the commit row has no mount point, so the note renders nowhere"
    )
    commit_at = BODY.index('id="es-commit"')
    note_at = BODY.index('id="es-copy-backup-note"')
    assert commit_at < note_at, "the note must follow the copy commit row it reassures"
    assert CODE.count("Every copy backs up what it is about to overwrite") == 1, (
        "the backup sentence is written twice; paintPill's pattern is one "
        "string over two mount points, for this exact reason"
    )


def test_the_backup_note_says_the_prune_is_per_thing():
    """backup.prune keys on (kind, src, stem) -- it keeps the newest N of
    EACH backed-up thing, not N in total. "The last 10 backups are kept"
    would be a plausible, wrong reading of a list that silently shortens.
    """
    assert "of each" in CODE, "the note must not imply one global keep window"


# ---- the two destructive buttons no longer look alike ------------------


def test_deleting_a_backup_is_marked_and_restoring_is_not():
    """Both were a plain .btn, so permanently destroying a backup looked
    identical to restoring one -- on an app that already marks its other
    irreversible action (skills.js's Forget character) with .danger.
    """
    delete = re.search(r"button\('Delete',.*?\}, '(\w+)'\)", CODE, re.DOTALL)
    assert delete and delete.group(1) == "danger", "Delete is not marked danger"
    restore = re.search(r"button\('Restore',(.*?)\}\)\)", CODE, re.DOTALL)
    assert restore and "danger" not in restore.group(1), (
        "Restore is not destructive and must not carry the treatment"
    )


# ---- the backup row is columns, not one text node ----------------------


def test_every_backup_column_class_has_a_rule():
    """The row is three spans and two buttons; a class with no rule behind
    it is an inert screen that looks deliberate. `.mono` is the specific
    trap here -- it exists only as input.field.mono / span.field.mono /
    textarea.field.mono, so a bare .mono on a plain span does nothing at
    all, which is how the date would quietly stop being monospace.
    """
    for cls in ("bk-when", "bk-what", "bk-origin"):
        assert cls in CODE, f"the backup row no longer builds .{cls}"
        assert re.search(rf"#es-backups\s+\.{cls}\s*\{{", CSS), (
            f".{cls} is built but nothing styles it"
        )
    assert "'bk-when mono'" not in CODE and '"bk-when mono"' not in CODE, (
        "a bare .mono class does nothing; #es-backups .bk-when sets the face"
    )


def test_backup_rows_align_target_and_origin_to_the_same_baseline():
    """.bk-what stacks two lines (name, meta); centring every column across
    the row's full height put Origin between them rather than beside the
    name it actually describes. Aligning the row to its start keeps Origin
    level with the name line the eye reads first, tightening the
    Target-to-Origin association within one row.
    """
    grid = re.search(r"\.es-backup-grid \{([^}]*)\}", CSS)
    assert grid, ".es-backup-grid has no rule"
    assert "align-items: start" in grid.group(1)
    assert "align-items: center" not in grid.group(1)
    # The pinned track: the target identity keeps the flexible column
    # regardless of the alignment fix above.
    assert "minmax(220px, 1fr)" in grid.group(1)


def test_origin_reads_as_its_own_column_not_as_the_targets_secondary_text():
    """.bk-meta (the target's own raw id) and .bk-origin (the backup's
    creation type) are two different axes of information about one row.
    Painted in the same faint tone they read as one column of secondary
    text; matching Origin to the date's tone instead keeps it visually
    distinct from the identity it sits beside.
    """
    origin = re.search(r"#es-backups \.bk-origin \{([^}]*)\}", CSS)
    assert origin, "#es-backups .bk-origin has no rule"
    assert "var(--text-dim)" in origin.group(1)

    when = re.search(r"#es-backups \.bk-when \{([^}]*)\}", CSS)
    assert when and "var(--text-dim)" in when.group(1), (
        "Date and Origin should share one tone as the row's two fact columns"
    )
    meta = re.search(r"(?<!bk-name, )#es-backups \.bk-meta \{([^}]*)\}", CSS)
    assert meta and "var(--text-faint)" in meta.group(1), (
        "the target's own secondary id must stay the dimmer of the two tones"
    )


def test_origin_still_names_only_the_backup_creation_type():
    """Origin must never be read as which profile a backup came from -- it
    is Automatic/Manual, and only that, in both the matcher and the row
    builder. A geometry or colour change here must not have touched this.
    """
    matcher = re.search(
        r"function backupMatches\(item, needle\) \{(.*?)\n  \}", CODE, re.DOTALL
    )
    assert matcher
    assert "item.origin === 'auto' ? 'Automatic' : 'Manual'" in matcher.group(1)
    render = re.search(r"function renderBackups\(\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert render
    assert "item.origin === 'auto' ? 'Automatic' : 'Manual'" in render.group(1)


def test_the_backup_stamp_is_punctuated_but_not_sliced_blind():
    """backup.parse_name joins its date and time groups raw, so `created`
    is 20260824-140300. Turning the row into columns buys nothing if the
    date column is still fifteen unbroken digits -- and a blind slice would
    render a changed stamp as nonsense rather than as itself.
    """
    fn = re.search(r"function whenText\(created\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert fn, "the backup stamp is no longer punctuated"
    body = fn.group(1)
    assert "exec(" in body and "return created" in body, (
        "whenText must fall back to the raw stamp when it does not match"
    )


# ---- the mode switch has a word in front of it -------------------------


def test_the_characters_accounts_switch_is_labelled():
    """It changes what the source dropdown, the target list and the filter
    all mean, and was the only unlabelled control on the screen. The .lab
    was there holding the 118px column; it just had nothing in it.
    """
    row = re.search(
        r'<div class="row">\s*<span class="lab">(.*?)</span>.*?name="es-kind"',
        BODY,
        re.DOTALL,
    )
    assert row, "the mode switch no longer leads with a .lab"
    label = row.group(1).strip()
    assert label, "the mode switch's label column is empty again"
    # R3. Four labels in this card said "Copy" -- the card title, this
    # switch, `Copy from` and `Copy to selected` -- across three different
    # meanings, and this is the one whose options (`Characters`,
    # `Accounts`) already say what they select. The label stays, for the
    # reason above; the WORD is what was redundant.
    assert "copy" not in label.lower(), (
        "the mode switch is labelled `Copy` again; it is the fourth `Copy` "
        "in one card and the only one whose options already self-describe"
    )


# ---- the settings-folder path joins the rest of the app ----------------


def test_both_folder_paths_are_values_and_not_input_lookalikes():
    """Two findings in one row, and the second undid half of the first.

    It was the one path in the app in the proportional face, the one row
    whose first element was off the shared label column, and it had no
    truncation -- so a long root pushed the Choose button toward the right
    edge of a card already narrower than 620px at the window floor. The
    fix was span.field.mono, which carried a mono face, the shared column
    and an end ellipsis.

    It also carried .field's INPUT costume -- fill, border, radius -- onto
    a value that cannot be typed into: computed rgb(12, 10, 15), the same
    fill as the real Filter... input below it and as the genuinely EDITABLE
    #f-recdir one route away (round 3's P4). .es-path is the same row's
    answer without the costume, so this asserts both halves: the path is on
    the shared label column, in .es-path, and .es-path is not .field.
    """
    for ident in ("es-root", "es-folder-root"):
        # The label column and the path in one match: on this row they are
        # one fact, and a .lab that drifted onto another row would satisfy
        # two separate assertions while looking exactly as wrong.
        row = re.search(
            rf'<span class="lab">[^<]*</span>\s*<span id="{ident}"[^>]*'
            rf'class="([^"]*)"',
            BODY,
        )
        assert row, f"#{ident} is not a span on the shared label column"
        classes = row.group(1).split()
        assert "es-path" in classes, (
            f"#{ident} must be an .es-path value: {row.group(1)}"
        )
        assert "field" not in classes, (
            f"#{ident} is wearing the input treatment again: {row.group(1)}"
        )

    # The four things .field was carrying for a reason, none of which were
    # about looking like an input. A .es-path that lost min-width or the
    # ellipsis puts Profiles 7's row back to a long root pushing the one
    # control on it off the right edge.
    rule = re.search(r"\.es-path \{([^}]*)\}", CSS)
    assert rule, ".es-path has no rule -- the paths render unstyled"
    body = rule.group(1)
    for prop in ("min-width", "text-overflow", "var(--mono)", "user-select"):
        assert prop in body, f".es-path dropped {prop}: {body}"
    for costume in ("border", "background", "var(--field)"):
        assert costume not in body, (
            f".es-path is wearing the input treatment again ({costume}): {body}"
        )


# ---- the gear's name does not appear inside the screen renamed off it --


def test_no_card_heading_borrows_the_gears_own_name():
    """Round 2's Profiles 8. DESIGN.md renamed the TAB away from "EVE
    Settings" because a tab of that name beside a gear named "Settings"
    describes the implementation -- and the cards kept the word, so the
    gear's own name went on appearing twice inside the screen that was
    renamed to avoid it.

    The word is not banned: it is the user's own ("a settings change in one
    character that I want to propagate"), and PRODUCT.md says to name
    things the way they do. What is banned is the UNQUALIFIED form, which
    is the gear's name. Settings > Folders disambiguates the same way --
    "EVE gamelogs" beside "Recordings".
    """
    headings = re.findall(r"<h2>(.*?)</h2>", BODY, re.DOTALL)
    assert headings, "the route has no card headings at all"
    for heading in headings:
        # The pill lives inside the folder card's h2; it is not part of the
        # name and says "EVE closed" / "EVE running", which would satisfy
        # the qualifier on its own.
        words = re.sub(r"<[^>]*>.*", "", heading, flags=re.DOTALL).lower()
        if "settings" not in words:
            continue
        assert "eve settings" in words, (
            "a card heading uses the gear's own unqualified name: " + words
        )


# ---- the source is not the smallest control on the screen --------------


def test_the_source_is_not_held_to_the_two_up_select_track():
    """P3. `Copy from` decides what content overwrites every ticked
    character and was the narrowest control on the screen -- 149 CSS px
    against the filter's 432 -- because `.settings .row > select.field` is
    a fixed 150px track written for the Server/Profile pair that shares a
    row. `Copy from` is alone on its row and inherited a cap meant for
    two-up.

    An id override, so Server and Profile keep the fixed track. Asserted
    here because the shared rule out-specifies any class this screen could
    add, so the day the override is dropped the control silently goes back
    to 150px with nothing else changing.
    """
    shared = re.search(r"\.settings \.row > select\.field \{([^}]*)\}", CSS)
    assert shared, "the shared select track is gone; this override may be stale"
    assert "flex:" in shared.group(1), shared.group(1)

    rule = re.search(r"#es-source \{([^}]*)\}", CSS)
    assert rule, "#es-source no longer overrides the shared fixed select track"
    assert re.search(r"flex:\s*1\b", rule.group(1)), (
        "the source must take the row's measure, not a fixed track: " + rule.group(1)
    )


# ---- the folder card collapses, and the pill does not go with it -------


def test_the_folder_card_has_two_faces_and_only_one_shows():
    """The setup is correct after the first visit and inert forever after;
    the copy card below it is why the screen exists. Both halves are
    toggled from one place so they cannot both be up.
    """
    assert '<div class="row" id="es-folder-summary" hidden>' in BODY, (
        "the collapsed face is gone, or no longer starts hidden"
    )
    assert '<div id="es-folder-detail">' in BODY
    paint = re.search(r"function paintFolder\(\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert paint, "paintFolder is gone"
    assert "es-folder-summary').hidden = open" in paint.group(1)
    assert "es-folder-detail').hidden = !open" in paint.group(1)


def test_the_eve_pill_is_outside_the_half_that_collapses():
    """It is the running-client hazard the copy below is guarded against.
    Inside the folder row it would vanish with the controls on every visit
    after the first -- which is every visit that matters.
    """
    summary = BODY[BODY.index("es-folder-summary") : BODY.index("es-folder-detail")]
    assert "es-eve-state" not in summary
    detail = BODY[BODY.index("es-folder-detail") : BODY.index("es-warning")]
    assert "es-eve-state" not in detail
    # Matched on the heading's SHAPE, not its words: what this test is
    # about is that the pill sits in the h2 rather than in either face, and
    # round 2's Profiles 8 renamed the heading underneath the old literal.
    assert re.search(r'<h2>[^<]+<span id="es-eve-state"', BODY), (
        "the pill must sit in the card heading, which neither face hides"
    )


def test_the_pill_undoes_the_heading_treatment():
    """.card > h2 is uppercase and letter-spaced. Un-neutralised, the pill
    reads as EVE RUNNING in small caps -- a status badge wearing a heading.
    """
    rule = re.search(r"#es-eve-state \{([^}]*)\}", CSS)
    assert rule, "#es-eve-state has no rule"
    assert "text-transform: none" in rule.group(1)
    assert "letter-spacing: normal" in rule.group(1)


def test_an_unset_or_unreadable_folder_forces_the_controls_open():
    """There is nothing to summarise, and the user has to act on it."""
    forced = re.search(r"function forcedOpen\(\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert forced, "forcedOpen is gone"
    for term in ("state.root", "state.unreadable", "state.too_broad"):
        assert term in forced.group(1), term


def test_the_card_re_collapses_on_every_visit():
    """Not persisted, on purpose: the point of collapsing it is that the
    target list is on screen at open, and a card that stayed expanded
    across visits gives that straight back.
    """
    route = re.search(
        r"document\.addEventListener\('wm:route'.*?\n    \}\);", CODE, re.DOTALL
    )
    assert route and "expanded = false" in route.group(0), (
        "entering the route no longer re-collapses the folder card"
    )


# ---- the commit says what it will do, and to how many ------------------


def test_the_commit_context_stays_visible_over_the_target_roster():
    """The roster stays fully visible, but its source, cost, hazard and action
    must not scroll away while the user verifies a large target set.
    """
    context_at = BODY.index('id="es-commit-context"')
    roster_at = BODY.index('id="es-targets"')
    assert context_at < roster_at
    assert 'id="es-copy-source"' in BODY[context_at:roster_at]
    assert 'id="es-copy-followup"' in BODY[context_at:roster_at]

    rule = re.search(r"\.es-commit-context \{([^}]*)\}", CSS)
    assert rule and "position: sticky" in rule.group(1)
    assert "top: 0" in rule.group(1)

    paint = re.search(r"function paintCommit\(\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert paint and "es-copy-source" in paint.group(1)
    assert "es-source" in paint.group(1)


def test_the_commit_row_carries_the_count_and_the_hazard():
    """Profiles 1. `Copy to selected` sits at the bottom of the second card;
    the `EVE running` pill lives in the first card's heading, and in the
    scrolled capture the button is on screen and the pill is not. The count
    is Profiles 3's other half -- ui/copy.py puts one in the confirm, and
    the page printed no quantity at all.
    """
    commit = re.search(r'<div class="row" id="es-commit">(.*?)</div>', BODY, re.DOTALL)
    assert commit, "the commit row is gone"
    for part in ('id="es-copy"', 'id="es-copy-count"', 'id="es-eve-state-commit"'):
        assert part in commit.group(1), part


def test_the_commit_row_groups_state_apart_from_action_and_hazard():
    """The count and source are one fact -- what will happen, and to what.
    Grouping them lets the wide tier give that group the row's remaining
    space instead of leaving it as a bare gap between the button on the
    left and a pill stranded at the far right edge.
    """
    commit = re.search(r'<div class="row" id="es-commit">(.*?)</div>', BODY, re.DOTALL)
    assert commit, "the commit row is gone"
    inner = commit.group(1)
    info = re.search(
        r'<span class="es-commit-info">\s*'
        r'<span id="es-copy-count" class="es-count">[^<]*</span>\s*'
        r'<span id="es-copy-source" class="es-copy-source"></span>\s*'
        r"</span>",
        inner,
    )
    assert info, "the count and source no longer share one grouping span"
    assert inner.index('id="es-copy"') < inner.index('class="es-commit-info"')
    assert inner.index('class="es-commit-info"') < inner.index(
        'id="es-eve-state-commit"'
    )

    rule = re.search(r"\.es-commit-info \{([^}]*)\}", CSS)
    assert rule, ".es-commit-info has no rule"


def test_the_commit_bar_widens_to_meet_the_roster_above_the_floor():
    """Capped to the card's 586px prose measure like every other row, the
    commit bar read as a narrow aside pinned to the card's upper-left
    corner while the roster it introduces already spans the full card
    beneath it. Past the 840 floor the bar takes the SAME width the roster
    does, so the two read as one region; at or below the floor nothing
    changes -- DESIGN.md's complementary tier to a floor-anchored
    `max-width: 840px` is `min-width: 841px`.
    """
    generic = re.search(
        r"#route-evesettings > \.settings > \.card:has\(> \.es-roster\) > "
        r":not\(\.es-roster\)([^{]*)\{([^}]*)\}",
        CSS,
    )
    assert generic, "the shared 586px re-cap for the card's non-roster children is gone"
    assert ":not(.es-commit-context)" in generic.group(1), (
        "the commit bar must be excluded from the shared 586px re-cap so its "
        "own rule, not a specificity fight, decides its width"
    )

    base = re.search(r"\.es-commit-context \{([^}]*)\}", CSS)
    assert base and "max-width: 586px" in base.group(1), (
        "below the floor the commit bar must keep the card's narrow prose measure"
    )

    wide = _brace_block(CSS, "@media (min-width: 841px)")
    assert re.search(r"\.es-commit-context\s*\{[^}]*max-width:\s*none", wide), (
        "the commit bar never widens past the card's narrow prose measure"
    )
    assert re.search(
        r"\.es-commit-context > \.hint, \.es-commit-context > \.es-copy-followup\s*"
        r"\{[^}]*max-width:\s*586px",
        wide,
    ), "the bar's own prose must keep the readable measure it widens away from"
    assert re.search(r"\.es-commit-info\s*\{[^}]*flex:\s*1\b", wide), (
        "above the floor the state group must absorb the row's slack, not "
        "leave the pill stranded far from the button and count"
    )


def test_the_second_pill_is_the_same_pill_and_not_a_second_sentence():
    """A hand-written hazard string here would be free to drift from the one
    ui/copy.py states in the confirm a second later. One painter, two mount
    points -- so there is exactly one place the words are decided.
    """
    paint = re.search(r"function paintPill\(running\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert paint, "paintPill is gone"
    body = paint.group(1)
    assert "es-eve-state'" in body and "es-eve-state-commit'" in body, (
        "both mount points must be painted by paintPill"
    )
    assert CODE.count("'EVE running'") == 1, (
        "the hazard string is written twice; it may only be written once"
    )


def test_the_commit_pill_overrides_hidden():
    """.pill sets display: inline-flex, and an author rule beats the UA
    stylesheet's [hidden] { display: none } regardless of specificity. Without
    the override the pill evesettings.js hides stays on screen -- DESIGN.md's
    named trap, which six rules in this file carry a note about and one
    shipped without anyway.
    """
    assert re.search(r"#es-eve-state-commit\[hidden\]\s*\{[^}]*display:\s*none", CSS)
    assert "es-eve-state-commit').hidden" in CODE, (
        "nothing sets hidden on the pill, so the override guards nothing"
    )


# ---- the roster is a verification surface ------------------------------


def test_the_roster_is_columned_and_uncapped():
    """Profiles 2. Select-all is the normal path, so what is wanted is to SEE
    who is about to be overwritten. A single column capped at 38vh gave two
    nested scrollbars and rows clipped mid-name at both edges, with a
    half-legible name directly above a full-strength accent button.

    Backups now follow the same rule: the route owns scrolling and reveals a
    long history in explicit batches rather than through a nested viewport.
    """
    assert '<div id="es-targets" class="es-roster"></div>' in BODY, (
        "the roster must not be a .list-scroll -- that is the inner scroller"
    )
    rule = re.search(r"\.es-roster \{([^}]*)\}", CSS)
    assert rule, ".es-roster has no rule"
    assert "columns:" in rule.group(1), "the roster must be columned"
    assert "max-height" not in rule.group(1), (
        "a cap here is what produced the nested scrollbars"
    )
    assert not re.search(r"#es-backups\s*\{[^}]*max-height", CSS), (
        "backups must use the route scrollbar, not a nested capped viewport"
    )
    assert 'id="es-backups" class="list-scroll"' not in BACKUPS_ROUTE


def test_a_name_may_not_break_across_a_column():
    """Half a name in one column and half in the next is the clipping this
    finding is about, reintroduced by a different mechanism."""
    assert re.search(r"\.es-roster > \.check \{[^}]*break-inside:\s*avoid", CSS)


# ---- where a folder is, is Wingman's job -------------------------------


def test_the_settings_root_can_be_detected_not_only_chosen():
    """Profiles 4. Detect exists in Settings > Folders and on the first-run
    screen, for a folder shallower and better known than this one, while the
    folder the product is named for got `Choose folder...` alone.
    PRODUCT.md: "Do explain Wingman -- where a folder is."
    """
    assert 'id="es-detect"' in BODY
    assert "eve_settings_detect_root" in CODE, "the button is not wired"


def test_choosing_and_detecting_end_the_same_way():
    """Both answer the same question, so both must drop the selection (a
    source picked in the old tree does not exist in the new one), re-read the
    state and re-resolve names. Two hand-rolled copies would drift.
    """
    fn = re.search(r"function chooseRoot\(method\) \{(.*?)\n    \}", CODE, re.DOTALL)
    assert fn, "chooseRoot is gone -- the two paths have been forked again"
    for term in ("selected = {}", "refresh()", "eve_settings_resolve_names"):
        assert term in fn.group(1), term
    for method in ("eve_settings_pick_root", "eve_settings_detect_root"):
        assert "chooseRoot('" + method + "')" in CODE, method


# ---- name what is blocking you, not what is downstream -----------------


def test_the_empty_roster_names_the_blocking_condition_first():
    """Profiles 5. With no folder chosen this said "No other characters in
    this profile." There is no profile. The filter case is last because it is
    the only one of the four the user reached deliberately.
    """
    fn = re.search(r"function emptyText\(needle\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert fn, "emptyText is gone"
    body = fn.group(1)
    root_at = body.index("state.root")
    needle_at = body.index("if (needle)")
    assert root_at < needle_at, (
        "the blocking condition must be tested before the filter"
    )
    assert "unreadable" in body, "an unread folder is not an empty one"


def test_an_empty_dropdown_does_not_render_as_a_working_one():
    """Profiles 6. Blank, un-placeholdered and undimmed before a folder
    exists, Server and Profile read as broken rather than as not-yet-
    applicable. `Copy from` is the same control with the same failure and is
    held to the same rule.
    """
    fill = re.search(
        r"function fill\(id, items, current, empty\) \{(.*?)\n  \}", CODE, re.DOTALL
    )
    assert fill, "fill no longer takes an empty-state label"
    assert "el.disabled = !list.length" in fill.group(1)
    source = re.search(r"function renderSource\(\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert source and "el.disabled = !list.length" in source.group(1), (
        "Copy from must not be the one blank dropdown beside two placeholdered ones"
    )
    assert re.search(
        r"#es-server:disabled, #es-profile:disabled, #es-source:disabled \{[^}]*color:",
        CSS,
    ), "nothing makes the disabled state visible; the UA's own is light-scheme grey"


# ---- the one control on its row looks like one -------------------------


def test_change_is_a_button_not_a_link():
    """Profiles 7. The summary row was a mono boxed path that looked
    interactive and is not, dim static text, and then the only thing on it
    that acts -- which was link-styled, borderless, and no more prominent
    than the text beside it. P4 took the box off the path; this rule is
    about the other half, and it survives that on its own terms.
    """
    summary = BODY[BODY.index("es-folder-summary") : BODY.index("es-folder-detail")]
    assert 'id="es-folder-edit" class="btn"' in summary, (
        "the row's one control must not be the quietest thing on it"
    )


# ---- X1's execution on this route --------------------------------------


def test_selective_copy_controls_are_inside_the_copy_card_in_action_order():
    """The new choice belongs between its source and target controls."""
    card = re.search(
        r'<section class="card">\s*<h2>Copy EVE settings</h2>(.*?)</section>',
        BODY,
        re.DOTALL,
    )
    assert card, "the existing Copy EVE settings card is missing"
    copy_body = card.group(1)
    source_at = copy_body.index('id="es-source"')
    options_at = copy_body.index('id="es-copy-options"')
    filter_at = copy_body.index('id="es-filter"')
    assert source_at < options_at < filter_at, (
        "What to copy must follow Copy from and precede the target filter"
    )
    assert BODY.count('id="es-copy-options"') == 1, (
        "the copy options must not also be mounted outside the copy card"
    )


def test_selective_copy_explains_recognized_and_other_settings():
    assert (
        "Checked groups are copied as a unit. Unchecked groups stay unchanged. "
        "Everything else is copied."
    ) in BODY


def test_bulk_controls_name_their_scope():
    assert ">Select shown</button>" in BODY
    assert ">Clear selection</button>" in BODY


def test_copy_button_and_followup_do_not_infer_python_results():
    paint = re.search(r"function paintCommit\(\) \{(.*?)\n  \}", CODE, re.DOTALL).group(
        1
    )
    assert "Copy to " in paint
    assert "Copy operation in progress" in paint
    assert ">Copy to selected</button>" not in BODY
    assert 'id="es-copy-followup"' in BODY
    assert 'id="es-copy-view-backups"' in BODY
    assert "backups created" not in CODE.lower()


def test_copy_followup_tracks_only_a_successful_copy_lifecycle():
    mutate = re.search(r"function mutate\(method\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert mutate
    block = mutate.group(1)
    assert "pendingMutation = method;" in block
    assert "if (method === 'eve_settings_copy')" in block
    assert block.index(
        "pendingMutation = '';", block.index("if (!accepted)")
    ) < block.index("setBusy(false);", block.index("if (!accepted)"))

    done = re.search(
        r"WM\.handle\('onEveSettingsDone', function \(payload\) \{(.*?)\n  \}\);",
        CODE,
        re.DOTALL,
    )
    assert done
    completion = done.group(1)
    assert "var completedMutation = pendingMutation;" in completion
    assert completion.index("pendingMutation = '';") < completion.index(
        "setBusy(false);"
    )
    assert re.search(
        r"completedMutation === 'eve_settings_copy'.*?payload\.ok",
        completion,
        re.DOTALL,
    )
    copy_branch = re.search(
        r"if \(completedMutation === 'eve_settings_copy'\) \{(.*?)\n    \}",
        completion,
        re.DOTALL,
    )
    assert copy_branch and "selected = {};" in copy_branch.group(1)
    assert "copyFollowup" in copy_branch.group(1)
    assert "selected = {};" not in completion.replace(copy_branch.group(0), "")

    route = re.search(
        r"document\.addEventListener\('wm:route'.*?\n    \}\);", CODE, re.DOTALL
    )
    assert route and "clearCopyFollowup()" not in route.group(0)
    opener = re.search(r"function openBackups\(\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert opener and "clearCopyFollowup()" not in opener.group(1)

    root = re.search(r"function chooseRoot\(method\) \{(.*?)\n    \}", CODE, re.DOTALL)
    select = re.search(
        r"\['es-server', 'es-profile'\]\.forEach.*?"
        r"addEventListener\('change', function \(\) \{(.*?)\n      \}\);",
        CODE,
        re.DOTALL,
    )
    kind = re.search(
        r"querySelectorAll\('input\[name=\"es-kind\"\]'\).*?"
        r"addEventListener\('change', function \(\) \{(.*?)\n        \}\);",
        CODE,
        re.DOTALL,
    )
    source = re.search(
        r"WM\.el\('es-source'\)\.addEventListener\('change', function \(\) \{"
        r"(.*?)\n    \}\);",
        CODE,
        re.DOTALL,
    )
    assert root and "var previousRoot = state && state.root;" in root.group(1)
    assert "clearCopyFollowup();" not in root.group(1).split("WM.send", 1)[0]
    assert "payload && payload.root !== previousRoot" in root.group(1)
    for name, handler in (
        ("server/profile", select),
        ("kind", kind),
        ("source", source),
    ):
        assert handler and "clearCopyFollowup();" in handler.group(1), name
    assert (
        "WM.el('es-copy-view-backups').addEventListener('click', openBackups);" in CODE
    )


def test_copy_followup_is_quiet_and_hideable():
    followup = re.search(r'<[^>]+id="es-copy-followup"[^>]*>', BODY)
    assert followup and 'role="status"' not in followup.group(0)
    assert re.search(r"\.es-copy-followup\[hidden\]\s*\{[^}]*display:\s*none", CSS)


def test_copy_group_rendering_uses_kind_payload_and_remembers_seen_ids():
    """Payload groups and per-kind choices survive repaints without reset."""
    assert re.search(
        r"var copyGroupSelections\s*=\s*\{\s*characters:\s*\{\},\s*"
        r"accounts:\s*\{\}\s*\}",
        CODE,
    ), "the independent per-kind selection store is missing"
    render = re.search(r"function renderCopyGroups\(\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert render, "copy groups are not rendered"
    block = render.group(1)
    null_guard = block.index("if (!state) return;")
    availability_read = block.index("state.selective_copy_available")
    assert null_guard < availability_read, (
        "renderCopyGroups must guard null state before reading availability"
    )
    assert block.index("row.hidden = true;") < null_guard
    assert block.index("host.innerHTML = '';") < null_guard
    assert "var choices = copyGroupSelections[currentKind];" in block
    assert re.search(
        r"var groups = \(state\.copy_groups &&\s*"
        r"state\.copy_groups\[currentKind\]\) \|\| \[\];",
        block,
    ), "the visible kind must index the payload rather than a page-owned table"
    assert re.search(
        r"if \(!Object\.prototype\.hasOwnProperty\.call\(choices, group\.id\)\) "
        r"\{\s*choices\[group\.id\] = !!group\.default_on;\s*\}",
        block,
        re.DOTALL,
    ), "default_on must initialize only an id the user has not seen before"


def test_switching_copy_kind_redraws_its_groups():
    switch = re.search(
        r"document\.querySelectorAll\('input\[name=\"es-kind\"\]'\).*?"
        r"radio\.addEventListener\('change', function \(\) \{(.*?)\n        \}\);",
        CODE,
        re.DOTALL,
    )
    assert switch, "the Characters/Accounts change handler is missing"
    assert "renderCopyGroups();" in switch.group(1), (
        "switching kind must redraw the kind-indexed copy groups"
    )


def test_copy_click_sends_groups_only_on_the_structured_path():
    """Available copy gets the selected ids as arg three; fallback stays plain."""
    click = re.search(
        r"WM\.el\('es-copy'\)\.addEventListener\('click'.*?\n    \}\);",
        CODE,
        re.DOTALL,
    )
    assert click, "the copy click handler is missing"
    assert re.search(
        r"if \(state\.selective_copy_available\) \{\s*"
        r"mutate\('eve_settings_copy',\s*WM\.el\('es-source'\)\.value,\s*"
        r"targets,\s*selectedGroupIds\(\)\);\s*"
        r"\} else \{\s*"
        r"mutate\('eve_settings_copy',\s*WM\.el\('es-source'\)\.value,\s*"
        r"targets\);\s*\}",
        click.group(0),
        re.DOTALL,
    ), (
        "structured copy must pass selectedGroupIds() as mutate arg three, "
        "while fallback passes only source and targets"
    )


def test_profiles_keeps_one_existing_primary_action():
    assert BODY.count('class="btn acc"') == 1
    assert 'id="es-copy" class="btn acc"' in BODY


def test_copy_is_inert_when_it_cannot_act():
    """X1. The disabled treatment already existed and worked; the attribute
    was missing, so `Copy to selected` was full-strength accent with nothing
    ticked and "No other characters in this profile" printed above it.

    Busy and empty are one decision because they are one question, and
    setBusy setting .disabled itself is what let a finished copy re-enable a
    button whose selection the same push had cleared.
    """
    paint = re.search(r"function paintCommit\(\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert paint, "paintCommit is gone"
    assert "WM.setEnabled('es-copy'" in paint.group(1), (
        "the shared helper decides what is inert, not a hand-rolled variant"
    )
    busy = re.search(r"function setBusy\(value\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert busy and "es-copy').disabled" not in busy.group(1), (
        "setBusy must go through paintCommit, which owns the whole question"
    )


# ---- round 5: the roster, the summary and the retention note -----------


def test_profiles_opens_backups_without_mounting_the_archive_inline():
    assert 'id="es-backups-open"' in BODY
    assert "<h2>Backups</h2>" not in BODY
    assert "function openBackups()" in CODE
    assert "WM.route('backups')" in CODE


def test_profile_tools_are_one_accessible_sibling_group_for_the_context():
    """Backups and Formations stay grouped with the selected profile context.

    The group is now visibly AND programmatically named "Profile tools":
    aria-labelledby points at a visible label rather than restating a
    sentence in aria-label alone, and the sentence it used to carry --
    "Tools for the selected EVE profile" -- overstated the case.
    eve_settings_backup_dir() (paths.py) is one fixed store, not scoped to
    the selected server or profile, so Backups reads across every profile
    ever backed up on this machine -- a label claiming these tools were FOR
    the selected profile was exactly the false claim the brief warns
    against. The tie to context is proximity and style now, not a wording
    promise the payload cannot back up.
    """
    tools = re.findall(
        r'<div class="es-profile-tools"([^>]*)>(.*?)</div>', BODY, re.DOTALL
    )
    assert len(tools) == 1, "profile tools must remain one sibling group"
    attrs, content = tools[0]
    assert 'role="group"' in attrs
    assert 'aria-labelledby="es-profile-tools-label"' in attrs
    assert 'aria-label="Tools for the selected EVE profile"' not in attrs, (
        "the group must not claim these tools belong only to the selected profile"
    )
    label = re.search(r'<span id="es-profile-tools-label"[^>]*>([^<]*)</span>', content)
    assert label and label.group(1).strip() == "Profile tools", (
        "the group's accessible name must also be its VISIBLE text"
    )
    assert 'id="es-backups-open"' in content
    assert 'id="es-formations-open"' in content

    context_end = BODY.index("</section>", BODY.index("es-context-card"))
    tools_at = BODY.index('class="es-profile-tools"')
    copy_at = BODY.index("<h2>Copy EVE settings</h2>")
    assert context_end < tools_at < copy_at
    assert "card" not in attrs.split()


def test_profile_tools_label_reads_as_subordinate_not_as_a_second_heading():
    """.card > h2 is the one heading treatment on the screen; the tools
    label sits outside any card and must not borrow it wholesale, or a
    plain sibling group starts reading as a second card.
    """
    rule = re.search(r"\.es-profile-tools-label \{([^}]*)\}", CSS)
    assert rule, ".es-profile-tools-label has no rule"
    assert "var(--text-label)" in rule.group(1)
    assert "text-transform: uppercase" in rule.group(1)

    group = re.search(r"\.es-profile-tools \{([^}]*)\}", CSS)
    assert group, ".es-profile-tools has no rule"
    assert "border-top" in group.group(1), (
        "the group should read as attached to the context card above it, "
        "not just positioned near it"
    )


def test_backups_is_a_profiles_subroute_with_destination_chrome():
    assert 'id="route-backups"' in HTML
    assert "backups: 'route-backups'" in APP
    assert 'data-route="backups"' not in HTML
    chromeless = re.search(r"WM\.CHROMELESS_ROUTES = \[([^]]+)\]", APP)
    assert chromeless and "'backups'" not in chromeless.group(1)
    eve_routes = re.search(r"WM\.EVE_ROUTES = \[([^]]+)\]", APP)
    assert eve_routes and "'backups'" in eve_routes.group(1)
    assert "name === 'backups'" in APP


def test_backups_entry_routes_once_and_leaves_refresh_to_the_route_listener():
    opener = re.search(r"function openBackups\(\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert opener
    assert "backupVisible = 20;" in opener.group(1)
    assert "WM.route('backups');" in opener.group(1)
    assert "renderBackups()" not in opener.group(1)
    assert "refresh()" not in opener.group(1)

    listener = re.search(
        r"document\.addEventListener\('wm:route'.*?\n    \}\);", CODE, re.DOTALL
    )
    assert listener and "event.detail === 'backups'" in listener.group(0)
    assert "refresh();" in listener.group(0)


def test_backups_route_has_one_heading_and_native_retention_disclosure():
    assert BACKUPS_ROUTE.count("<h1>Backups</h1>") == 1
    assert "<h2>Backups</h2>" not in BACKUPS_ROUTE
    assert '<button class="btn" id="es-backups-back" type="button">' in BACKUPS_ROUTE
    assert '<details id="es-retention">' in BACKUPS_ROUTE
    assert "<summary>Retention</summary>" in BACKUPS_ROUTE
    assert 'id="es-backup-filter"' in BACKUPS_ROUTE
    assert 'id="es-backup-filter-clear"' in BACKUPS_ROUTE


def test_the_last_backup_menu_opens_away_from_the_route_edge():
    rule = re.search(
        r"\.es-backup-row:last-child \.bk-menu > button \{(.*?)\}",
        CSS,
        re.DOTALL,
    )
    assert rule, "the final backup menu still opens into the route boundary"
    assert "top: auto" in rule.group(1)
    assert re.search(r"bottom:\s*calc\(100% \+ 4px\)", rule.group(1))


def test_backups_retention_has_a_visible_native_state_affordance():
    assert re.search(r"#es-retention > summary::before \{[^}]*content:", CSS, re.DOTALL)
    assert re.search(
        r"#es-retention\[open\] > summary::before \{[^}]*transform:",
        CSS,
        re.DOTALL,
    )


def test_backups_route_preserves_a_readable_measure_for_prose_and_controls():
    measure = re.search(
        r"#route-backups\s+\.es-backups-card\s*>\s*"
        r":not\(#es-backups\):not\(#es-backup-head\)\s*\{([^}]*)\}",
        CSS,
    )
    assert measure and "max-width: 586px" in measure.group(1)


def test_the_retention_note_follows_the_action_it_qualifies():
    """R2. A retention policy opened the Backups card, ahead of the one
    control in it. The note is not cut -- it is the promise that makes the
    copy card above it safe -- but a card whose point is an action may not
    lead with the policy that governs it.
    """
    card = re.search(
        r'<section class="card es-backups-card">(.*?)</section>',
        BACKUPS_ROUTE,
        re.DOTALL,
    )
    assert card, "the Backups card is missing"
    button = card.group(1).index('id="es-backup-profile"')
    note = card.group(1).index('id="es-backup-note"')
    listing = card.group(1).index('id="es-backups"')
    assert button < note < listing, (
        "the retention note is back above the profile backup action, or has "
        "fallen below the list of backups it describes the pruning of"
    )


def test_the_collapsed_summary_names_the_server_and_the_profile():
    """R5. `Tranquility - Default` sat beside a labelled `Folder`, unlabelled,
    though the server and the profile decide what a copy will hit exactly as
    much as the folder does -- and `Default` alone does not read as a profile
    name. The words go in the TEXT: `.settings .row > .lab` is width:100%, so
    a second label in that row would stack and break it into three lines.
    """
    assert re.search(r"setLabel\(nameOf\(state\.servers", CODE), (
        "the collapsed summary prints the server name bare again"
    )
    assert re.search(r"setLabel\(nameOf\(state\.profiles", CODE), (
        "the collapsed summary prints the profile name bare again"
    )
    summary = re.search(r'id="es-folder-summary".*?</div>', BODY, re.DOTALL).group(0)
    assert summary.count('class="lab"') == 1, (
        "a second .lab in the collapsed row: it is width:100% and stacks, "
        "which breaks the one-line summary the card collapses to"
    )


# ---- account identity and full-width backup safety ---------------------


def test_account_identification_is_a_focused_subscreen_from_account_mode():
    assert 'id="es-account-tools"' in BODY
    assert 'id="es-account-summary"' in BODY
    assert 'id="es-account-guidance"' in BODY
    assert 'id="es-identify-open"' in BODY
    assert 'id="es-identity-panel"' not in BODY, (
        "account management must not expand inside the copy form"
    )
    for ident in (
        "ai-back",
        "es-identity-panel",
        "es-manage-toggle",
        "es-identify-start",
        "es-identify-check",
        "es-identify-cancel",
        "es-identify-candidate",
    ):
        assert f'id="{ident}"' in ACCOUNT_ROUTE
    render = re.search(r"function renderIdentity\(\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert render and "kind() === 'accounts'" in render.group(1)
    assert "WM.current_route !== 'accountidentity'" in render.group(1)
    assert "WM.route('accountidentity')" in CODE


def test_account_identification_summary_and_entry_match_backend_preconditions():
    render = re.search(r"function renderIdentity\(\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert render
    block = render.group(1)
    assert "account.account_name" in block
    assert "state.accounts.length" in block
    assert "var characters = (state && state.characters) || [];" in block
    assert re.search(r"state\.accounts\.length\s*&&\s*state\.characters\.length", block)
    assert "state.identity_characters" not in block
    assert (
        "No accounts found in this profile. Launch a character, make a small settings change, then close EVE completely."
        in block
    )
    assert (
        "No characters found in this profile. Launch a character, make a small settings change, then close EVE completely."
        in block
    )
    assert "Identify accounts to replace internal IDs with names." in block
    assert "es-identify-open').hidden" in block
    assert re.search(r"#es-identify-open\[hidden\]\s*\{[^}]*display:\s*none", CSS)


def test_account_guidance_is_available_only_inside_a_selected_profile():
    """A missing root/profile must not masquerade as failed account discovery."""
    render = re.search(r"function renderIdentity\(\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert render
    block = render.group(1)
    assert "var profileSelected" in block
    assert "state.root" in block and "state.profile" in block
    assert "es-account-tools').hidden = !accountsMode || !profileSelected" in block


def test_account_identity_route_is_a_chromeless_profiles_subscreen():
    assert "accountidentity: 'route-accountidentity'" in APP
    assert 'data-route="accountidentity"' not in HTML
    chromeless = re.search(r"WM\.CHROMELESS_ROUTES = \[([^]]+)\]", APP)
    eve_routes = re.search(r"WM\.EVE_ROUTES = \[([^]]+)\]", APP)
    assert chromeless and "'accountidentity'" in chromeless.group(1)
    assert eve_routes and "'accountidentity'" in eve_routes.group(1)
    assert "name === 'accountidentity'" in APP


def test_identification_exposes_its_existing_five_step_progress():
    progress = re.search(r'<p[^>]+id="ai-progress"[^>]*>', ACCOUNT_ROUTE)
    assert progress and "aria-live" not in progress.group(0)

    paint = re.search(
        r"function paintIdentification\(step, message\) \{(.*?)\n  \}", CODE, re.DOTALL
    )
    assert paint
    for label in (
        "Step 1 of 5 · Prepare",
        "Step 2 of 5 · Watch for changes",
        "Step 3 of 5 · Confirm character",
        "Step 4 of 5 · Name account",
        "Step 5 of 5 · Review roster",
    ):
        assert label in paint.group(1)
    assert "WM.el('ai-progress').textContent" in paint.group(1)


def test_identification_prerequisite_precedes_the_start_action():
    actions = re.search(
        r'<div class="row es-identify-actions">(.*?)</div>',
        ACCOUNT_ROUTE,
        re.DOTALL,
    )
    assert actions
    block = actions.group(1)
    assert "Close every EVE client" in block
    prerequisite_at = block.index("Close every EVE client")
    start_at = block.index('id="es-identify-start"')
    assert prerequisite_at < start_at
    assert 'id="ai-prerequisite" class="ai-prerequisite"' in block
    assert ">Begin identification</button>" in block
    paint = re.search(
        r"function paintIdentification\(step, message\) \{(.*?)\n  \}", CODE, re.DOTALL
    )
    assert paint and (
        "ai-prerequisite').hidden = watching || candidate || name || roster"
        in paint.group(1)
    )
    assert "Close every EVE client" not in re.search(
        r'<section id="ai-intro">(.*?)</section>', ACCOUNT_ROUTE, re.DOTALL
    ).group(1)


def test_identification_uses_the_five_step_markup_and_required_copy():
    for ident in (
        "ai-intro",
        "es-identify-candidate",
        "ai-name-step",
        "es-account-name",
        "es-account-name-save",
        "ai-roster-step",
        "ai-roster-heading",
        "ai-roster-count",
        "ai-roster-characters",
        "ai-roster-add-row",
        "ai-roster-character",
        "ai-roster-add",
        "ai-roster-empty",
        "ai-roster-done",
        "ai-identify-another",
    ):
        assert f'id="{ident}"' in ACCOUNT_ROUTE
    for copy in (
        "Launch one character, enter the game, make a small settings change, then close the client completely.",
        "No account and character changes were found. Make a small settings change in the client, then close it completely and check again.",
        "Use the username you sign in to EVE Online with. Stored only on this computer.",
        "Check this account in the EVE launcher, then add any other characters shown there.",
    ):
        assert copy in ACCOUNT_ROUTE or copy in CODE
    assert "Optional account name" not in ACCOUNT_ROUTE
    assert "account alias" not in _strip_html_comments(ACCOUNT_ROUTE).casefold()


def test_identification_uses_atomic_confirmation_and_bounded_roster():
    for method in (
        "eve_settings_identification_start",
        "eve_settings_identification_check",
        "eve_settings_identification_cancel",
        "eve_settings_identification_confirm",
        "eve_settings_set_account_name",
        "eve_settings_set_account_characters",
    ):
        assert f"WM.send('{method}'" in CODE
    assert "eve_settings_set_account_alias" not in CODE
    assert "es-account-name-save').click()" in CODE
    assert "account.account_name" in CODE
    assert "eve_settings_identification_confirm', accountId, characterId," in CODE
    assert "WM.route('evesettings')" in CODE
    route = re.search(
        r"document\.addEventListener\('wm:route'.*?\n    \}\);", CODE, re.DOTALL
    )
    assert route and "identityRouteOpen" in route.group(0)
    assert "event.detail === 'accountidentity'" in route.group(0)
    assert "if (leavingIdentity)" in route.group(0)
    assert "eve_settings_identification_cancel" in route.group(0)
    assert "ai-identify-another" in CODE and "paintIdentification('idle')" in CODE
    assert "result.status === 'invalidated'" in CODE
    assert "result.status === 'error'" in CODE
    assert "result.status === 'busy'" in CODE
    assert "result.error === 'Another Profiles operation is running.'" not in CODE
    assert "filter(function (account) { return account.account_name; }).length" in CODE
    assert "linked.length >= 3 || !add.options.length" in CODE
    assert "WM.confirm('Move character?'" in CODE
    assert "owner.display_name" in CODE and "account.display_name" in CODE


def test_watching_has_a_visible_focusable_step_heading():
    heading = re.search(r'<h2[^>]*id="ai-watching-heading"[^>]*>', ACCOUNT_ROUTE)
    assert heading and 'tabindex="-1"' in heading.group(0)
    paint = re.search(
        r"function paintIdentification\(step, message\) \{(.*?)\n  \}", CODE, re.DOTALL
    )
    assert paint
    assert "WM.el('ai-watching-step').hidden = !watching;" in paint.group(1)
    assert "step === 'watching' ? 'ai-watching-heading'" in paint.group(1)


def test_state_repaint_transitions_from_idle_to_watching_through_the_focus_path():
    render = re.search(r"function renderIdentity\(\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert render
    assert "identityStep = 'watching';" not in render.group(1)
    assert (
        "identityStep === 'idle' && state.identification_active ? 'watching' : identityStep"
        in render.group(1)
    )
    assert "paintIdentification(step, identityMessage);" in render.group(1)


def test_identification_steps_are_focused_and_have_one_primary_action():
    for ident in (
        "ai-intro-heading",
        "ai-watching-heading",
        "es-identify-candidate-heading",
        "ai-name-heading",
        "ai-roster-heading",
    ):
        assert f'id="{ident}"' in ACCOUNT_ROUTE
        assert 'tabindex="-1"' in re.search(
            rf'<h2[^>]*id="{ident}"[^>]*>', ACCOUNT_ROUTE
        ).group(0)
    assert 'id="ai-roster-count"' in ACCOUNT_ROUTE
    roster_count = re.search(r'<[^>]+id="ai-roster-count"[^>]*>', ACCOUNT_ROUTE)
    assert roster_count and 'role="status"' in roster_count.group(0)
    roster_status = re.search(r'<[^>]+id="ai-roster-status"[^>]*>', ACCOUNT_ROUTE)
    assert roster_status and 'role="status"' in roster_status.group(0)
    for ident in ("ai-roster-identified", "ai-roster-empty"):
        element = re.search(rf'<[^>]+id="{ident}"[^>]*>', ACCOUNT_ROUTE)
        assert element and 'role="status"' not in element.group(0)
    assert "}, 'ai-roster-status');" in CODE
    name_input = re.search(r'<input[^>]+id="es-account-name"[^>]*>', ACCOUNT_ROUTE)
    assert (
        name_input
        and 'aria-describedby="ai-name-hint ai-name-status"' in name_input.group(0)
    )
    for ident in ("ai-name-status", "es-manage-status"):
        element = re.search(rf'<[^>]+id="{ident}"[^>]*>', ACCOUNT_ROUTE)
        assert element and 'class="field-msg"' in element.group(0)
    assert "el.classList.toggle('err', !!error);" in CODE
    paint = re.search(
        r"function paintIdentification\(step, message\) \{(.*?)\n  \}", CODE, re.DOTALL
    )
    assert paint and ".focus()" in paint.group(1)
    block = paint.group(1)
    assert "es-identify-check').classList.toggle('acc', watching)" in block
    assert "es-identify-link').classList.toggle('acc', candidate)" in block
    assert "es-account-name-save').classList.toggle('acc', name)" in block
    assert (
        "ai-roster-add').classList.toggle('acc', roster && additionAvailable)" in block
    )
    assert (
        "ai-roster-done').classList.toggle('acc', roster && !additionAvailable)"
        in block
    )


def test_open_roster_changes_step_after_refresh_so_the_roster_heading_receives_focus():
    open_roster = re.search(
        r"function openRoster\(accountId\) \{(.*?)\n    \}", CODE, re.DOTALL
    )
    assert open_roster
    assert "identityStep = 'roster';" not in open_roster.group(1)
    assert (
        "refresh().then(function () { paintIdentification('roster');"
        in open_roster.group(1)
    )


def test_account_identity_actions_follow_the_profiles_busy_state():
    busy = re.search(r"function setBusy\(value\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert busy
    for ident in (
        "es-identify-start",
        "es-account-name-save",
        "ai-roster-add",
        "es-character-add-btn",
        "es-identity-account",
        "es-character-add",
    ):
        assert ident in busy.group(1), f"{ident} remains interactive during a mutation"
    assert re.search(
        r"WM\.el\('es-account-name'\)\.disabled = value;", busy.group(1)
    ), "the guided account-name field remains editable during a mutation"
    assert "setBusy(busy)" in CODE, (
        "an identification refusal must not clear an existing mutation's busy state"
    )
    assert "'aria-label', 'Remove '" in CODE


def test_account_management_uses_the_specified_names_and_links_label():
    assert "Manage account names and character links…" in ACCOUNT_ROUTE
    assert "Manage account names and character links…" in CODE
    assert "Close account names and character links" in CODE
    assert "Manage names and character links…" not in CODE
    assert "Close names and character links" not in CODE


def test_switching_managed_accounts_clears_the_previous_inline_error():
    render = re.search(
        r"function renderIdentityAccount\(\) \{(.*?)\n  \}", CODE, re.DOTALL
    )
    assert render
    assert "paintFieldError('es-manage-status', '');" in render.group(1)


def test_add_dropdowns_exclude_characters_linked_to_any_account():
    helper = re.search(
        r"function linkedCharacterIds\(\) \{(.*?)\n  \}", CODE, re.DOTALL
    )
    assert helper
    assert "state.accounts" in helper.group(1)
    assert "account.character_ids" in helper.group(1)

    manual = re.search(
        r"function renderIdentityAccount\(\) \{(.*?)\n  \}", CODE, re.DOTALL
    )
    roster = re.search(r"function renderRoster\(\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert manual and roster
    assert "linkedCharacterIds()" in manual.group(1)
    assert "linkedCharacterIds()" in roster.group(1)
    assert "if (claimed[character.id]) return;" in manual.group(1)
    assert "if (claimed[character.id]) return;" in roster.group(1)


def test_account_labels_never_lead_with_an_unhelpful_missing_state():
    assert "Unidentified" not in CODE
    assert "Unidentified" not in ACCOUNT_ROUTE


def test_account_targets_render_human_identity_with_secondary_number():
    target = re.search(r"function renderTargets\(\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert target
    assert "row.display_name || row.name" in target.group(1)
    assert "row.display_meta" in target.group(1)
    assert "es-target-name" in target.group(1)
    assert "es-target-meta" in target.group(1)


def test_backups_are_a_full_width_column_grid_without_nested_scrolling():
    assert 'class="card es-backups-card"' in BACKUPS_ROUTE
    assert 'id="es-backups" class="list-scroll"' not in BACKUPS_ROUTE
    grid = re.search(r"\.es-backup-grid \{([^}]*)\}", CSS)
    assert grid and "grid-template-columns" in grid.group(1)
    assert "minmax(220px, 1fr)" in grid.group(1), (
        "the target identity must own the flexible backup column"
    )
    assert re.search(
        r"#route-backups\s+\.es-backups-card\s*\{[^}]*width:\s*100%", CSS
    ), "the Backups card must use the route's available width"


def test_backup_rows_use_resolved_labels_and_reveal_history_in_batches():
    render = re.search(r"function renderBackups\(\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert render
    block = render.group(1)
    assert "item.display_name" in block and "item.display_meta" in block
    assert "filtered.slice(0, backupVisible)" in block
    assert "backupVisible += 20" in CODE
    assert "item.kind +" not in block and "item.stem" not in block


def test_backups_route_reuses_profiles_state_and_completion_owner():
    """The subroute uses the existing Profiles bridge lifecycle."""
    assert "WM.route('backups')" in CODE
    assert "event.detail === 'backups'" in CODE
    assert CODE.count("WM.handle('onEveSettingsDone'") == 1
    assert "WM.formationsDone" in CODE


def test_profiles_passes_accounts_into_the_formation_editor():
    assert "WM.openFormations(state.accounts" in CODE
    assert "WM.openFormations = function (accounts, preferredPath)" in FORMATIONS
    assert "option.textContent = account.name;" in FORMATIONS


def test_formation_account_selector_is_disabled_while_busy():
    assert "WM.setEnabled('fm-account', !state.busy" in FORMATIONS


def test_formation_tool_is_hidden_when_it_cannot_open():
    tool = re.search(r"function paintFormationsTool\(\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert tool
    body = tool.group(1)
    assert "formationsButton.hidden = !available;" in body
    markup = re.search(r'<button[^>]+id="es-formations-open"[^>]*>', BODY)
    assert markup and "hidden" in markup.group(0), (
        "the unavailable Formations tool flashes before its first state payload"
    )
    assert re.search(
        r"(?m)^#es-formations-open\[hidden\]\s*\{\s*display:\s*none;\s*\}", CSS
    ), "the Formations hidden override must be a valid standalone CSS rule"


def test_formation_tool_owns_its_availability_through_busy_repaints():
    tool = re.search(r"function paintFormationsTool\(\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert tool
    for condition in ("state.formations_available", "state.accounts.length", "!busy"):
        assert condition in tool.group(1)
    busy = re.search(r"function setBusy\(value\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert busy
    assert "paintFormationsTool();" in busy.group(1)
    assert "'es-formations-open'" not in busy.group(1), (
        "the generic busy loop must not overwrite the tool's availability"
    )


def test_formation_account_switch_guards_dirty_edits():
    assert "WM.el('fm-account').addEventListener('change'" in FORMATIONS
    switch = FORMATIONS[
        FORMATIONS.index("WM.el('fm-account').addEventListener('change'") :
    ]
    assert "state.dirty" in switch
    assert "Discard changes?" in switch
    assert "WM.el('fm-account').value = selectedAccountPath" in switch


def test_formation_switch_response_does_not_overwrite_an_edit_made_while_loading():
    load = FORMATIONS[
        FORMATIONS.index("function load(") : FORMATIONS.index("function save(")
    ]
    stale = re.search(
        r"if \(mode === 'switch' && revision !== startedAt\) \{(.*?)\n      \}",
        load,
        re.DOTALL,
    )
    assert stale, "a switch reply must consult the revision captured before its read"
    assert "state.dirty = true;" in stale.group(1)
    assert "WM.el('fm-account').value = selectedAccountPath;" in stale.group(1)
    assert "return;" in stale.group(1)


def test_formation_switch_failure_keeps_the_editor_open_but_entry_failure_ejects():
    load = FORMATIONS[
        FORMATIONS.index("function load(") : FORMATIONS.index("function save(")
    ]
    failure = load[load.index("if (!reply || !reply.ok)") :]
    switch = re.search(
        r"if \(mode === 'switch'\) \{(.*?)\n        \}", failure, re.DOTALL
    )
    assert switch, "a failed account switch needs its own failure branch"
    assert "WM.el('fm-account').value = selectedAccountPath" in switch.group(1)
    assert "WM.route('evesettings')" not in switch.group(1), (
        "a failed switch must retain the editor and its prior formations"
    )
    assert "WM.route('evesettings')" in failure[switch.end() :], (
        "the initial formation load must still return to Profiles on failure"
    )


def test_formation_account_selection_stays_in_the_supplied_option_space():
    """The API resolves a file path; the <select> holds discovered paths.

    A junction, symlink, or Windows case normalization can make those strings
    differ for the same file. The resolved reply remains the save target, but
    every select operation has to retain the requested account-list value.
    """
    assert (
        "var accountChoices = [], selectedAccountPath = '', lastSuccessfulPath = '';"
        in FORMATIONS
    )
    load = FORMATIONS[
        FORMATIONS.index("function load(") : FORMATIONS.index("function save(")
    ]
    assert "state.path = reply.path;" in load, "saves must keep the resolved file path"
    assert "selectedAccountPath = path;" in load
    assert "lastSuccessfulPath = path;" in load
    assert "renderAccounts(selectedAccountPath);" in load
    assert "lastSuccessfulPath = state.path;" not in load

    switch = FORMATIONS[
        FORMATIONS.index("WM.el('fm-account').addEventListener('change'") :
    ]
    assert "nextPath === selectedAccountPath" in switch
    assert "WM.el('fm-account').value = selectedAccountPath;" in switch

    done = FORMATIONS[FORMATIONS.index("WM.formationsDone") :]
    assert "load(selectedAccountPath, 'reload', state.selected, true);" in done


def test_failed_formation_switch_keeps_dirty_edits_saveable():
    """Discard confirmation is provisional until the replacement read works."""
    switch = FORMATIONS[
        FORMATIONS.index("WM.el('fm-account').addEventListener('change'") :
    ]
    confirmed = re.search(r"if \(yes\) \{(.*?)\n        \}", switch, re.DOTALL)
    assert confirmed, "the dirty switch confirmation no longer loads an account"
    assert "load(nextPath, 'switch');" in confirmed.group(1)
    assert "state.dirty = false;" not in confirmed.group(1), (
        "a failed replacement read must leave the visible old edits dirty and saveable"
    )


def test_backup_filter_matches_tokens_and_visible_words():
    """Filtering covers both payload terms and the labels shown in the row."""
    matcher = re.search(
        r"function backupMatches\(item, needle\) \{(.*?)\n  \}", CODE, re.DOTALL
    )
    assert matcher
    body = matcher.group(1)
    for value in (
        "display_name",
        "display_meta",
        "item.kind",
        "item.origin",
        "Automatic",
        "Manual",
    ):
        assert value in body

    render = re.search(r"function renderBackups\(\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert render
    block = render.group(1)
    assert block.index(".filter(") < block.index(".slice(0, backupVisible)")
    assert "No backups match this filter" in block
    assert "Clear filter" in BACKUPS_ROUTE


def test_backup_actions_use_an_accessible_disclosure():
    """Delete is named, keyboard-dismissible, and only one menu opens at once."""
    render = re.search(r"function renderBackups\(\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert render
    body = render.group(1)
    assert "details" in body and "summary" in body
    assert "aria-label" in body
    assert "Escape" in body
    assert ".focus()" in body
    assert "querySelectorAll('.bk-menu[open]')" in body
    assert "other !== menu" in body and "other.open = false" in body


def test_backup_filter_and_disclosures_remain_usable_during_mutations():
    """Busy blocks mutations without trapping route or archive navigation."""
    busy = re.search(r"function setBusy\(value\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert busy
    body = busy.group(1)
    for control in ("es-backups-back", "es-backup-filter", "es-backups-more"):
        assert control not in body
    assert "querySelectorAll('button')" in body
    assert "es-backup-profile').disabled" in body
    assert "es-auto-keep-apply" in body


def test_empty_backups_explain_that_copies_create_automatic_backups():
    render = re.search(r"function renderBackups\(\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert render
    assert "No backups yet. Copies create backups automatically." in render.group(1)


def test_profile_backup_button_names_the_selected_profile():
    assert "'Back up ' + profileName + ' profile'" in CODE
    assert "backupButton.disabled" in CODE


def test_profile_backup_is_the_backups_routes_primary_action():
    button = re.search(r'<button id="es-backup-profile" class="([^"]*)"', BACKUPS_ROUTE)
    assert (
        button and "btn" in button.group(1).split() and "acc" in button.group(1).split()
    )
    assert BACKUPS_ROUTE.count('class="btn acc"') == 1, (
        "Backups must retain one accent action: manual profile backup"
    )


def test_root_changes_repaint_cleared_targets_and_commit_state():
    """refresh() paints the old selection, so root changes need a second paint."""
    root = re.search(r"function chooseRoot\(method\) \{(.*?)\n    \}", CODE, re.DOTALL)
    assert root
    changed = re.search(
        r"if \(payload && payload\.root !== previousRoot\) \{(.*?)\n            \}",
        root.group(1),
        re.DOTALL,
    )
    assert changed
    body = changed.group(1)
    assert body.index("selected = {};") < body.index("renderTargets();"), (
        "clearing targets after refresh must repaint the roster and commit label"
    )


def test_successful_noncopy_completion_clears_copy_followup():
    """A later mutation replaces the global result, so Copy complete cannot linger."""
    done = re.search(
        r"WM\.handle\('onEveSettingsDone', function \(payload\) \{(.*?)\n  \}\);",
        CODE,
        re.DOTALL,
    )
    assert done
    completion = done.group(1)
    noncopy = re.search(
        r"else if \(payload\.ok\) \{(.*?)\n    \}", completion, re.DOTALL
    )
    assert noncopy and "clearCopyFollowup();" in noncopy.group(1), (
        "successful non-copy completions must replace stale copy feedback"
    )


def test_formation_commit_keeps_the_eve_closed_requirement_next_to_save():
    commit = re.search(r'<div class="row" id="fm-commit">(.*?)</div>', HTML, re.DOTALL)
    assert commit and "Saving needs every EVE client closed." in commit.group(1)


def test_retention_is_explicit_and_does_not_add_a_second_accent():
    assert 'id="es-auto-keep"' in BACKUPS_ROUTE
    assert 'id="es-auto-keep-apply" class="btn"' in BACKUPS_ROUTE
    assert "eve_settings_set_auto_keep" in CODE
    assert "event.key === 'Enter'" in CODE
    assert BODY.count('class="btn acc"') == 1
    assert ACCOUNT_ROUTE.count('class="btn acc"') == 1


# ---- account identity: wide-width composition ---------------------------


def test_account_identity_shell_centers_at_wide_widths():
    """.account-identity-shell kept its 620px measure but sat flush against
    the route's left edge at every width past that measure -- the same
    narrow-upper-left read the copy commit region had. `.route.active` is
    `display: flex` (row direction, DESIGN.md `.route`/`.route.active`), so
    an auto inline margin on this flex item is honoured by the flexbox spec
    (auto margins on a flex item absorb the row's free space) and centres a
    fixed-width item exactly the way a block box would.
    """
    rule = re.search(r"\.account-identity-shell \{([^}]*)\}", CSS)
    assert rule, ".account-identity-shell has no rule"
    assert "max-width: 620px" in rule.group(1), "the workflow's own measure must stay"
    assert "margin-inline: auto" in rule.group(1), (
        "the shell must centre once the route is wider than its own measure"
    )


def test_manual_identity_management_is_a_labelled_subordinate_group():
    """Manage account names and character links... stays a linkbtn
    disclosure right after the guided flow, but is now a named, subordinate
    group -- visibly and programmatically -- rather than trailing the
    roster step with nothing marking the boundary. Exact copy is untouched:
    only the group wrapping and its own label are new.
    """
    open_tag = re.search(r'<div class="es-manual-identity"([^>]*)>', ACCOUNT_ROUTE)
    assert open_tag, "the manual management path is no longer its own group"
    attrs = open_tag.group(1)
    assert 'role="group"' in attrs
    assert 'aria-labelledby="es-manual-identity-label"' in attrs

    label = re.search(
        r'<p id="es-manual-identity-label"[^>]*>([^<]*)</p>', ACCOUNT_ROUTE
    )
    assert label and label.group(1).strip(), "the group has no visible label"

    wrapper_at = ACCOUNT_ROUTE.index('class="es-manual-identity"')
    toggle_at = ACCOUNT_ROUTE.index('id="es-manage-toggle"')
    panel_at = ACCOUNT_ROUTE.index('id="es-identity-panel"')
    roster_done_at = ACCOUNT_ROUTE.index('id="ai-roster-done"')
    assert roster_done_at < wrapper_at < toggle_at < panel_at, (
        "the manual path must stay close to, and after, the primary flow"
    )

    # Exact copy is pinned elsewhere (test_account_management_uses_the_
    # specified_names_and_links_label); this only guards that wrapping the
    # existing controls did not touch it.
    assert (
        'id="es-manage-toggle" class="linkbtn ai-manage-toggle" type="button">'
        "Manage account names and character links\u2026</button>" in ACCOUNT_ROUTE
    )

    rule = re.search(r"\.es-manual-identity \{([^}]*)\}", CSS)
    assert rule, ".es-manual-identity has no rule"
    assert "border-top" in rule.group(1), (
        "the group boundary must be visible, not only programmatic"
    )


# ---- undefined --border custom property ----------------------------------


def test_profiles_boundaries_use_the_defined_panel_border_token():
    """`--border` is never declared in `:root` -- only `--panel-border` is
    (style.css:73) -- so every `var(--border)` on this page silently
    computes invalid and the declaration is dropped, leaving the boundary
    unstyled. Six rules on this route carried it: the Backups retention
    disclosure and archive row, the sticky commit-context bar, and the
    Account Identity manual-management separator, identity boundary and
    linked-character row. Each must use the same `--panel-border` token
    every working boundary on the page already uses (e.g. .es-backup-head,
    style.css:3163), and none may still reference the undefined name.
    """
    selectors = [
        "#es-retention",
        ".es-backup-row",
        ".es-commit-context",
        ".es-identity",
        ".es-manual-identity",
        ".es-linked-character",
    ]
    for selector in selectors:
        rule = _brace_block(CSS, selector + " {")
        assert "var(--panel-border)" in rule, (
            f"{selector} must use the defined --panel-border token for its border"
        )
        assert "var(--border)" not in rule, (
            f"{selector} still references the undefined --border custom property"
        )

    assert "var(--border)" not in CSS, (
        "no rule on the page may reference the undefined --border custom "
        "property; every boundary must use --panel-border instead"
    )
