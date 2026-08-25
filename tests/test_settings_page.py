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

WEB = pathlib.Path(__file__).resolve().parents[1] / "obs_youtube_uploader" / "web"
HTML = (WEB / "index.html").read_text(encoding="utf-8")


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
    assert [name for name, _ in _rail()] == [name for name, _ in _panes()]


def test_general_is_the_last_rail_item():
    """Its whole content is the switch that hides Bookmarks and Previews
    (app.js's EVE_SECTIONS), so it sits under the two entries it removes
    and the rail loses its tail rather than a hole in its middle. It is
    also visited once, probably never, and was first.

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
    from obs_youtube_uploader.ui import copy as copy_mod

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


def test_the_dev_harness_quotes_copy_pys_inert_notes_verbatim():
    """dev.js is the one file allowed to fabricate data, and it fabricates
    this table so the Previews card can be verified in ?dev=1 at all. A
    double that has drifted from the thing it doubles hides exactly the bug
    it should catch -- the same argument dev.js's own comment makes about
    pushing onSettings when the bridge returns it.
    """
    from obs_youtube_uploader.ui import copy as copy_mod

    dev_js = (WEB / "dev.js").read_text(encoding="utf-8")
    # The strings are wrapped across source lines by ' + ', so join them
    # back before comparing.
    flat = re.sub(r"'\s*\+\s*'", "", dev_js)
    for key, note in copy_mod.INERT_NOTES.items():
        assert key in flat, f"dev.js's inert_notes is missing {key!r}"
        assert note in flat, (
            f"dev.js's inert_notes[{key!r}] has drifted from ui/copy.py"
        )
