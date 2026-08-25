"""The first-run screen, checked lexically.

Nothing in this suite renders index.html or executes web/firstrun.js, so
this file follows the house approach of test_page_conventions.py and
test_bridge_contract.py: read the source, and pin the facts that would
otherwise fail silently.

"Silently" is the operative word on this screen. It is the only one a user
can be shown before they have seen anything else, and its failure mode is
not an error -- a handler that never registers leaves an inert copy of the
screen, and a message slot that is never written just looks like a button
that does nothing. Both have shipped here.

Every rule below is a finding from docs/ui-critique.md section 5.
"""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
WEB = ROOT / "obs_youtube_uploader" / "web"
HTML = (WEB / "index.html").read_text(encoding="utf-8")
JS = (WEB / "firstrun.js").read_text(encoding="utf-8")
API = (ROOT / "obs_youtube_uploader" / "ui" / "api.py").read_text(encoding="utf-8")


def _route() -> str:
    """Just the #route-firstrun block, comments stripped.

    Scoped rather than searching the whole document: several of these
    controls have same-named siblings in Settings, which is the module
    this screen's behaviour is repeatedly compared against.
    """
    start = HTML.index('<div class="route" id="route-firstrun">')
    end = HTML.index('id="statusbar-slot"', start)
    return re.sub(r"<!--.*?-->", "", HTML[start:end], flags=re.DOTALL)


def _js() -> str:
    text = re.sub(r"/\*.*?\*/", "", JS, flags=re.DOTALL)
    return re.sub(r"(?m)^\s*//.*$", "", text)


# ---- finding 1: the screen has an exit ---------------------------------


def test_the_screen_can_be_left_without_choosing_a_folder():
    """PRODUCT.md: "It must not require the EVE tools to upload a video, or
    a Google account to use the EVE tools. The two halves must stay
    independent."

    A recording folder configures the UPLOADER half. This was the only
    screen in the app with no exit, so someone who installed Wingman for
    previews and bookmark keybinds was stopped at it -- and app.js hides
    both the gear and the whole destination nav on this route, so there was
    genuinely nowhere else to go.
    """
    assert 'id="btn-firstrun-skip"' in _route(), "no way off the first-run screen"
    src = _js()
    assert "btn-firstrun-skip" in src, "the skip control is markup with no handler"
    assert "'skip_first_run'" in src


def test_the_skip_is_persisted_by_a_bridge_method_that_exists():
    """WM.send names a Python method by string. A misspelling resolves to
    undefined and the promise rejects into a bridge failure the page reads
    as "could not reach the app" -- so the exit would be present, pressable
    and inert. Nothing else in the suite checks this direction of the
    bridge for this screen.

    Persisted rather than held for the session, because
    _push_first_run_when_ready decides whether the screen appears at all:
    a session-only skip returns on the next launch, which is the same trap
    with an extra step.
    """
    assert "def skip_first_run(self)" in API
    assert 'settings.get("first_run_skipped")' in API


def test_the_skip_is_not_a_second_primary_action():
    """.btn.acc is the one accent per screen and Continue is it.
    test_page_conventions.py's accent count would catch a second one; this
    pins the positive half -- the skip is the quiet affordance, not a
    third button competing with the answer the screen wants.
    """
    route = _route()
    assert 'class="linkbtn" id="btn-firstrun-skip"' in route
    assert route.count('class="btn acc"') == 1


# ---- finding 2: the screen says what the app is ------------------------


def test_the_screen_names_the_eve_half_of_the_product():
    """The first and only thing Wingman used to say to a new user was that
    it watches a folder for OBS recordings. PRODUCT.md opens by saying that
    framing -- an uploader with EVE extras -- "is out of date and should
    not be used to decide anything", and this screen was that framing,
    shown before anything else.

    It is also what makes the skip legible: a folder the EVE tools do not
    need is a folder you can decline. Asserted on the vocabulary rather
    than the sentence, so the copy can be rewritten without failing here.
    """
    route = _route().lower()
    assert "previews" in route
    assert "keybinds" in route
    assert "later in settings" in route


# ---- finding 3: Detect reports finding nothing -------------------------


def test_detect_says_so_when_it_finds_nothing():
    """`if (path) setChosen(path)` with no else. OBS not installed, or its
    config elsewhere: the field stayed empty, the note still explained what
    Detect reads, and Continue stayed disabled -- a failed detection and a
    dead button were indistinguishable, on the one screen with no way out.

    settings.js:132-137 has always said it ("Detect found neither folder
    automatically"), twenty lines away in a sibling module.
    """
    src = _js()
    handler = src[src.index("btn-firstrun-detect") :]
    handler = handler[: handler.index("addEventListener", 40)]
    assert "note(" in handler, "Detect still has no failure branch"


# ---- finding 4: the note has a precedence rule -------------------------


def test_the_note_is_not_a_second_copy_of_its_own_sentence():
    """#firstrun-note's standing text lives in index.html and firstrun.js
    restores it, which is two places for one sentence unless the module
    reads it back out of the DOM.

    DESIGN.md, "State that must not be retyped": four places carried a
    count of the bookmark keybinds and three of them were wrong. "Derive
    it, or assert it in a test."
    """
    # The element has to exist, and not only because the sentence does:
    # firstrun.js reads it at the top of its IIFE, and a throw there takes
    # every registration below it down with it -- including onFirstRun,
    # which is the only thing that shows this route at all.
    route = _route()
    assert 'id="firstrun-note"' in route
    assert "Detect reads the folder" in route

    src = _js()
    # The assignment direction matters: writing INTO the element is what
    # the error path has always done. Reading OUT of it is the derivation.
    assert "= WM.el('firstrun-note').textContent" in src
    assert "Detect reads the folder" not in src, (
        "firstrun.js carries its own copy of the standing note; read it "
        "from the element instead"
    )


def test_a_message_about_the_last_action_is_restored_by_the_next_one():
    """The note carries three different things -- the standing explanation,
    a detection that found nothing, and a refused folder -- and the refusal
    path used to overwrite the element permanently. A user who mistyped a
    path, read the error, and wanted the Detect explanation back had lost
    it for the session.

    The restore half of the rule is the input handler: typing is the thing
    that can change the outcome the message was about.
    """
    src = _js()
    typing = src[src.index("f-firstrun-dir').addEventListener") :]
    typing = typing[: typing.index("});")]
    assert "note('')" in typing, "nothing restores the note once it carries an error"


def test_the_note_has_a_severity_treatment_and_it_uses_the_tokens():
    """A warning that renders in --text-faint alongside the standing
    explanation is not a warning. --warn and --err are the same two tokens
    .field-msg and the status strip use, so one severity reads the same
    everywhere; a local colour literal here would be a third answer.
    """
    css = (WEB / "style.css").read_text(encoding="utf-8")
    assert ".firstrun-note.warn { color: var(--warn); }" in css
    assert ".firstrun-note.err { color: var(--err); }" in css


# ---- finding 5: the placeholder suggests input -------------------------


def test_the_placeholder_is_an_example_not_a_status_report():
    """The field is typeable, and the placeholder is the one piece of text
    inside it. "No folder chosen yet" spent it telling the user something
    the disabled Continue button below already says.
    """
    field = re.search(r'<input[^>]*id="f-firstrun-dir"[^>]*>', _route()).group(0)
    placeholder = re.search(r'placeholder="([^"]*)"', field).group(1)
    assert "chosen" not in placeholder.lower()
    assert placeholder.startswith("C:\\"), placeholder


# ---- not a finding, found next to one ----------------------------------


def test_a_cancelled_browse_keeps_the_path_already_found():
    """Api.pick_folder returns "" on cancel, and this screen handed that
    straight to setChosen -- so cancelling a second Browse wiped the path
    the first one found and re-disabled Continue.

    settings.js's applyFolder has always guarded it ("a cancelled dialog is
    also a valid result"). This screen did not, and the smoke checklist's
    "Cancelling a Browse changes nothing" is written against Settings, so
    nothing would have caught it here.
    """
    src = _js()
    browse = src[src.index("btn-firstrun-browse") :]
    browse = browse[: browse.index("addEventListener", 40)]
    assert "if (!path) { return; }" in browse
