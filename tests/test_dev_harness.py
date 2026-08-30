"""The `?dev=1` harness, checked against the bridge it doubles.

`web/dev.js` is the only file allowed to fabricate data, and it is how
every screen gets verified, because nothing in this suite renders the page.
That makes a gap in it expensive in a specific way: a bridge method with no
stub does not break the harness loudly. `WM.send` rejects to the console
and the page draws whatever it can without the data — which, for a section
whose entire content comes from one call, is a screen that looks finished
and is missing its subject.

That happened, to `get_bookmarks`, for two rounds. The Bookmarks section
rendered three cards, their headings, their prose and a Reset button with
zero keybind rows, and five sessions verified through it.
"""

import re
from pathlib import Path

from wingman import bookmarks
from wingman.evesettings import selective

WEB = Path(__file__).resolve().parents[1] / "wingman" / "web"
DEV_JS = (WEB / "dev.js").read_text(encoding="utf-8")

# Every page module, so a WM.send anywhere is covered rather than only the
# ones someone remembered to list.
PAGE_JS = {
    path.name: path.read_text(encoding="utf-8")
    for path in sorted(WEB.glob("*.js"))
    if path.name != "dev.js"
}


def _stubbed() -> set[str]:
    """Every bridge method dev.js provides, however it provides it.

    Three shapes: the generic `log()` list, the per-field
    `{applied, persisted, error}` list, and direct `api.name = ` assignment.
    """
    names = set(re.findall(r"api\.([a-z_][\w]*)\s*=", DEV_JS))
    # The two forEach tables, whose bodies are lists of quoted names.
    for block in re.findall(r"\[([^\]]*?)\]\s*\.forEach", DEV_JS, re.DOTALL):
        names.update(re.findall(r"'([a-z_][\w]*)'", block))
    return names


def _called() -> dict[str, set[str]]:
    """Every method the page asks the bridge for, by file."""
    out: dict[str, set[str]] = {}
    for name, source in PAGE_JS.items():
        found = set(re.findall(r"WM\.send\(\s*'([a-z_][\w]*)'", source))
        if found:
            out[name] = found
    return out


def _fixture_body(marker: str) -> str:
    """One stub's body, with `//` comments stripped.

    The comments have to go before any quote-scanning: this file's prose
    contains apostrophes ("the file's own comment"), and an unpaired one
    opens a string that swallows the next several hundred characters and
    reports them as a malformed fixture value. That is a test failing for a
    reason that has nothing to do with what it checks.
    """
    block = DEV_JS[DEV_JS.index(marker) :]
    block = block[: block.index("\n  };")]
    return re.sub(r"(?m)^\s*//.*$", "", block)


def test_the_scan_found_both_sides():
    """A regex that silently matched nothing would make every assertion
    below pass while checking air -- the trap test_page_conventions.py
    records having fallen into with its max-width brace matcher."""
    stubbed = _stubbed()
    called = _called()
    assert len(stubbed) >= 20, f"dev.js stub scan found only {sorted(stubbed)}"
    assert len(called) >= 4, f"page WM.send scan found only {sorted(called)}"
    assert "get_settings" in stubbed and "list_rows" in stubbed


def test_every_bridge_method_the_page_calls_has_a_double():
    """The general form of the `get_bookmarks` gap, and the reason this
    file exists rather than two fixture assertions.

    A missing stub is invisible in the way that matters: the console
    carries `bridge: no such method: X`, which nobody reads while looking
    at a screen, and the screen itself renders its static markup and omits
    everything the call would have filled in.

    **The dangerous class is the READS, and it is now empty.** A method the
    page calls on load or route entry fills a section's content, so a
    missing double leaves a screen that looks finished with its subject
    absent -- `get_bookmarks` rendered three cards, their headings, their
    prose and a Reset button with zero keybind rows, through two rounds and
    five sessions' verification runs.

    The remaining gaps are all user-initiated actions: click, change and
    keydown handlers. Those fail *visibly* -- you press the thing and
    nothing happens, in the same session in which you pressed it -- so they
    are debt rather than a trap, and stubbing them is a larger change than
    the one this file came in with.

    Asserted as exact equality rather than a subset, so the list stays
    honest in both directions: a new gap fails, and so does an entry that
    has since been doubled and not removed from here.
    """
    known_gaps = {
        "bookmarks.js: alert_bookmarks",
        "bookmarks.js: capture_bind",
        "bookmarks.js: parse_bind",
        "bookmarks.js: reset_binds",
        "bookmarks.js: save_bookmarks",
        "firstrun.js: skip_first_run",
        "list.js: open_recording_dir",
        "previews.js: alert_bookmarks",
        "previews.js: capture_preview_bind",
        "previews.js: parse_preview_bind",
        "previews.js: set_preview_binds",
        "settings.js: set_preview_enabled",
        "settings.js: set_restore_preview_positions",
    }
    stubbed = _stubbed()
    missing = {
        f"{file}: {method}"
        for file, methods in _called().items()
        for method in methods
        if method not in stubbed
    }
    new = sorted(missing - known_gaps)
    assert not new, (
        "the page calls bridge methods the ?dev=1 harness does not double, "
        "so those screens render without their data and look finished: " + repr(new)
    )
    fixed = sorted(known_gaps - missing)
    assert not fixed, (
        "these are doubled now and should come off the known-gaps list: " + repr(fixed)
    )


def test_no_load_time_read_is_left_undoubled():
    """The half of the rule above that must not drift into the list.

    Every method named here is fetched on load or route entry and its
    result is rendered, so it decides whether a section has any content at
    all. These are the ones whose absence produces a finished-looking empty
    screen rather than a dead button, and none of them may be a known gap.
    """
    reads = {
        "get_settings",
        "list_rows",
        "skills_state",
        "get_bookmarks",
        "get_preview_hotkey_state",
    }
    stubbed = _stubbed()
    undoubled = sorted(reads - stubbed)
    assert not undoubled, (
        "a screen's own content comes from these, so the harness renders "
        "that screen as a finished-looking shell without them: " + repr(undoubled)
    )


def test_the_harness_assigns_each_bridge_method_once():
    """Sibling of test_the_dev_harness_declares_each_payload_key_once.

    That one scans `settingsPayload` only, so two `api.get_bookmarks = `
    assignments would sail straight through it -- flagged by R2 when this
    file's stubs were added. A later assignment silently replaces an
    earlier one, which is the same failure as a duplicate object key and
    just as quiet.
    """
    assigned = re.findall(r"(?m)^\s*api\.([a-z_][\w]*)\s*=", DEV_JS)
    assert len(assigned) >= 8, f"assignment scan found only {assigned!r}"
    dupes = sorted({n for n in assigned if assigned.count(n) > 1})
    assert not dupes, (
        "dev.js assigns these bridge methods more than once, so the harness "
        "serves whichever came last: " + repr(dupes)
    )


def test_profiles_group_fixture_matches_the_python_payload():
    """The browser harness must show exactly the groups Python sends."""
    marker = "var selective = {"
    assert marker in DEV_JS
    block = DEV_JS[DEV_JS.index(marker) : DEV_JS.index("\n  };", DEV_JS.index(marker))]

    def parsed(kind: str) -> list[dict]:
        match = re.search(kind + r": \[(.*?)\n\s*\]", block, re.DOTALL)
        assert match, kind
        return [
            {"id": ident, "label": label, "default_on": default == "true"}
            for ident, label, default in re.findall(
                r"\{ id: '([^']+)', label: '([^']+)', default_on: (true|false) \}",
                match.group(1),
            )
        ]

    assert parsed("characters") == selective.groups_payload("character")
    assert parsed("accounts") == selective.groups_payload("account")
    assert "selective_copy_available: true" in DEV_JS
    assert "copy_groups: selective.groups_payload" in DEV_JS


def test_the_preview_fixture_uses_real_gesture_strings():
    """Previews store `preview/gestures.py` display strings
    ("Ctrl+Alt+Right"), NOT the AHK that Bookmarks stores ("^!Right"). The
    two subsystems genuinely differ, and the harness has to match each.

    This exists because the fixture got the format wrong on its first
    draft, and the failure is the deceptive kind: the page renders the
    stored value directly, so a wrong format shows up as `^!Right` in a
    bind button and reads as a formatting bug in the page rather than as a
    wrong double. Round-tripped through the real parser rather than
    compared to a literal, so a change to the format fails here instead of
    being invisibly re-fabricated.
    """
    from wingman.preview import gestures as preview_gestures

    block = _fixture_body("api.get_preview_hotkey_state")
    gestures = {g for g in re.findall(r"'([^']+)'", block) if "+" in g}
    assert gestures, "the preview fixture declares no gesture strings"
    for gesture in sorted(gestures):
        parsed = preview_gestures.parse(gesture)
        assert parsed is not None, (
            f"dev.js's preview fixture holds {gesture!r}, which "
            "preview/gestures.py cannot parse"
        )
        assert preview_gestures.display(parsed) == gesture, (
            f"dev.js's preview fixture holds {gesture!r}, which is not the "
            "canonical spelling the app would store"
        )


def test_the_bookmark_fixture_uses_real_ahk_strings():
    """The mirror of the above, for the subsystem that really does use AHK.

    bookmarks.parse_ahk is the same function the bridge validates a
    hand-typed bind with, so a fixture it rejects is one the app could
    never have produced.
    """
    block = _fixture_body("api.get_bookmarks")
    binds = set(re.findall(r"keybinds\.\w+\s*=\s*'([^']+)'", block))
    assert binds, "the bookmarks fixture assigns no keybinds"
    for bind in sorted(binds):
        assert bookmarks.parse_ahk(bind)["ahk"], (
            f"dev.js's bookmarks fixture holds {bind!r}, which "
            "bookmarks.parse_ahk rejects"
        )


def test_the_bookmark_binds_are_not_a_hand_kept_copy():
    """Derive it or assert it -- DESIGN.md, "state that must not be
    retyped".

    Four places once carried a count of these binds: bookmarks.py defined
    eighteen, a confirmation said twenty-one, two comments said nineteen,
    and the smoke checklist said twenty-one. The user-visible one guarded
    the only irreversible action on that screen.

    So the harness fixture is allowed to be a literal -- it has to be, it
    is JavaScript -- but not allowed to drift. A fixture that quietly lost
    a bind would put the harness back to lying about this section, just
    less obviously than the empty list it replaced.
    """
    block = DEV_JS[DEV_JS.index("var bookmarkBinds = [") :]
    block = block[: block.index("];")]
    ids = re.findall(r"'([A-Za-z0-9]+)'", block)
    assert ids == list(bookmarks.BIND_IDS), (
        "dev.js's bookmarkBinds has drifted from bookmarks.BIND_IDS"
    )


def test_the_bookmark_labels_are_not_a_hand_kept_copy():
    """Same rule, and the half a user actually reads. These are house
    style -- the finisher scheme and the tag letters are FlyGD's own
    (PRODUCT.md) -- so a drifted label in the harness would be verified
    against, and look plausible, while naming something the app does not.
    """
    block = DEV_JS[DEV_JS.index("var bookmarkLabels = {") :]
    block = block[: block.index("};")]
    pairs = dict(re.findall(r"(\w+):\s*'([^']*)'", block))
    assert pairs == dict(bookmarks.BIND_LABELS), (
        "dev.js's bookmarkLabels has drifted from bookmarks.BIND_LABELS"
    )


def test_the_bookmark_groups_are_not_a_hand_kept_copy():
    """Round 5, C8's fixture. The route no longer renders eighteen rows in
    one flat list: `bookmarks.bind_groups()` splits them and shortens the
    labels, and the page renders a named group as a multi-column block.

    That makes this fixture load-bearing in the same way `bookmarkLabels`
    is, and in one extra way. A harness whose groups disagree with the
    derivation would render the layout the lane was verifying at a row
    count and a label length the app never produces -- and the derivation
    is exactly the part with no other coverage on screen, because the
    grouping is invisible in the payload and only visible in the shape of
    the rendered card.
    """
    block = DEV_JS[DEV_JS.index("var bookmarkGroups = [") :]
    block = block[: block.index("\n  ];")]
    # Each `{ name: ..., ids: [...], short: {...} }` in source order.
    groups = []
    for chunk in re.findall(
        r"\{\s*name:\s*'([^']*)',\s*ids:\s*\[(.*?)\],\s*short:\s*\{(.*?)\}\s*\}",
        block,
        re.DOTALL,
    ):
        name, ids, short = chunk
        groups.append(
            {
                "name": name,
                "ids": re.findall(r"'([^']+)'", ids),
                "short": dict(re.findall(r"(\w+):\s*'([^']*)'", short)),
            }
        )
    assert groups == [dict(g) for g in bookmarks.bind_groups()], (
        "dev.js's bookmarkGroups has drifted from bookmarks.bind_groups()"
    )
