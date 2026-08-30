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
    commit_at = HTML.index('id="es-commit"')
    note_at = HTML.index('id="es-copy-backup-note"')
    backups_at = HTML.index("<h2>Backups</h2>")
    assert commit_at < note_at < backups_at, (
        "the note must sit between the commit row and the Backups card: "
        "above the button it reassures, and not inside the card that "
        "already carries the full sentence"
    )
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
    assert 'id="es-backups" class="list-scroll"' not in BODY


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
    assert (
        "Unchecked groups keep each target\u2019s own settings. Everything else is copied."
        in copy_body
    )


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


def test_the_retention_note_follows_the_action_it_qualifies():
    """R2. A retention policy opened the Backups card, ahead of the one
    control in it. The note is not cut -- it is the promise that makes the
    copy card above it safe -- but a card whose point is an action may not
    lead with the policy that governs it.
    """
    card = re.search(r"<h2>Backups</h2>(.*?)</section>", BODY, re.DOTALL)
    assert card, "the Backups card no longer opens with its own heading"
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


def test_account_identity_route_is_a_chromeless_profiles_subscreen():
    assert "accountidentity: 'route-accountidentity'" in APP
    assert 'data-route="accountidentity"' not in HTML
    chromeless = re.search(r"WM\.CHROMELESS_ROUTES = \[([^]]+)\]", APP)
    eve_routes = re.search(r"WM\.EVE_ROUTES = \[([^]]+)\]", APP)
    assert chromeless and "'accountidentity'" in chromeless.group(1)
    assert eve_routes and "'accountidentity'" in eve_routes.group(1)
    assert "name === 'accountidentity'" in APP


def test_identification_uses_explicit_request_response_methods_and_cancels_on_leave():
    for method in (
        "eve_settings_identification_start",
        "eve_settings_identification_check",
        "eve_settings_identification_cancel",
        "eve_settings_set_account_alias",
        "eve_settings_set_account_characters",
    ):
        assert method in CODE
    route = re.search(
        r"document\.addEventListener\('wm:route'.*?\n    \}\);", CODE, re.DOTALL
    )
    assert route and "identityRouteOpen" in route.group(0)
    assert "event.detail === 'accountidentity'" in route.group(0)
    assert "if (leavingIdentity)" in route.group(0)
    assert "eve_settings_identification_cancel" in route.group(0)


def test_identification_completion_replaces_setup_with_the_way_back():
    paint = re.search(
        r"function paintIdentification\(status, message\) \{(.*?)\n  \}",
        CODE,
        re.DOTALL,
    )
    assert paint
    assert "ai-intro').hidden = complete" in paint.group(1)
    assert "ai-complete').hidden = !complete" in paint.group(1)
    assert "ai-complete-back').classList.toggle('acc', complete)" in paint.group(1)
    assert "linked to " in CODE


def test_account_identity_actions_follow_the_profiles_busy_state():
    busy = re.search(r"function setBusy\(value\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert busy
    for ident in (
        "es-identify-start",
        "es-alias-apply",
        "es-character-add-btn",
        "es-identity-account",
        "es-account-alias",
        "es-character-add",
    ):
        assert ident in busy.group(1), f"{ident} remains interactive during a mutation"
    assert "setBusy(busy)" in CODE, (
        "an identification refusal must not clear an existing mutation's busy state"
    )
    assert "'aria-label', 'Remove '" in CODE


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
    assert 'class="card es-backups-card"' in BODY
    assert 'id="es-backups" class="list-scroll"' not in BODY
    grid = re.search(r"\.es-backup-grid \{([^}]*)\}", CSS)
    assert grid and "grid-template-columns" in grid.group(1)
    assert "minmax(220px, 1fr)" in grid.group(1), (
        "the target identity must own the flexible backup column"
    )
    assert re.search(r"\.es-backups-card\s*\{\s*max-width:\s*none", CSS), (
        "the Backups card must use the route's available width"
    )


def test_backup_rows_use_resolved_labels_and_reveal_history_in_batches():
    render = re.search(r"function renderBackups\(\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert render
    block = render.group(1)
    assert "item.display_name" in block and "item.display_meta" in block
    assert "backups.slice(0, backupVisible)" in block
    assert "backupVisible += 20" in CODE
    assert "item.kind +" not in block and "item.stem" not in block


def test_profile_backup_button_names_the_selected_profile():
    assert "'Back up ' + profileName + ' profile'" in CODE
    assert "backupButton.disabled" in CODE


def test_retention_is_explicit_and_does_not_add_a_second_accent():
    assert 'id="es-auto-keep"' in BODY
    assert 'id="es-auto-keep-apply" class="btn"' in BODY
    assert "eve_settings_set_auto_keep" in CODE
    assert "event.key === 'Enter'" in CODE
    assert BODY.count('class="btn acc"') == 1
    assert ACCOUNT_ROUTE.count('class="btn acc"') == 1
