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

import json
import re
import subprocess
from pathlib import Path

from wingman import bookmarks
from wingman.evesettings import identity, selective

WEB = Path(__file__).resolve().parents[1] / "wingman" / "web"
DEV_JS = (WEB / "dev.js").read_text(encoding="utf-8")
EVE_SETTINGS_JS = (WEB / "evesettings.js").read_text(encoding="utf-8")
INDEX_HTML = (WEB / "index.html").read_text(encoding="utf-8")

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


def _identity_scenarios() -> dict:
    match = re.search(
        r"var identityScenarios = JSON\.parse\('(.*?)'\);", DEV_JS, re.DOTALL
    )
    assert match, "dev.js must declare one JSON-backed identity scenario table"
    return json.loads(match.group(1))


def test_identity_scenario_selector_covers_every_visual_state_once():
    required = {
        "idle",
        "waiting",
        "none",
        "ambiguous",
        "candidate-multiple",
        "pending-name",
        "existing-name",
        "roster-one",
        "roster-two",
        "roster-three",
        "roster-empty",
        "move",
        "full",
    }
    scenarios = _identity_scenarios()
    assert set(scenarios) == required
    table = re.search(
        r"var identityScenarios = JSON\.parse\('(.*?)'\);", DEV_JS, re.DOTALL
    ).group(1)
    for token in required:
        assert table.count('"' + token + '":{') == 1, token
    assert "new URLSearchParams(window.location.search)" in DEV_JS
    assert ".get('identity')" in DEV_JS
    assert ".has('identity')" in DEV_JS
    assert "if (identityScenarioRequested && !identityScenarioQueued)" in DEV_JS
    assert "if (identityScenarioRequested) {" in DEV_JS


def test_bare_dev_mode_does_not_open_an_identity_scenario():
    """The explicit identity selector, not dev mode itself, owns this route.

    The ordinary fixture must keep Profiles on its usual landing route so it
    remains useful for reviewing the account source and backup list.
    """
    assert "var identityScenarioRequested = identitySearch.has('identity');" in DEV_JS
    assert "var identityScenario = identitySearch.get('identity') || 'idle';" in DEV_JS
    assert "if (identityScenarioRequested && !identityScenarioQueued)" in DEV_JS
    assert "if (identityScenarioRequested) {" in DEV_JS
    assert "document.readyState === 'loading'" in DEV_JS


def test_identity_scenario_rosters_obey_production_invariants():
    for scenario_name, scenario in _identity_scenarios().items():
        claimed = set()
        names = set()
        for account in scenario["accounts"]:
            character_ids = account["character_ids"]
            assert len(character_ids) <= 3, (scenario_name, account)
            account_name = account["account_name"].strip()
            if character_ids:
                assert account_name, (scenario_name, account)
            if account_name:
                folded = account_name.casefold()
                assert folded not in names, (scenario_name, account_name)
                names.add(folded)
            for character_id in character_ids:
                assert character_id not in claimed, (scenario_name, character_id)
                claimed.add(character_id)


def test_ordinary_profiles_fixture_keeps_a_three_character_account_and_matching_backup():
    scenarios = _identity_scenarios()
    account = next(
        item for item in scenarios["idle"]["accounts"] if item["id"] == "1001"
    )
    assert account["character_ids"] == ["90000000", "90000001", "90000002"]
    assert 'display_name: "alpha@example"' in DEV_JS
    assert 'display_meta: "Account 1001"' in DEV_JS


def test_profiles_fixture_covers_new_visual_states():
    for query in ("backups", "copy", "formations-account"):
        assert ".get('" + query + "')" in DEV_JS
    for state in ("empty", "unreadable", "filtered"):
        assert "'" + state + "'" in DEV_JS
    assert "Copy operation in progress" in DEV_JS
    assert "Copy complete" in DEV_JS


def _identity_character_names() -> dict[str, str]:
    block = DEV_JS[
        DEV_JS.index("var eveNames = [") : DEV_JS.index(
            "];", DEV_JS.index("var eveNames = [")
        )
    ]
    return {
        str(90000000 + index): name
        for index, name in enumerate(re.findall(r"'([^']+)'", block))
    }


def _fixture_labels_from_identity_scenario(scenario: dict) -> dict[str, dict]:
    names = _identity_character_names()
    return {
        account["id"]: identity.account_identity(
            account["id"],
            {account["id"]: account["account_name"]} if account["account_name"] else {},
            {account["id"]: account["character_ids"]}
            if account["character_ids"]
            else {},
            names.__getitem__,
        )
        for account in scenario["accounts"]
    }


def _run_dev_initial_account_labels(scenario: dict) -> dict[str, dict]:
    formatter = re.search(
        r"  function devAccountLabel\(account\) \{.*?\n  \}\n\n"
        r"  function refreshDevAccount",
        DEV_JS,
        re.DOTALL,
    )
    assert formatter, "dev.js must have one formatter for refreshed account labels"
    builder = re.search(
        r"  function devFixtureAccounts\(scenario\) \{.*?\n  \}\n\n"
        r"  eve\.accounts = devFixtureAccounts",
        DEV_JS,
        re.DOTALL,
    )
    assert builder, "dev.js must derive each scenario's initial account labels"
    source = (
        "var characters = "
        + json.dumps(_identity_character_names())
        + ";\nvar eve = { identity_characters: Object.keys(characters).map(function (id) { return { id: id, name: characters[id] }; }) };\n"
        + "function devCharacter(id) { return eve.identity_characters.filter(function (item) { return item.id === id; })[0]; }\n"
        + formatter.group(0).removesuffix("\n\n  function refreshDevAccount")
        + "\n"
        + builder.group(0).removesuffix("\n\n  eve.accounts = devFixtureAccounts")
        + "\nvar scenario = "
        + json.dumps(scenario)
        + ";\nvar accounts = devFixtureAccounts(scenario);\n"
        + "process.stdout.write(JSON.stringify(accounts.map(function (account) { return { primary: account.display_name, secondary: account.display_meta, option: account.name }; })));"
    )
    completed = subprocess.run(
        ["node", "-e", source], check=True, capture_output=True, text=True
    )
    return {
        account["id"]: label
        for account, label in zip(
            scenario["accounts"], json.loads(completed.stdout), strict=True
        )
    }


def test_dev_account_labels_match_the_python_identity_contract():
    for scenario_name, scenario in _identity_scenarios().items():
        expected = _fixture_labels_from_identity_scenario(scenario)
        assert _run_dev_initial_account_labels(scenario) == expected, scenario_name
    assert "devAccountLabels" not in DEV_JS
    assert "eve.accounts = devFixtureAccounts(selectedIdentityScenario);" in DEV_JS
    assert "eve.accounts.forEach(refreshDevAccount);" not in DEV_JS


def _copy_fixture_completion(copy_scenario: str) -> int:
    mutation = re.search(
        r"  function eveMutation\(name\) \{.*?\n  \}\n  \['eve_settings_copy'",
        DEV_JS,
        re.DOTALL,
    )
    assert mutation, "dev.js must retain the delayed mutation fixture"
    source = (
        "var copyScenario = " + json.dumps(copy_scenario) + "; var completions = 0;\n"
        "var window = { onEveSettingsDone: function () { completions += 1; } };\n"
        "var setTimeout = function (callback) { callback(); };\n"
        + mutation.group(0).removesuffix("\n  ['eve_settings_copy'")
        + "\neveMutation('eve_settings_copy')();\n"
        "process.stdout.write(String(completions));"
    )
    completed = subprocess.run(
        ["node", "-e", source], check=True, capture_output=True, text=True
    )
    return int(completed.stdout.rsplit("\n", 1)[-1])


def test_copy_fixture_has_stable_busy_and_settled_success_states():
    paint = re.search(
        r"function paintCommit\(\) \{(.*?)\n  \}", EVE_SETTINGS_JS, re.DOTALL
    )
    assert paint and "Copy operation in progress\\u2026" in paint.group(1)
    followup = re.search(r'<div id="es-copy-followup".*?</div>', INDEX_HTML, re.DOTALL)
    assert followup and "Copy complete." in followup.group(0)
    assert _copy_fixture_completion("busy") == 0
    assert _copy_fixture_completion("success") == 1


def test_move_scenario_uses_the_guided_candidate_path():
    move = _identity_scenarios()["move"]
    assert move["stage"] == "move"
    assert move["check"] == {
        "status": "candidate",
        "error": None,
        "account_id": "1002",
        "character_ids": ["90000000"],
    }
    assert "move_account" not in move
    assert "move_character" not in move
    assert "stage === 'move'" in DEV_JS


def test_identity_harness_doubles_atomic_endpoints_without_alias_compatibility():
    stubbed = _stubbed()
    assert "eve_settings_identification_confirm" in stubbed
    assert "eve_settings_set_account_name" in stubbed
    assert "eve_settings_set_account_characters" in stubbed
    assert "eve_settings_set_account_alias" not in stubbed
    assert "eve_settings_set_account_alias" not in DEV_JS


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


def test_profiles_delayed_mutation_logs_every_received_argument():
    """The generic callback must retain group ids instead of truncating at targets."""
    block = DEV_JS[
        DEV_JS.index("function eveMutation(name) {") : DEV_JS.index(
            "  ['eve_settings_copy'", DEV_JS.index("function eveMutation(name) {")
        )
    ]
    assert re.search(r"return function \(\) \{", block), (
        "the delayed mutation must accept the endpoint's complete argument list"
    )
    assert re.search(
        r"console\.log\('DEV api\.' \+ name \+ '\(',\s*"
        r"Array\.prototype\.slice\.call\(arguments\), '\)'\);",
        block,
        re.DOTALL,
    ), (
        "the delayed mutation must preserve and log all arguments, including "
        "eve_settings_copy's third group-id argument"
    )


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
