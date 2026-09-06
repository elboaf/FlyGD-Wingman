"""The Settings route's rail and card headings, checked lexically.

Same rationale as tests/test_page_conventions.py, which this file
deliberately does not grow into: those rules are page-wide, these are one
route's. Nothing in the suite renders index.html, so both read its source.

Every rule below is here because it was broken and shipped:

- The rail's first item was General, whose entire content is the checkbox
  that turns most of the product off, while the landing section was
  Account -- so item one was the one place the rail never opened on.
- Two rail items repeated themselves verbatim as their own first card
  heading, which DESIGN.md forbids in as many words, and a third did it
  with a parenthetical bolted on.
- Two sections one rail item apart both headed a card "Keybinds", for two
  independent keybind systems that can take each other's keys --
  previews.js's bookmarkClash exists for nothing else.
"""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
WEB = ROOT / "wingman" / "web"
HTML = (WEB / "index.html").read_text(encoding="utf-8")


def test_design_records_the_global_badge_fetch_exception():
    design = (ROOT / "DESIGN.md").read_text(encoding="utf-8")
    assert "update availability" in design.lower()
    assert "after the page is ready" in design.lower()


def _settings_route() -> str:
    """The #route-settings block, comments stripped.

    Comments first: the rail carries a long one naming General and several
    sections, and a naive capture reads those as markup.
    """
    body = re.sub(r"<!--.*?-->", "", HTML, flags=re.DOTALL)
    start = body.index('<div class="route" id="route-settings">')
    end = body.index('<div class="route" id="route-evesettings">')
    return body[start:end]


def _rail() -> list[tuple[str, str]]:
    """(section name, visible label) in rail order."""
    return re.findall(
        r'<button class="rail-item[^"]*" data-section="([\w-]+)">([^<]+)</button>',
        _settings_route(),
    )


def _panes() -> list[tuple[str, str]]:
    """(section name, markup) in document order."""
    route = _settings_route()
    marks = list(
        re.finditer(r'<div class="settings[^"]*" id="section-([\w-]+)">', route)
    )
    out = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(route)
        out.append((m.group(1), route[m.start() : end]))
    return out


def _headings(pane: str) -> list[str]:
    return [h.strip() for h in re.findall(r"<h2>([^<]+)</h2>", pane)]


def test_the_rail_and_the_panes_are_in_the_same_order():
    """Only one pane renders at a time, so their order is invisible and can
    drift from the rail's for free. It is still the order a reader of this
    file navigates by, and a rail item whose pane is nowhere near it is how
    the wrong card gets edited."""
    expected = [
        "uploading",
        "characters",
        "bookmarks",
        "previews",
        "alerts",
        "general",
    ]
    assert [name for name, _ in _rail()] == expected
    assert [name for name, _ in _panes()] == expected


def test_general_is_the_last_rail_item():
    """Its whole content is the switch that hides the EVE-only Settings
    sections (app.js's EVE_SECTIONS), so it sits under the entries it
    removes and the rail loses its tail rather than a hole in its middle.
    It is also visited once, probably never, and was first.

    Paired with test_page_conventions.py's landing-section rules: that one
    pins where Settings opens, this one pins what the rail reads as."""
    assert [name for name, _ in _rail()][-1] == "general"


def test_no_section_repeats_its_rail_label_as_its_first_card_heading():
    """DESIGN.md, in as many words: "A screen may not repeat its own tab
    name as its first card heading." The rail item is the tab here.

    A trailing parenthetical does not buy an exemption -- "Discord" under
    "Discord" still leads with the word the user just clicked, and the
    heading's job is to say what the card does."""
    labels = dict(_rail())
    for name, pane in _panes():
        headings = _headings(pane)
        assert headings, f"section {name} has no card heading"
        first = re.sub(r"\s*\([^)]*\)\s*$", "", headings[0]).strip()
        assert first.casefold() != labels[name].casefold(), (
            f"section {name} heads its first card with its own rail label "
            f"{labels[name]!r}"
        )


def test_no_two_settings_cards_share_a_heading():
    """Bookmarks and Previews each held a card headed "Keybinds". They
    configure two independent keybind systems whose keys collide -- one
    global, one only inside EVE -- and nothing on either screen said the
    other existed. Two identical headings on one route are either a
    collision like that one or a copy-paste."""
    seen: dict[str, str] = {}
    for name, pane in _panes():
        for heading in _headings(pane):
            key = heading.casefold()
            assert key not in seen, (
                f"{heading!r} heads a card in both {seen[key]} and {name}"
            )
            seen[key] = name


# ---- state that must not be retyped into the page ----------------------


def test_the_page_never_types_a_version_number():
    """M2's whole point. `__version__` reaches the page on the settings
    payload and is written into the titlebar and into ABOUT by JS; a third
    hand-typed copy in the markup is the drift DESIGN.md's "State that must
    not be retyped" exists to prevent, and the copy a user reads is the one
    that matters when they report a bug.

    pyproject.toml already derives its version from `__version__` rather
    than carrying one, and tests/test_packaging_version.py asserts that
    chain. This is the same rule for the surface the user actually sees.
    """
    body = re.sub(r"<!--.*?-->", "", HTML, flags=re.DOTALL)
    literals = re.findall(r"\b\d+\.\d+\.\d+\b", body)
    assert not literals, (
        "index.html types a version-shaped literal: "
        f"{literals!r} -- push it from __version__ instead"
    )


def test_the_previews_inert_note_is_not_typed_into_the_page():
    """Walkthrough Settings 1. "Previews are off, so every keybind below is
    unregistered..." is ui/copy.py's INERT_NOTES["previews_off"], shipped
    on the settings payload. It was ALSO typed into index.html, which is
    one sentence in two files with nothing holding them in step -- and the
    Python one is the tested one.

    The slot stays in the markup and stays empty; previews.js writes it.
    """
    from wingman.ui import copy as copy_mod

    note = copy_mod.INERT_NOTES["previews_off"]
    # Compare on words, not on the raw markup: the page wraps and indents,
    # so a substring test would pass while the sentence really was there.
    flat = " ".join(re.sub(r"<[^>]+>", " ", HTML).split())
    assert note not in flat, (
        "index.html types INERT_NOTES['previews_off'] instead of rendering "
        "it from the payload"
    )

    previews_js = (WEB / "previews.js").read_text(encoding="utf-8")
    assert "inertNotes.previews_off" in previews_js, (
        "previews.js no longer reads the note off the settings payload"
    )


def test_each_folder_cost_sentence_is_written_once_and_sits_under_its_field():
    """Both folder notes have TWO authors: the markup paints them before the
    first settings payload lands, and settings.js's render() rewrites them
    on every payload. The slot's previous occupant proved what that costs --
    the markup said "OBS's" with a straight apostrophe and settings.js said
    it with a typographic one, two spellings of one sentence that no reader
    could see and nothing held in step.

    The sentences are round 3's B11 answer, per folder: what changing that
    folder costs, stated before the click. The number belongs to
    set_folder's report afterwards, because it depends on the folder.

    **Scope is asserted here too, and that is round 5's E2.** There used to
    be one note for two fields, stating the RECORDING folder's cost, so
    changing the gamelogs path explained the recording watcher. Only the
    note's TEXT was guarded; nothing said it had to sit under the field it
    describes. So this now pins both: each note is in the same card as its
    own input, and the two costs are different sentences because the two
    folders do different things -- one starts a watcher, the other makes
    shared telemetry re-read (ui/api.py's set_folder branches on exactly that).

    Compared on words, since the markup wraps and indents and the JS is
    split across string concatenations.
    """
    settings_js = (WEB / "settings.js").read_text(encoding="utf-8")
    panes = dict(_panes())

    # (JS constant, note id, the input that note must sit beside, section)
    cases = [
        ("FOLDER_COST", "detect-note", "f-recdir", "uploading"),
        ("GAMELOG_COST", "gamelogs-note", "f-gamelogs", "alerts"),
    ]
    seen = set()
    for const, note_id, field_id, section in cases:
        literal = re.search(rf"var {const} = (.+?);\n", settings_js, re.DOTALL)
        assert literal, f"settings.js no longer declares {const}"
        js = re.sub(r"'\s*\+\s*'", "", literal.group(1)).strip().strip("'")
        js = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), js)
        js = " ".join(js.split())

        assert section in panes, f"there is no {section!r} section"
        pane = panes[section]
        slot = re.search(
            rf'<p class="sub-hint" id="{note_id}">(.*?)</p>', pane, re.DOTALL
        )
        assert slot, f"index.html no longer carries #{note_id} in {section}"
        markup = " ".join(re.sub(r"<[^>]+>", " ", slot.group(1)).split())

        assert markup == js, (
            f"index.html's #{note_id} and settings.js's {const} have "
            f"drifted:\n  markup: {markup!r}\n  js:     {js!r}"
        )

        # E2: the note must be in the same CARD as the field it describes,
        # not merely in the same section.
        card = next(
            (c for c in pane.split('<section class="card">') if field_id in c), None
        )
        assert card is not None, f"#{field_id} is not in the {section} section"
        assert note_id in card, (
            f"#{note_id} is not in the same card as #{field_id}. That is E2 "
            "exactly: a cost sentence rendering under a field it does not "
            "describe."
        )
        seen.add(js)

    assert len(seen) == len(cases), (
        "the two folders were given the same cost sentence; they do "
        "different things and E2 was the sentence that covered both"
    )


def test_the_dev_harness_quotes_copy_pys_inert_notes_verbatim():
    """dev.js is the one file allowed to fabricate data, and it fabricates
    this table so the Previews card can be verified in ?dev=1 at all. A
    double that has drifted from the thing it doubles hides exactly the bug
    it should catch -- the same argument dev.js's own comment makes about
    pushing onSettings when the bridge returns it.

    Escapes are decoded before comparing. dev.js writes the guillemet in
    "Settings > Discord" as `\\u203a`, which is the same character as
    copy.py's and not the same bytes; a raw substring test passes or fails
    on which of the two spellings the author happened to use. That was
    hidden until R1's and R2's copies of this table were de-duplicated --
    R2's used the literal and satisfied the test for both.
    """
    from wingman.ui import copy as copy_mod

    dev_js = (WEB / "dev.js").read_text(encoding="utf-8")
    # The strings are wrapped across source lines by ' + ', so join them
    # back before comparing, then decode \uXXXX to the characters they name.
    flat = re.sub(r"'\s*\+\s*'", "", dev_js)
    flat = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), flat)
    for key, note in copy_mod.INERT_NOTES.items():
        assert key in flat, f"dev.js's inert_notes is missing {key!r}"
        assert note in flat, (
            f"dev.js's inert_notes[{key!r}] has drifted from ui/copy.py"
        )


def test_the_remove_confirm_recognises_a_real_webhook_description():
    """Round 3, B12. The Remove dialog names WHICH webhook, because the
    field is masked and cannot -- but webhook_status() returns a PARSE
    ERROR for a stored value it cannot read, and interpolating that into
    "Combat logs stop being posted to ..." produces nonsense. settings.js
    tells the two apart by the one thing discord.describe() guarantees.

    Asserted rather than trusted, because that guard is a Python format
    typed into JavaScript: if describe() ever stops rendering the path,
    the confirm degrades silently to "this webhook" with nothing failing.
    """
    from wingman import discord as discord_mod

    described = discord_mod.describe(
        discord_mod.parse_webhook("https://discord.com/api/webhooks/1/tok")[0]
    )
    settings_js = (WEB / "settings.js").read_text(encoding="utf-8")
    guard = re.search(r"line\.indexOf\('([^']+)'\)", settings_js)
    assert guard, "settings.js no longer guards the Remove confirm's name"
    assert guard.group(1) in described, (
        f"settings.js looks for {guard.group(1)!r}, which discord.describe() "
        f"does not put in {described!r}"
    )


def test_the_dev_harness_shows_the_webhook_line_the_app_shows():
    """dev.js is the only file allowed to fabricate data, and this is the
    line round 3's B13 is about -- the only element on the Discord card
    that says which webhook is configured. Its fixture had drifted into a
    prose shape the app never renders, which made the Remove confirm's
    naming branch untestable by hand: the harness said "this webhook"
    while the app named it.
    """
    from wingman import discord as discord_mod

    dev_js = (WEB / "dev.js").read_text(encoding="utf-8")
    stored = re.search(r"discord_webhook: '([^']+)'", dev_js)
    assert stored, "dev.js no longer stores a fake webhook"
    fixture = re.search(r"\? '([^']*)' : statusLine", dev_js)
    assert fixture, "dev.js no longer defaults webhook_status"
    expected = discord_mod.describe(discord_mod.parse_webhook(stored.group(1))[0])
    assert fixture.group(1) == expected, (
        f"dev.js renders {fixture.group(1)!r} where the app renders {expected!r}"
    )


def test_the_dev_harness_declares_each_payload_key_once():
    """A duplicate key in an object literal is legal JavaScript. The last
    one wins, nothing warns, and the fixture the harness renders is not the
    one you are reading.

    This is not hypothetical. R1 and R2 of round 2 both needed
    `inert_notes` in dev.js's settings payload -- R1 for the Uploader
    panel's no_webhook sentence, R2 for Previews' previews_off -- and added
    it independently, five lines apart. Git merged the two cleanly, and the
    test above still passed, because both copies carry the right strings.

    Keys are checked across the whole file rather than per literal: dev.js
    builds its doubles from flat literals, and a repeated key anywhere in
    it is either this bug or a fixture shadowing another one.
    """
    dev_js = (WEB / "dev.js").read_text(encoding="utf-8")
    payload = dev_js[dev_js.index("function settingsPayload") :]
    payload = payload[: payload.index("\n  }")]

    # The payload's own top-level keys sit at exactly six spaces; anything
    # deeper belongs to a nested literal and may legitimately repeat (the
    # fake characters are a list of same-shaped objects). Asserting the
    # count first, because a regex that silently matches nothing is a test
    # that passes for the wrong reason -- the trap the max-width:720px
    # check in test_page_conventions.py records having fallen into.
    keys = re.findall(r"(?m)^ {6}([a-z_][\w]*)\s*:", payload)
    assert len(keys) >= 5, f"settingsPayload key scan found only {keys!r}"

    dupes = sorted({k for k in keys if keys.count(k) > 1})
    assert not dupes, (
        "dev.js declares these settings-payload keys more than once, so the "
        "harness renders whichever came last: " + repr(dupes)
    )


def test_every_message_slot_settings_js_writes_to_exists_in_the_page():
    """`say()` returns silently when its element is missing.

        function say(slot, text, tone) {
          var el = WM.el(slot);
          if (!el) { return; }

    That is the right behaviour at runtime -- a per-field message is not
    worth throwing over -- and it means a mistyped slot id swallows every
    error, refusal and warning for that field, permanently and with no
    symptom anywhere a user or a test would look. The field just stops
    explaining itself.

    Round 5's E2 made this worth guarding rather than merely true: the two
    folder fields shared one `#msg-folders` and now have one slot each,
    because after D2 they sit in different sections and a gamelogs refusal
    would otherwise have rendered onto a pane the user was not looking at.
    One id became two, in a file that resolves them through a lookup table
    rather than a literal, so the chance of a mismatch went up at exactly
    the moment the failure got quieter.

    Derived from the source both ways round: the literals are grepped out
    of settings.js, and the lookup table is read as a table. Retyping the
    list here would be the hand-kept copy CLAUDE.md forbids.
    """
    settings_js = (WEB / "settings.js").read_text(encoding="utf-8")

    slots = set(re.findall(r"(?:say|commit)\(\s*'(msg-[\w-]+)'", settings_js))

    table = re.search(r"var TARGET_MSG = \{([^}]*)\}", settings_js)
    assert table, "settings.js no longer declares TARGET_MSG"
    mapped = set(re.findall(r"'(msg-[\w-]+)'", table.group(1)))
    assert mapped, "TARGET_MSG names no message slots"
    slots |= mapped

    assert len(slots) >= 5, (
        f"only found {len(slots)} message slots in settings.js, which "
        "suggests the pattern changed and this guard stopped seeing them"
    )

    present = set(re.findall(r'class="field-msg" id="([\w-]+)"', HTML))
    missing = sorted(slots - present)
    assert not missing, (
        "settings.js writes to message slots that are not in index.html, so "
        f"every message for those fields is silently dropped: {missing}"
    )


def test_each_folder_field_reaches_its_own_note_and_message():
    """The four folder lookup tables must agree on their keys.

    `TARGET_FIELD`, `TARGET_MSG`, `TARGET_NOTE` and `TARGET_COST` are
    indexed by the same `which` -- the discriminator `Api.set_folder`,
    `pick_folder` and `detect_folder` all share. A key present in one and
    missing from another does not throw: `WM.el(undefined)` is null, and
    both `say()` and the note loop skip a null slot, so that folder simply
    stops reporting anything.

    Round 5's D2 is why there are four of them. One card held both folders
    under one note and one message slot; the fields now sit in different
    sections, each with its own note, its own cost sentence and its own
    slot, all reached through `which`.
    """
    settings_js = (WEB / "settings.js").read_text(encoding="utf-8")

    tables = {}
    for name in ("TARGET_FIELD", "TARGET_MSG", "TARGET_NOTE", "TARGET_COST"):
        block = re.search(name + r" = \{([^}]*)\}", settings_js)
        assert block, f"settings.js no longer declares {name}"
        tables[name] = set(re.findall(r"(\w+)\s*:", block.group(1)))

    keys = tables["TARGET_FIELD"]
    assert keys == {"recording", "gamelogs"}, (
        f"the folder discriminators changed: {sorted(keys)}. They mirror "
        "Api.set_folder/pick_folder/detect_folder and must match."
    )
    for name, got in tables.items():
        assert got == keys, (
            f"{name} is keyed {sorted(got)} but the folders are "
            f"{sorted(keys)}; the odd one out silently reports nothing"
        )


# ---- Task 7: About-card update UI --------------------------------------


def about_card_html() -> str:
    """The `About Wingman` card's markup, comments stripped.

    Same reasoning as `_settings_route`/`_panes` above: this file is read
    lexically, so a helper narrows every assertion below to the one card
    rather than to the whole page, which is what makes a false pass here
    findable.
    """
    body = re.sub(r"<!--.*?-->", "", HTML, flags=re.DOTALL)
    start = body.index("<h2>About Wingman</h2>")
    end = body.index("</section>", start)
    return body[start:end]


def test_about_card_has_live_update_status_progress_and_actions():
    card = about_card_html()
    assert 'aria-label="Settings"' in HTML
    assert 'id="update-status"' in card and 'role="status"' in card
    assert 'id="update-progress"' in card and "<progress" in card
    for control in ("btn-update-check", "btn-update-download", "btn-update-install"):
        assert f'id="{control}"' in card
    # Determinate from the start, not an indeterminate bar dressed as one:
    # the renderer only ever sets `.max`/`.value`, never removes them.
    assert 'max="1" value="0"' in card
    # One accent or none, and this card offers none -- `.btn.acc` is
    # reserved for the single primary action a screen exists to perform,
    # and Settings has no such action.
    assert "btn acc" not in card
    # Start-on-login and the licence line survive; this is an addition to
    # the card, not a replacement of it.
    assert 'id="start-on-login"' in card
    assert 'id="msg-about"' in card


def test_update_progress_is_hidden_until_a_download_starts():
    card = about_card_html()
    assert re.search(r'<progress id="update-progress"[^>]*\bhidden\b', card), (
        "the progress element must start hidden -- there is nothing to "
        "show a percentage of before a download begins"
    )


def test_install_uses_app_confirm_before_bridge_call():
    settings_js = (WEB / "settings.js").read_text(encoding="utf-8")
    confirm = settings_js.index("WM.confirm('Install update?'")
    send = settings_js.index("WM.send('install_update')", confirm)
    assert confirm < send
    assert "window.confirm" not in settings_js


def test_general_entry_reads_update_status_and_no_other_section_does():
    """The read that fills the card's content must be scoped the same way
    every other section-owned fetch is (alerts.js, bookmarks.js,
    previews.js): on `wm:section === 'general'`, not on every section
    change, or a screen the user is not looking at keeps polling.
    """
    settings_js = (WEB / "settings.js").read_text(encoding="utf-8")
    match = re.search(
        r"document\.addEventListener\('wm:section', function \(ev\) \{\s*"
        r"if \(ev\.detail === 'general'\) \{([^}]*)\}",
        settings_js,
    )
    assert match, "no wm:section listener scoped to 'general' was found"
    assert "WM.send('update_status')" in match.group(1)


def test_general_update_read_cannot_overwrite_any_newer_card_render():
    """Pushes own freshness even when their phase does not change.

    Download progress sends several `downloading` payloads, so comparing
    states cannot detect that a cached read is stale. The card renderer must
    advance an unconditional generation on every accepted render, while the
    General-entry read may paint only if that generation has not changed.
    """
    settings_js = (WEB / "settings.js").read_text(encoding="utf-8")
    renderer = settings_js.split("function renderUpdate(p) {", 1)[1].split("\n  }", 1)[
        0
    ]
    listener = settings_js.split("document.addEventListener('wm:update-status'", 1)[
        1
    ].split("\n  });", 1)[0]
    general_entry = settings_js.split("document.addEventListener('wm:section'", 1)[
        1
    ].split("\n  });", 1)[0]

    assert "var updateRenderGeneration = 0;" in settings_js
    increment = "updateRenderGeneration += 1;"
    assert increment in renderer
    assert "p.state" not in renderer[: renderer.index(increment)], (
        "generation must advance before any state comparison so same-state "
        "progress pushes invalidate older reads"
    )
    assert "renderUpdate(ev.detail || {});" in listener
    capture = "var cardGenerationAtRead = updateRenderGeneration;"
    send = "WM.send('update_status')"
    assert general_entry.index(capture) < general_entry.index(send)
    assert re.search(
        r"if \(p\s*&&\s*updateRenderGeneration\s*===\s*"
        r"cardGenerationAtRead\)\s*\{\s*renderUpdate\(p\);\s*\}",
        general_entry,
    )


def test_renderer_reads_only_payload_booleans_for_permission():
    """Task 7's binding rule: the renderer must not reconstruct
    can_check/can_download/can_install from `state`; it reads exactly the
    fields Python already computed.
    """
    settings_js = (WEB / "settings.js").read_text(encoding="utf-8")
    renderer = settings_js[settings_js.index("function renderUpdate(") :]
    renderer = renderer[: renderer.index("\n  }\n")]
    for flag in ("can_check", "can_download", "can_install"):
        assert f"p.{flag}" in renderer, (
            f"renderUpdate must read {flag} from the payload rather than "
            "deriving it from p.state"
        )


def test_update_error_takes_precedence_over_normal_state_copy():
    settings_js = (WEB / "settings.js").read_text(encoding="utf-8")
    status_text = settings_js[settings_js.index("function updateStatusText(") :]
    status_text = status_text[: status_text.index("\n  }\n")]

    assert status_text.index("p.error") < status_text.index("switch (p.state)")


def test_update_actions_render_only_from_backend_pushes():
    """Action return values can arrive after a fast worker's newer push.

    Only the generation-gated General-entry read may render its method
    return; all state-changing actions use onUpdateStatus as their
    authoritative path.
    """
    settings_js = (WEB / "settings.js").read_text(encoding="utf-8")
    for method in ("check_for_updates", "download_update", "install_update"):
        send = settings_js.index(f"WM.send('{method}')")
        statement = settings_js[send : settings_js.index(";", send) + 1]
        assert "renderUpdate" not in statement
        assert ".then(" not in statement

    cached_read = settings_js.index("WM.send('update_status')")
    statement = settings_js[cached_read : settings_js.index(";", cached_read) + 1]
    assert "renderUpdate" in statement


def test_confirm_fires_once_on_a_true_downloading_to_installable_transition():
    """The transition check must be one function taking the previous
    phase, not a copy re-derived at each render entry point (the cached
    General read and the `wm:update-status` push listener). Separate copies
    could auto-confirm on a phase one path never crossed, while rendering
    action returns could move the shared phase backwards after a newer push.
    """
    settings_js = (WEB / "settings.js").read_text(encoding="utf-8")
    assert re.search(
        r"function \w+\(\s*\w+\s*,\s*\w+\s*\)\s*\{[^}]*downloading[^}]*ready",
        settings_js,
        re.DOTALL,
    ), (
        "expected one function receiving (previous, next) that tests for "
        "the downloading -> ready transition"
    )
    # Every call to renderUpdate must feed and update the SAME previous-phase
    # variable, so a transition detected by one entry point cannot be missed
    # or double-counted by another.
    assert settings_js.count("updatePhase = ") >= 1
    renderer = settings_js[settings_js.index("function renderUpdate(") :]
    renderer = renderer[: renderer.index("\n  }\n")]
    assert re.search(
        r"justFinishedDownloading\([^)]*\)\s*&&\s*p\.can_install",
        renderer,
    ), "source checkouts must not receive an unusable automatic Install prompt"
    calls = len(re.findall(r"renderUpdate\(", settings_js))
    assert calls == 3, (
        "expected renderUpdate only in its declaration, the cached General read, "
        "and the push listener; action returns must not repaint stale state; "
        f"found {calls} occurrences"
    )
