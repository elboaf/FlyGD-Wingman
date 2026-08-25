"""The Profiles route, checked lexically.

Same approach and same reason as test_page_conventions.py: nothing in this
suite renders index.html or executes web/*.js, so what this screen depends
on is enforced by reading its source. These are the five facts the UI
critique's Profiles findings turned into code, each of which would fail
silently rather than loudly if it were undone.

They are mechanical. Whether the collapsed card is the right shape is a
question for docs/smoke-checklist.md; whether the pill still exists at all
after someone edits the card is a question for here.
"""

import pathlib
import re

WEB = pathlib.Path(__file__).resolve().parents[1] / "obs_youtube_uploader" / "web"
HTML = (WEB / "index.html").read_text(encoding="utf-8")
CSS = (WEB / "style.css").read_text(encoding="utf-8")
JS = (WEB / "evesettings.js").read_text(encoding="utf-8")

# The route's own markup. Every rule below is about this block and would
# otherwise match a sibling screen that happens to use the same class.
ROUTE = re.search(
    r'<div class="route" id="route-evesettings">.*?\n  </div>', HTML, re.DOTALL
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
    note = re.search(
        r"WM\.el\('es-backup-note'\)\.textContent =(.*?);", CODE, re.DOTALL
    )
    assert note, "the Backups card no longer explains what it prunes"
    assert "state.auto_keep" in note.group(1), (
        "the keep depth must come off the payload: " + note.group(1)
    )
    assert not re.search(r"\b\d+\b", note.group(1).replace("auto_keep", "")), (
        "a count is typed into the backup note: " + note.group(1)
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
    assert row.group(1).strip(), "the mode switch's label column is empty again"


# ---- the settings-folder path joins the rest of the app ----------------


def test_both_folder_paths_are_monospace_fields_on_the_shared_column():
    """It was the one path in the app in the proportional face, the one row
    whose first element was off the shared label column, and it had no
    truncation -- so a long root pushed the Choose button toward the right
    edge of a card already narrower than 620px at the window floor.
    span.field's ellipsis is what the row was missing.
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
        assert "field" in classes and "mono" in classes, (
            f"#{ident} must be a span.field.mono: {row.group(1)}"
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
    assert re.search(r"<h2>Settings folder<span id=\"es-eve-state\"", BODY), (
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
        r"if \(event\.detail !== 'evesettings'\) return;(.*?)\}\);", CODE, re.DOTALL
    )
    assert route and "expanded = false" in route.group(1), (
        "entering the route no longer re-collapses the folder card"
    )
