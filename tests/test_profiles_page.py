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
    assert root and "var previous = contextOf(state);" in root.group(1)
    assert "clearCopyFollowup();" not in root.group(1).split("WM.send", 1)[0]
    assert "payload && contextChanged(previous, payload)" in root.group(1)
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
    """Backups and Formations stay grouped with the selected profile context."""
    tools = re.findall(
        r'<div class="es-profile-tools"([^>]*)>(.*?)</div>', BODY, re.DOTALL
    )
    assert len(tools) == 1, "profile tools must remain one sibling group"
    attrs, content = tools[0]
    assert 'role="group"' in attrs
    assert 'aria-label="Tools for the selected EVE profile"' in attrs
    assert 'id="es-backups-open"' in content
    assert 'id="es-formations-open"' in content

    context_end = BODY.index("</section>", BODY.index("es-context-card"))
    tools_at = BODY.index('class="es-profile-tools"')
    copy_at = BODY.index("<h2>Copy EVE settings</h2>")
    assert context_end < tools_at < copy_at
    assert "card" not in attrs.split()


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


def test_the_collapsed_summary_names_the_server():
    """R5, revised for round 7. `Tranquility - Default` sat beside a
    labelled `Folder`, unlabelled, and this row's own words go in the TEXT
    rather than a second `.lab` -- `.settings .row > .lab` is width:100%, so
    a second label here would stack and break the row into three lines.

    The profile HALF of R5's finding moved rather than disappeared: Profile
    is now the primary, always-visible row's own labelled control (see
    `test_profile_is_the_primary_context_control`), so naming it a second
    time in the row that collapses away would restate what the row above
    never hides.
    """
    assert re.search(r"setLabel\(nameOf\(state\.servers", CODE), (
        "the collapsed summary prints the server name bare again"
    )
    assert "setLabel(nameOf(state.profiles" not in CODE, (
        "the collapsed summary names the profile again, restating the "
        "always-visible primary row's own control"
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
        r"if \(payload && contextChanged\(previous, payload\)\) \{(.*?)\n            \}",
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


# ---- round 7: Profiles is profile-first, with an inline New/Replace ----


def profiles_context_body() -> str:
    """The `.es-context-card` section alone: Profile, the New/Replace
    disclosure, and the collapsible folder/server setup all live here, and
    the ordering between them is what "profile-first" is actually about.
    Scoped narrower than BODY so a control that migrated to a sibling card
    could not still satisfy an ordering assertion aimed at this one.
    """
    start = BODY.index('<section class="card es-context-card">')
    end = BODY.index("</section>", start) + len("</section>")
    return BODY[start:end]


def profile_copy_panel_body() -> str:
    """The disclosure alone, bounded by the next sibling row rather than by
    counting braces: BODY has already had its HTML comments stripped, so the
    next literal landmark after the panel is the folder card's own summary
    row.
    """
    start = BODY.index('<div id="es-profile-copy-panel"')
    end = BODY.index('<div class="row" id="es-folder-summary"')
    return BODY[start:end]


def test_profile_is_the_primary_context_control():
    """Profile decides what a copy reads and what a copy targets, which is
    the reason the screen exists -- so it renders ahead of the folder/server
    setup that collapses away after the first visit, not folded inside it.
    The opener beside it is a plain .btn: the disclosure it opens is not the
    route's one irreversible action, .es-copy already is.
    """
    context = profiles_context_body()
    assert context.index('id="es-profile"') < context.index('id="es-folder-summary"')
    assert 'id="es-profile-copy-open" class="btn"' in context
    assert 'id="es-profile-copy-open" class="btn acc"' not in context


def test_profile_copy_modes_use_shared_radio_markup():
    """The New/Replace switch is a .radio/.ring pair like every other radio
    on the route, not a bare input rendering as a white Win32 dot.
    """
    assert re.search(
        r'name="es-profile-copy-mode" value="new" checked><span class="ring"></span>',
        BODY,
    )
    assert re.search(
        r'name="es-profile-copy-mode" value="replace"><span class="ring"></span>',
        BODY,
    )


def test_profile_copy_name_and_destination_have_associated_labels():
    assert re.search(r'<label class="lab" for="es-profile-copy-name">', BODY)
    assert 'id="es-profile-copy-name"' in BODY
    assert re.search(r'<label class="lab" for="es-profile-copy-destination">', BODY)
    assert 'id="es-profile-copy-destination"' in BODY


def test_profile_copy_fields_are_described_by_the_panels_status_line():
    """Both fields point at the one status line that carries Python's
    refusal about a name or a destination and the panel's own reason for a
    disabled submit. Without the association the message is announced once
    by role="status" and is then unreachable: a screen-reader user tabbing
    back to the field hears the label alone.
    """
    for field in ("es-profile-copy-name", "es-profile-copy-destination"):
        element = re.search(r'<(?:input|select) id="' + field + r'"[^>]*>', BODY)
        assert element, field
        assert 'aria-describedby="es-profile-copy-status"' in element.group(0), field
    assert 'id="es-profile-copy-status"' in BODY


def test_the_secondary_detail_no_longer_offers_a_profile_select():
    """Profile moved to the always-visible primary row; a second copy of it
    left behind in the collapsible detail would be two controls for the
    same choice, one of them invisible on every later visit.
    """
    detail = BODY[BODY.index('id="es-folder-detail"') : BODY.index('id="es-warning"')]
    assert 'id="es-profile"' not in detail
    assert 'id="es-server"' in detail


def test_folder_edit_names_both_things_it_changes():
    """Renamed from `Change…`: the row it sits on now also carries the
    server name (R5), so the action must say what it reopens.
    """
    summary = BODY[BODY.index("es-folder-summary") : BODY.index("es-folder-detail")]
    assert (
        'id="es-folder-edit" class="btn">Change folder or server\u2026</button>'
        in summary
    )


def test_the_disclosure_carries_no_second_accent_button():
    """One .btn.acc on the whole route (test_profiles_keeps_one_existing_
    primary_action), and it is .es-copy. Creating or replacing a profile is
    reversible through Backups' automatic archive, unlike overwriting a
    live roster, so its own submit stays a plain .btn.
    """
    panel = profile_copy_panel_body()
    assert 'class="btn acc"' not in panel
    assert 'id="es-profile-copy-submit" class="btn"' in panel
    assert 'id="es-profile-copy-cancel" class="btn"' in panel


def test_profile_copy_hidden_overrides_exist_for_every_display_setting_selector():
    """`.es-profile-copy` and the two field rows each set their own display,
    which beats the UA's `[hidden] { display: none }` regardless of
    specificity -- DESIGN.md's named trap, and test_page_conventions.py's
    repo-wide sweep for it is what caught the first draft of this rule
    keyed to the wrong (id) selector.
    """
    assert re.search(
        r"\.es-profile-copy\[hidden\],\s*"
        r"#es-profile-copy-new-fields\[hidden\],\s*"
        r"#es-profile-copy-replace-fields\[hidden\]\s*\{\s*display:\s*none;\s*\}",
        CSS,
    )


def test_profile_copy_state_carries_exactly_seven_fields():
    match = re.search(r"var profileCopy = \{(.*?)\n  \};", CODE, re.DOTALL)
    assert match, "the module-level profileCopy state is gone"
    fields = set(re.findall(r"(\w+):", match.group(1)))
    assert fields == {
        "open",
        "source",
        "mode",
        "name",
        "destination",
        "error",
        "destinationInvalid",
    }


def test_open_profile_copy_freezes_the_source_from_state_profile():
    """The source is read once, at open, not re-read at submit -- so a
    root/server/profile change accepted while the disclosure sits open
    cannot silently retarget an already-open request.
    """
    fn = re.search(r"function openProfileCopy\(\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert fn
    assert "source: state.profile" in fn.group(1)


def test_replace_options_exclude_the_frozen_source():
    fn = re.search(r"function replaceOptions\(\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert fn
    assert "profile.path !== profileCopy.source" in fn.group(1)


def test_replace_destination_renders_a_disabled_empty_option_when_none_exist():
    render = re.search(r"function renderProfileCopy\(\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert render
    body = render.group(1)
    assert "placeholder.disabled = true;" in body
    assert "No other profiles" in body


def test_replace_with_no_destination_disables_submit_and_names_the_reason():
    """Submitting Replace with nothing to replace sends an empty destination,
    which Python refuses as "That destination is not on the selected server"
    -- a race, not the truth that this server holds only the one profile.
    Whether an option list is empty is the page's own fact, so the page says
    it before the request and disables the button rather than after.
    """
    render = re.search(r"function renderProfileCopy\(\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert render
    body = render.group(1)
    assert "if (profileCopy.mode === 'replace') {" in body
    assert "if (!options.length) {" in body
    assert "There is no other profile on this server to replace. " in body
    assert re.search(
        r"WM\.setEnabled\('es-profile-copy-submit',\s*"
        r"!busy && !!profileCopy\.source && !blocked\);",
        body,
    )
    # The blocking state owns the status line while it lasts, and is not an
    # error: nothing failed, the panel is naming what it still needs.
    assert "status.classList.remove('err');" in body
    assert "paintFieldError('es-profile-copy-status', profileCopy.error);" in body


def test_a_vanished_replace_destination_asks_for_a_fresh_choice():
    """A refresh that removes the chosen destination must not leave the
    browser's own default -- the first remaining profile -- sitting in the
    control as though the user had picked it, for the one action on this
    screen that overwrites a whole profile.
    """
    render = re.search(r"function renderProfileCopy\(\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert render
    body = render.group(1)
    assert re.search(
        r"if \(previous && !options\.filter\(function \(profile\) \{\s*"
        r"return profile\.path === previous;\s*\}\)\.length\) \{\s*"
        r"profileCopy\.destinationInvalid = true;\s*\}",
        body,
    )
    assert "var vanished = profileCopy.destinationInvalid;" in body
    assert "if (vanished) {" in body
    assert "repick.value = '';" in body
    assert "repick.disabled = true;" in body
    assert "repick.selected = true;" in body
    assert "repick.textContent = 'Choose a profile';" in body
    assert "blocked = 'The profile you chose is no longer there. Choose another.';" in (
        body
    )
    # Choosing a real destination has to repaint, or the submit this state
    # disabled stays dead until some unrelated repaint happens by -- and it
    # must be the one thing that clears the latched invalid flag back.
    change_handler = re.search(
        r"WM\.el\('es-profile-copy-destination'\)\.addEventListener\("
        r"'change', function \(\) \{(.*?)\n\s*\}\);",
        CODE,
        re.DOTALL,
    )
    assert change_handler
    assert "profileCopy.destinationInvalid = false;" in change_handler.group(1)
    assert "renderProfileCopy();" in change_handler.group(1)


def test_a_vanished_destination_survives_a_second_ordinary_repaint():
    """The prior fix computed `vanished` fresh on every call from the
    destination select's OWN live `.value` -- but the very same call had
    just replaced that value with the disabled placeholder's `''`. A
    second, unrelated repaint (a poll, a busy toggle, any of the many
    other triggers that call renderProfileCopy() -- setBusy(), refresh(),
    the mode radios) reads that `''` back, sees no previous value to have
    vanished, and lets the browser's own default -- the first remaining
    profile -- silently reappear as though re-picked, submit re-enabled
    under it with nobody having chosen anything.

    So the invalidated state cannot live only in what the DOM's `.value`
    happens to read at the top of this call; it has to survive on
    `profileCopy` itself across repaints, and only a genuine user pick --
    the destination select's OWN 'change' event, which can only fire for
    one of the enabled real options, never the disabled placeholder --
    may clear it back.
    """
    render = re.search(r"function renderProfileCopy\(\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert render
    body = render.group(1)
    # Set when a chosen destination first vanishes...
    assert re.search(r"profileCopy\.destinationInvalid = true;", body)
    # ...and READ from profileCopy on every call, not recomputed solely from
    # the select's own live value (which this same function just wrote).
    assert re.search(r"var vanished = profileCopy\.destinationInvalid\b", body)

    # Only the destination select's own change handler may clear it, and it
    # must do so before repainting -- not the generic renderProfileCopy the
    # mode radios and every other trigger on this route call directly.
    change_handler = re.search(
        r"WM\.el\('es-profile-copy-destination'\)\s*"
        r"\.addEventListener\('change', function \(\) \{(.*?)\n\s*\}\);",
        CODE,
        re.DOTALL,
    )
    assert change_handler, "the destination select needs its own change handler"
    handler_body = change_handler.group(1)
    assert "profileCopy.destinationInvalid = false;" in handler_body
    assert "renderProfileCopy();" in handler_body


def test_send_profile_copy_examines_accepted_not_truthiness():
    """mutate() treats any returned object as truthy, which is wrong for an
    endpoint that can return `{accepted: false, error: ...}` -- a refusal
    object is itself truthy, and mutate() would read it as "started".
    """
    fn = re.search(r"function sendProfileCopy\(\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert fn
    body = fn.group(1)
    assert "if (busy || !profileCopy.source) return;" in body
    assert "if (result && result.accepted) return;" in body
    assert "mutate(" not in body


def test_immediate_refusal_writes_the_error_and_clears_busy():
    fn = re.search(r"function sendProfileCopy\(\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert fn
    refusal = fn.group(1).split(".then(function (result) {", 1)[1]
    assert "pendingMutation = '';" in refusal
    assert "profileCopy.error = result && result.error" in refusal
    assert "setBusy(false);" in refusal
    assert "renderProfileCopy();" in refusal


def test_completion_closes_the_disclosure_on_published_regardless_of_selection_persisted():
    """A created profile whose selection could not be saved is still ok:True
    and published:True from Python -- the file exists and the dropdown
    offers it, only the remembered selection failed -- and the warning
    alert already carries \"Select it from Profile\" for that half. Closing
    must key on `published` alone, or that case would leave the disclosure
    open over a request that already succeeded.
    """
    done = re.search(
        r"WM\.handle\('onEveSettingsDone', function \(payload\) \{(.*?)\n  \}\);",
        CODE,
        re.DOTALL,
    )
    assert done
    branch = re.search(
        r"if \(completedMutation === 'eve_settings_copy_profile'\) \{(.*?)\n    \}",
        done.group(1),
        re.DOTALL,
    )
    assert branch
    body = branch.group(1)
    assert "if (payload.published) resetProfileCopy();" in body
    assert "selection_persisted" not in body


def test_failed_publication_retains_the_disclosure_state():
    """A refused or failed copy must not silently drop the mode, name or
    destination the user entered -- only the error changes, and the panel
    stays open so the message lands beside the fields it is about.
    """
    done = re.search(
        r"WM\.handle\('onEveSettingsDone', function \(payload\) \{(.*?)\n  \}\);",
        CODE,
        re.DOTALL,
    )
    assert done
    branch = re.search(
        r"if \(completedMutation === 'eve_settings_copy_profile'\) \{(.*?)\n    \}",
        done.group(1),
        re.DOTALL,
    )
    assert branch
    body = branch.group(1)
    failure = body.split("else", 1)[1]
    assert "profileCopy.error = payload.error || profileCopy.error;" in failure
    assert "resetProfileCopy()" not in failure


def test_root_change_resets_profile_copy_only_when_the_root_actually_changed():
    root = re.search(r"function chooseRoot\(method\) \{(.*?)\n    \}", CODE, re.DOTALL)
    assert root
    before, _, after = root.group(1).partition(
        "if (payload && contextChanged(previous, payload))"
    )
    assert "resetProfileCopy();" not in before, (
        "a no-op or refused root change must not close the disclosure"
    )
    changed = re.search(r"\{(.*?)\n            \}", after, re.DOTALL)
    assert changed and "resetProfileCopy();" in changed.group(1)


def test_chooseroot_compares_the_full_persisted_context_not_only_root():
    """Fix round 1. A folder pick can silently change the SERVER or the
    PROFILE too -- discover()'s own fallback when the prior selection no
    longer resolves on the newly picked tree -- so a same-root pick that
    moved the profile out from under an open disclosure or a ticked roster
    used to go unnoticed: the old condition compared `payload.root` alone.
    """
    root = re.search(r"function chooseRoot\(method\) \{(.*?)\n    \}", CODE, re.DOTALL)
    assert root
    assert "var previous = contextOf(state);" in root.group(1), (
        "chooseRoot must capture the full context before the pick, not root alone"
    )
    assert "payload.root !== previousRoot" not in root.group(1), (
        "chooseRoot still compares root alone; a same-root server/profile "
        "fallback would go unnoticed"
    )


def test_context_comparison_covers_root_server_and_profile():
    fn = re.search(
        r"function contextChanged\(before, after\) \{(.*?)\n  \}", CODE, re.DOTALL
    )
    assert fn, "the full-context comparison helper is gone"
    body = fn.group(1)
    assert "before.root !== next.root" in body
    assert "before.server !== next.server" in body
    assert "before.profile !== next.profile" in body


def test_selection_change_resets_profile_copy_only_when_accepted():
    handler = re.search(
        r"\['es-server', 'es-profile'\]\.forEach.*?"
        r"addEventListener\('change', function \(\) \{(.*?)\n      \}\);",
        CODE,
        re.DOTALL,
    )
    assert handler
    then = re.search(
        r"\.then\(function \(accepted\) \{(.*?)\n\s*\}\);", handler.group(1), re.DOTALL
    )
    assert then
    accepted_branch = re.search(
        r"if \(accepted\) \{(.*?)\n\s*\}", then.group(1), re.DOTALL
    )
    assert accepted_branch and "resetProfileCopy();" in accepted_branch.group(1)


def test_refused_selection_change_retains_selection_and_disclosure():
    """Fix round 1. `selected = {}` and `clearCopyFollowup()` used to run
    the instant the control changed, before `eve_settings_select` had even
    been asked -- so a refused or no-op selection change silently dropped
    the ticked roster and the open New/Replace disclosure anyway. Every
    clearing statement must sit behind the accepted branch instead.
    """
    handler = re.search(
        r"\['es-server', 'es-profile'\]\.forEach.*?"
        r"addEventListener\('change', function \(\) \{(.*?)\n      \}\);",
        CODE,
        re.DOTALL,
    )
    assert handler
    body = handler.group(1)
    before_send = body.split("WM.send", 1)[0]
    assert "selected = {}" not in before_send, (
        "the roster selection is cleared before Python answers"
    )
    assert "clearCopyFollowup();" not in before_send, (
        "the copy follow-up is cleared before Python answers"
    )
    assert "resetProfileCopy();" not in before_send, (
        "the disclosure is reset before Python answers"
    )

    then = re.search(
        r"\.then\(function \(accepted\) \{(.*?)\n\s*\}\);", body, re.DOTALL
    )
    assert then
    accepted_branch = re.search(
        r"if \(accepted\) \{(.*?)\n\s*\}", then.group(1), re.DOTALL
    )
    assert accepted_branch, "the clearing statements must be gated on `accepted`"
    branch_body = accepted_branch.group(1)
    assert "clearCopyFollowup();" in branch_body
    assert "selected = {};" in branch_body
    assert "resetProfileCopy();" in branch_body


def test_profile_copy_controls_join_busy_state_while_navigation_stays_enabled():
    """setBusy is the shared owner of "can this act right now" for the whole
    route (paintCommit, paintFormationsTool); the disclosure and its opener
    follow the same rule rather than a hand-rolled parallel one. Route
    navigation is never touched here at all -- #nav-* ids belong to app.js,
    not this file -- so leaving the route mid-mutation was never blocked by
    this function and stays that way.
    """
    busy = re.search(r"function setBusy\(value\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert busy
    body = busy.group(1)
    assert "renderProfileCopy();" in body
    assert "paintProfileCopyTool();" in body
    assert "nav-" not in body


def test_profile_copy_tool_is_unavailable_without_a_selected_profile():
    fn = re.search(r"function paintProfileCopyTool\(\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert fn
    assert "state.profile" in fn.group(1)
    assert "WM.setEnabled('es-profile-copy-open'" in fn.group(1)
