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
    assert 'display_meta: "Suartad Arsten + 2 · Account 1001"' in DEV_JS
    character_backup = re.search(
        r"kind: 'character', stem: 'core_char_90000001',\s*"
        r"display_name: '([^']+)', display_meta: 'Character 90000001'",
        DEV_JS,
    )
    assert character_backup and character_backup.group(1) == "Yas Kalkoken", (
        "the character backup must use the name belonging to its file id"
    )


def test_profiles_fixture_covers_new_visual_states():
    for query in ("backups", "copy", "formations-account"):
        assert ".get('" + query + "')" in DEV_JS
    for state in ("empty", "unreadable", "filtered"):
        assert "'" + state + "'" in DEV_JS
    assert "Copy operation in progress" in DEV_JS
    assert "Copy complete" in DEV_JS


def test_filtered_backups_fixture_uses_a_nonmatching_filter():
    scenario = re.search(
        r"if \(backupsScenario === 'filtered'\) \{(.*?)\n      \}", DEV_JS, re.DOTALL
    )
    assert scenario, "the filtered backup fixture is missing"
    assert "no matching backup" in scenario.group(1).lower(), (
        "the filtered checkpoint must render the no-match state, not a matching row"
    )


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


def test_dev_account_labels_use_the_python_identity_data_without_node():
    """The fixture needs the same two account identities without subprocesses.

    pytest's contract is Python-only lexical verification; executing extracted
    JavaScript through an undeclared Node binary made the suite environment
    dependent. The scenario data remains checked by the Python formatter, and
    these assertions pin the JavaScript boundary that consumes it.
    """
    expected = {
        name: _fixture_labels_from_identity_scenario(scenario)
        for name, scenario in _identity_scenarios().items()
    }
    assert expected["idle"]["1001"] == {
        "primary": "alpha@example",
        "secondary": "Suartad Arsten + 2 · Account 1001",
        "option": "alpha@example · Suartad Arsten + 2 · Account 1001",
    }
    assert expected["idle"]["1003"] == {
        "primary": "Account 1003",
        "secondary": "Not identified",
        "option": "Account 1003 · Not identified",
    }
    formatter = re.search(
        r"  function devAccountLabel\(account\) \{(.*?)\n  \}", DEV_JS, re.DOTALL
    )
    assert formatter, "dev.js must format the canonical account identity"
    body = formatter.group(1)
    assert "account.character_ids.map(devKnownCharacter)" in body
    for token in (
        "Account ' + account.id",
        "Not identified",
        "primary + ' · ' + secondary",
    ):
        assert token in body
    builder = re.search(
        r"  function devFixtureAccounts\(scenario\) \{(.*?)\n  \}", DEV_JS, re.DOTALL
    )
    assert builder, "dev.js must derive each scenario's initial account labels"
    for field in ("label.option", "label.primary", "label.secondary"):
        assert field in builder.group(1)
    assert "devAccountLabels" not in DEV_JS
    assert "eve.accounts = devFixtureAccounts(selectedIdentityScenario);" in DEV_JS
    assert "eve.accounts.forEach(refreshDevAccount);" not in DEV_JS


def test_formation_switch_fixture_keeps_its_read_delay_visible():
    """The switch screenshot needs the async gap before it changes account data."""
    load = re.search(
        r"api\.eve_settings_formations = function \(path\) \{(.*?)\n  \};",
        DEV_JS,
        re.DOTALL,
    )
    assert load and "setTimeout(function ()" in load.group(1)
    assert "}, 150);" in load.group(1), (
        "the dev switch checkpoint depends on the 150ms formation-read delay"
    )


def test_copy_fixture_has_stable_busy_and_settled_success_states():
    paint = re.search(
        r"function paintCommit\(\) \{(.*?)\n  \}", EVE_SETTINGS_JS, re.DOTALL
    )
    assert paint and "Copy operation in progress\\u2026" in paint.group(1)
    followup = re.search(r'<div id="es-copy-followup".*?</div>', INDEX_HTML, re.DOTALL)
    assert followup and "Copy complete." in followup.group(0)
    mutation = re.search(
        r"  function eveMutation\(name\) \{(.*?)\n  \}", DEV_JS, re.DOTALL
    )
    assert mutation, "dev.js must retain the delayed mutation fixture"
    body = mutation.group(1)
    guard = "name !== 'eve_settings_copy' || copyScenario !== 'busy'"
    assert guard in body
    assert body.index(guard) < body.index("window.onEveSettingsDone"), (
        "only the busy copy fixture may suppress the completion push"
    )


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


def _eve_select_stub_body() -> str:
    match = re.search(
        r"api\.eve_settings_select = function \(server, profile\) \{(.*?)\n  \};",
        DEV_JS,
        re.DOTALL,
    )
    assert match, "dev.js must double eve_settings_select(server, profile)"
    return re.sub(r"(?m)^\s*//.*$", "", match.group(1))


def test_eve_select_double_treats_an_empty_profile_as_the_servers_first():
    """'' is not "no profile" on this endpoint.

    Api.eve_settings_select hands discover() `profile or None`, and an empty
    token is its one deliberate fallback: the requested server's FIRST
    profile. evesettings.js now depends on that -- its server `change`
    handler sends '' on purpose rather than carrying the old server's
    profile path, which the endpoint would refuse -- so a double that
    assigns the token straight onto eve.profile models a contract the
    bridge does not have. In the harness that reads as a server change
    emptying the Profile select and disabling every control gated on
    `state.profile`, which is not what a real server change does.

    The fixture carries one server and one flat `profiles` list, which IS
    the list offered for the selected server, so its first entry is the
    faithful answer here without inventing a per-server association the
    payload does not carry.
    """
    body = _eve_select_stub_body()
    assert "eve.profile = profile;" not in body, (
        "the double must not assign the raw token: an empty profile is a "
        "request for the server's first profile, not a request for none"
    )
    assert "eve.profiles" in body, (
        "the empty-profile fallback must be derived from the profiles the "
        "fixture offers for that server, not hard-coded"
    )
    assert re.search(r"\bif \(!profile\)|profile \|\|", body), (
        "the double must branch on the empty token explicitly"
    )


def test_eve_select_double_still_honours_an_explicit_profile():
    """The fallback is for the empty token alone. A named profile -- what
    the Profile select itself sends -- is still taken verbatim, or every
    selection would answer with the same first profile and the two-profile
    fixture the copy checkpoints need would be unreachable.
    """
    body = _eve_select_stub_body()
    assert "eve.server = server;" in body
    assert re.search(r"eve\.profile = (?!profile;)\w+;", body), (
        "the double must still record a resolved profile onto the fixture"
    )
    # It answers the way the real endpoint answers an ACCEPTED change; the
    # double never second-guesses Python's own refusals.
    assert "Promise.resolve(true)" in body


# Task 7: the whole-profile copy double. Named by the scenario a session
# needs to eyeball rather than by an implementation detail, so a driver or
# a branch that stops being reachable from any of these names is caught
# rather than silently orphaned.
PROFILE_COPY_SCENARIOS = {
    "multiple": "multiple profiles with Default selected",
    "new-disclosure": "new profile disclosure",
    "replace-disclosure": "replace profile disclosure",
    "invalid-name": "invalid name",
    "collision": "case-insensitive collision",
    "busy": "accepted busy operation",
    "created": "successful create with selected destination",
    "replaced": "successful replace with retained source",
    "eve-running": "EVE-running refusal",
    "rollback-failed": "rollback failure",
    "unsaved-selection": "created profile with unsaved selection",
}


def _profile_copy_stub_body() -> str:
    match = re.search(
        r"api\.eve_settings_copy_profile = function "
        r"\(expectedSource, mode, destination\) \{(.*?)\n  \};",
        DEV_JS,
        re.DOTALL,
    )
    assert match, (
        "dev.js must double eve_settings_copy_profile(expectedSource, mode, destination)"
    )
    return match.group(1)


def _profile_copy_driver_body() -> str:
    match = re.search(
        r"function paintProfileCopyScenario\(\) \{(.*?)\n  \}", DEV_JS, re.DOTALL
    )
    assert match, (
        "dev.js must drive every profile-copy checkpoint through real controls"
    )
    return match.group(1)


def test_profile_copy_double_validates_the_frozen_source_before_anything_else():
    """The stub's own contract, from the brief: a stale expected-source token
    is refused inline, exactly as Api.eve_settings_copy_profile refuses it,
    and never reaches a scenario branch."""
    body = _profile_copy_stub_body()
    guard = (
        "if (expectedSource !== eve.profile) {\n"
        "      return Promise.resolve({ accepted: false, "
        "error: 'The selected profile changed.' });\n"
        "    }"
    )
    assert guard in body
    assert body.index(guard) < body.index("profileCopyScenario")


def test_profile_copy_double_completes_through_the_single_profiles_handler():
    """onEveSettingsDone is the one completion channel for every Profiles
    mutation (test_bridge_contract.py pins this on the Python side); a
    second handler here would let this double drift from what the bridge
    can ever actually send."""
    body = _profile_copy_stub_body()
    assert "window.onEveSettingsDone(" in body
    assert not re.search(r"window\.on(?!EveSettingsDone\b)\w*\(", body), (
        "the profile-copy double must not push any handler but onEveSettingsDone"
    )


def test_profile_copy_scenario_selector_covers_every_named_checkpoint_once():
    assert ".get('profile')" in DEV_JS
    stub = _profile_copy_stub_body()
    driver = _profile_copy_driver_body()
    for key in PROFILE_COPY_SCENARIOS:
        mentions = DEV_JS.count("'" + key + "'")
        assert mentions >= 1, key
    # "multiple" names the base fixture rather than a branch of its own, so
    # it is a driver no-op; every other scenario must appear in BOTH the
    # stub (what happens) and the driver (how a session reaches it).
    for key in PROFILE_COPY_SCENARIOS:
        if key == "multiple":
            continue
        assert "'" + key + "'" in driver, key
    for key in (
        "invalid-name",
        "collision",
        "busy",
        "created",
        "eve-running",
        "rollback-failed",
        "unsaved-selection",
    ):
        assert "'" + key + "'" in stub, key


def test_profile_copy_scenario_requested_reopens_the_profiles_route():
    assert "var profileCopyScenario = identitySearch.get('profile') || '';" in DEV_JS
    assert "|| profileCopyScenario)" in DEV_JS


def test_profile_copy_driver_opens_and_submits_through_real_controls():
    """Every checkpoint but the two disclosures is reached by opening the
    real panel and pressing the real submit button -- never a harness-only
    shortcut a real session could not also take."""
    driver = _profile_copy_driver_body()
    assert "WM.el('es-profile-copy-open').click()" in driver
    assert "WM.el('es-profile-copy-submit').click()" in driver
    assert "WM.el('es-profile-copy-replace').click()" in driver


# Round 1 fix: what the scripted driver actually sends over the bridge for
# every scenario that submits. Pinned here so the stub's own wiring check
# (below) cannot silently drift from what paintProfileCopyScenario() really
# does -- a driver change that stops matching this table, or a stub that
# stops enforcing it, both fail loudly rather than one quietly rendering
# the wrong checkpoint's outcome.
PROFILE_COPY_SCENARIO_REQUESTS = {
    "invalid-name": {"mode": "new", "destination": ""},
    "collision": {"mode": "new", "destination": "dEfAuLt"},
    "busy": {"mode": "new", "destination": "New Ops"},
    "created": {"mode": "new", "destination": "New Ops"},
    "unsaved-selection": {"mode": "new", "destination": "New Ops"},
    "eve-running": {"mode": "new", "destination": "New Ops"},
    "replaced": {"mode": "replace", "destination": "fleet"},
    "rollback-failed": {"mode": "replace", "destination": "fleet"},
}


def _profile_copy_scenario_requests() -> dict:
    match = re.search(
        r"var PROFILE_COPY_SCENARIO_REQUESTS = \{(.*?)\n  \};", DEV_JS, re.DOTALL
    )
    assert match, (
        "dev.js must declare the scripted per-scenario mode/destination table "
        "the wiring check below validates against"
    )
    body = match.group(1)
    entries = re.findall(
        r"'([a-z-]+)':\s*\{\s*mode:\s*'([a-z]+)',\s*destination:\s*'([^']*)'\s*\}",
        body,
    )
    assert entries, "the scenario request table must be parseable"
    return {
        key: {"mode": mode, "destination": destination}
        for key, mode, destination in entries
    }


def test_profile_copy_scripted_requests_match_the_scenario_driver_exactly():
    """Pins the exact mode/destination each scripted checkpoint sends,
    including the collision fixture's case-varied 'dEfAuLt' against the
    existing 'Default' profile -- a same-case duplicate would never
    exercise the case-insensitive comparison this checkpoint exists to
    show."""
    assert _profile_copy_scenario_requests() == PROFILE_COPY_SCENARIO_REQUESTS


def test_profile_copy_collision_scenario_types_a_case_varied_name():
    """The collision checkpoint must not merely retype the exact existing
    name -- it has to prove the comparison is case-insensitive, which only
    a differently-cased collision can show."""
    driver = _profile_copy_driver_body()
    assert "WM.el('es-profile-copy-name').value = 'dEfAuLt';" in driver
    assert "WM.el('es-profile-copy-name').value = 'Default';" not in driver
    requests = _profile_copy_scenario_requests()
    assert requests["collision"]["destination"] == "dEfAuLt"
    assert requests["collision"]["destination"].casefold() == "default"
    # And the existing profile it collides with really is spelled
    # differently on disk, not the same string the driver typed.
    assert "{ path: 'default', name: 'Default', file_count: 72 }" in DEV_JS


def test_profile_copy_double_refuses_a_scripted_mode_or_destination_mismatch():
    """A sender-wiring regression -- sendProfileCopy shipping the wrong mode,
    or reading the wrong field's value -- must be refused rather than
    silently accepted and rendered as if the intended checkpoint had fired.
    This is a bridge-argument check only: it must not evaluate whether a
    name is well-formed or a destination genuinely exists, which stays
    Python's job."""
    stub = _profile_copy_stub_body()
    assert "PROFILE_COPY_SCENARIO_REQUESTS[profileCopyScenario]" in stub
    assert "mode !== expectedRequest.mode" in stub
    assert "destination !== expectedRequest.destination" in stub
    # The check must run before ANY scenario-specific branch, so a mismatch
    # is refused instead of falling into some other checkpoint's canned
    # response.
    wiring_check = stub.index("expectedRequest")
    assert wiring_check < stub.index("profileCopyScenario === 'invalid-name'")
    assert wiring_check < stub.index("profileCopyScenario === 'collision'")
    assert wiring_check < stub.index("profileCopyScenario === 'busy'")
    # No production validation logic (name rules, real collisions) may leak
    # into this generic check -- it only ever compares against the fixed
    # per-scenario table above.
    guard = stub[
        wiring_check : stub.index("\n    if (profileCopyScenario === 'invalid-name')")
    ]
    assert "validate_friendly_name" not in guard
    assert "MAX_FRIENDLY_NAME_CHARS" not in guard


def test_profile_copy_invalid_name_and_collision_are_canned_not_computed():
    """Scenario-specific branches may return the approved inline errors, but
    must not perform filesystem-like validation in JavaScript -- so neither
    branch may examine the destination or mode it was actually sent."""
    stub = _profile_copy_stub_body()
    invalid = re.search(
        r"if \(profileCopyScenario === 'invalid-name'\) \{(.*?)\n    \}",
        stub,
        re.DOTALL,
    )
    assert invalid, "the invalid-name checkpoint must have its own branch"
    assert "Profile name cannot be empty." in invalid.group(1)
    assert "destination" not in invalid.group(1)
    collision = re.search(
        r"if \(profileCopyScenario === 'collision'\) \{(.*?)\n    \}",
        stub,
        re.DOTALL,
    )
    assert collision, "the collision checkpoint must have its own branch"
    assert "already exists" in collision.group(1)


def test_profile_copy_busy_scenario_never_settles():
    """The accepted-busy checkpoint exists to show the disabled controls
    while a copy is in flight, so its own branch must suppress the
    completion push the way the character-copy busy fixture already does."""
    stub = _profile_copy_stub_body()
    assert "if (profileCopyScenario === 'busy') return;" in stub
    assert stub.index("if (profileCopyScenario === 'busy') return;") < stub.index(
        "window.onEveSettingsDone("
    )


def test_profile_copy_created_scenario_selects_the_new_destination():
    """Mirrors Api.eve_settings_copy_profile: a successful creation adds the
    new profile to the list AND moves the selection onto it."""
    stub = _profile_copy_stub_body()
    created = re.search(
        r"if \(profileCopyScenario === 'created'\) \{(.*?)\n      \}",
        stub,
        re.DOTALL,
    )
    assert created, "the created checkpoint must have its own branch"
    body = created.group(1)
    assert "eve.profiles = eve.profiles.concat(" in body
    assert "eve.profile = createdProfile.path;" in body


def test_profile_copy_replaced_scenario_never_moves_the_selection():
    """Replacement never moves the selection (design's own rule), so the
    only `eve.profile =` assignment anywhere in the double must belong to
    the created/unsaved-selection creation paths, never to replace."""
    stub = _profile_copy_stub_body()
    assignments = re.findall(r"eve\.profile = [^;]+;", stub)
    assert assignments == ["eve.profile = createdProfile.path;"], assignments


def test_profile_copy_eve_running_refusal_matches_the_python_message():
    stub = _profile_copy_stub_body()
    running = re.search(
        r"if \(profileCopyScenario === 'eve-running'\) \{(.*?)\n      \}",
        stub,
        re.DOTALL,
    )
    assert running, "the eve-running checkpoint must have its own branch"
    body = running.group(1)
    assert "payload.ok = false;" in body
    assert "payload.published = false;" in body
    assert "EVE is running. Close EVE and retry." in body


def test_profile_copy_rollback_failure_names_backups_as_the_recovery_path():
    """The message a caught, unrecovered publication failure shows: the
    archive is now the only way back, and Backups is where it is restored
    from -- see Api._eve_copy_profile_worker's own \"Restore ... from
    Backups\" wording."""
    stub = _profile_copy_stub_body()
    rollback = re.search(
        r"if \(profileCopyScenario === 'rollback-failed'\) \{(.*?)\n      \}",
        stub,
        re.DOTALL,
    )
    assert rollback, "the rollback-failed checkpoint must have its own branch"
    body = rollback.group(1)
    assert "payload.ok = false;" in body
    assert "payload.published = false;" in body
    assert "could not put it back" in body
    assert "from Backups." in body


def test_profile_copy_unsaved_selection_matches_the_python_warning():
    """Api._eve_select_created_profile's own failure text: the profile
    exists and is offered back, but the selection itself was not saved."""
    stub = _profile_copy_stub_body()
    unsaved = re.search(
        r"if \(profileCopyScenario === 'unsaved-selection'\) \{(.*?)\n      \}",
        stub,
        re.DOTALL,
    )
    assert unsaved, "the unsaved-selection checkpoint must have its own branch"
    body = unsaved.group(1)
    assert "payload.selection_persisted = false;" in body
    assert "could not remember the selection" in body
    assert "Select it from Profile." in body
    # And it must NOT move the selection -- that is exactly what it failed
    # to do.
    assert "eve.profile = " not in body


def test_the_base_profiles_fixture_offers_a_second_profile_for_replace_targets():
    """Every profile-copy checkpoint needs a real replace target, and
    'multiple profiles with Default selected' names this as its own
    checkpoint: the single-profile fixture before this task could never
    show the Replace disclosure's destination dropdown populated."""
    match = re.search(r"profiles: \[(.*?)\],\n", DEV_JS, re.DOTALL)
    assert match, "dev.js must declare the fixture's profiles list"
    paths = re.findall(r"path: '([^']+)'", match.group(1))
    names = re.findall(r"name: '([^']+)'", match.group(1))
    assert len(paths) >= 2, "the fixture needs a second profile as a replace target"
    assert "Default" in names
    assert "server: 'tq', profile: 'default'," in DEV_JS


def _dev_preview_fixture() -> dict:
    """Parse DEV_PREVIEW_HOTKEYS_FIXTURE from dev.js as a Python dict.

    The fixture is a strict JSON-compatible object literal (double-quoted
    keys/strings, no JS-specific syntax inside the body), so json.loads
    works directly on the extracted block.
    """
    import json as _json

    marker = "DEV_PREVIEW_HOTKEYS_FIXTURE"
    assert marker in DEV_JS, f"{marker} not found in dev.js"
    raw = DEV_JS[DEV_JS.index(marker) :]
    brace_start = raw.index("{")
    depth = 0
    end = brace_start
    for i, ch in enumerate(raw[brace_start:], brace_start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    body = raw[brace_start : end + 1]
    return _json.loads(body)


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

    The fixture is now a named JSON literal (DEV_PREVIEW_HOTKEYS_FIXTURE);
    gestures are extracted by parsing the JSON rather than regex-scanning
    the getter body.
    """
    from wingman.preview import gestures as preview_gestures

    fixture = _dev_preview_fixture()
    hotkeys = fixture.get("hotkeys", {})
    # Collect all gesture strings: character binds + cycle_next/prev + group cycles
    all_gestures: set[str] = set()
    all_gestures.update(v for v in hotkeys.get("characters", {}).values() if v)
    if hotkeys.get("cycle_next"):
        all_gestures.add(hotkeys["cycle_next"])
    if hotkeys.get("cycle_prev"):
        all_gestures.add(hotkeys["cycle_prev"])
    all_gestures.update(g["cycle"] for g in hotkeys.get("groups", []) if g.get("cycle"))
    assert all_gestures, "the preview fixture declares no gesture strings"
    for gesture in sorted(all_gestures):
        parsed = preview_gestures.parse(gesture)
        assert parsed is not None, (
            f"dev.js's preview fixture holds {gesture!r}, which "
            "preview/gestures.py cannot parse"
        )
        assert preview_gestures.display(parsed) == gesture, (
            f"dev.js's preview fixture holds {gesture!r}, which is not the "
            "canonical spelling the app would store"
        )


def test_the_preview_fixture_carries_online_and_offline_layout_sources():
    """The fixture must carry both an online and an offline layout source.

    The fixture is now a named JSON literal; check via JSON parse.
    """
    fixture = _dev_preview_fixture()
    sources = fixture.get("layout_sources", [])
    assert sources, "fixture must have layout_sources"
    assert any(s.get("online") for s in sources), (
        "fixture must have at least one online layout source"
    )
    assert any(not s.get("online") for s in sources), (
        "fixture must have at least one offline layout source"
    )
    assert "copy_preview_layout" in _stubbed()


def test_preview_fixture_covers_the_roster_states_screenshots_need():
    """Keep the authoritative fixture representative rather than tiny.

    The capture tool injects this exact JSON into the real page. A short,
    uniform roster hides scrolling, the offline divider, unavailable geometry,
    direct-bind sharing, and a collision until a user's own state happens to
    expose one of them.
    """
    fixture = _dev_preview_fixture()
    roster = fixture["roster"]
    online = set(fixture["characters"])
    offline = set(roster) - online
    hotkeys = fixture["hotkeys"]
    direct = hotkeys["characters"]

    assert len(roster) >= 10
    assert online and offline
    assert any(len(name) >= 30 for name in roster)
    assert hotkeys["group_by_character"]
    assert set(roster) & set(fixture["sizable"])
    assert set(roster) - set(fixture["sizable"])
    long_name = "Aleksandrina Shadowbanes Voidstriders"
    assert long_name in roster
    assert long_name not in fixture["excluded"], (
        "the staged Copy target must have an enabled Copy control"
    )
    assert any(source["name"] != long_name for source in fixture["layout_sources"])

    by_gesture = {}
    for name, gesture in direct.items():
        by_gesture.setdefault(gesture, []).append(name)
    assert any(len(names) >= 2 for names in by_gesture.values()), (
        "fixture needs a supported shared direct-character bind"
    )
    assert any(
        gesture in {hotkeys["cycle_next"], hotkeys["cycle_prev"]}
        for gesture in direct.values()
    ), "fixture needs a direct-character/cycle-keybind conflict"


def test_preview_fixture_covers_a_named_group_cycle_conflict():
    """The same screenshot fixture must also exercise a named-group
    keybind collision, not just the direct-character/cycle conflict above.

    The warning-ownership fix (Task 2) applies uniformly to character,
    cycle, and named-group rows; only a real collision in each keeps the
    screenshot actually showing one.
    """
    fixture = _dev_preview_fixture()
    groups = fixture["hotkeys"]["groups"]
    by_cycle = {}
    for group in groups:
        cycle = group.get("cycle")
        if cycle:
            by_cycle.setdefault(cycle, []).append(group["name"])
    assert any(len(names) >= 2 for names in by_cycle.values()), (
        "fixture needs two named groups sharing one cycle keybind, so a "
        "named-group conflict warning actually renders in the screenshot"
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


def test_the_preview_groups_fixture_covers_real_states():
    """The preview fixture must carry cycle groups, not just the old hotkeys.

    The five group-mutation methods are no longer known gaps -- dev.js now
    doubles them.  This test pins the fixture data those stubs read from.

    The fixture is now a named JSON literal (DEV_PREVIEW_HOTKEYS_FIXTURE);
    assertions use the JSON parse helper.
    """
    from wingman.preview import gestures as preview_gestures

    fixture = _dev_preview_fixture()
    hotkeys = fixture.get("hotkeys", {})
    assert hotkeys.get("groups"), "preview fixture lacks groups array"
    assert hotkeys.get("group_by_character"), (
        "preview fixture lacks group_by_character map"
    )
    # At least one group must carry a real parseable cycle gesture.
    gestures_in_groups = [g["cycle"] for g in hotkeys["groups"] if g.get("cycle")]
    assert gestures_in_groups, "no group has a cycle gesture in the fixture"
    for gesture in gestures_in_groups:
        parsed = preview_gestures.parse(gesture)
        assert parsed is not None, (
            f"preview fixture group holds {gesture!r}, which gestures.py cannot parse"
        )
        assert preview_gestures.display(parsed) == gesture, (
            f"preview fixture group holds {gesture!r}, not canonical spelling"
        )
    # Named groups must include at least a DPS group and an empty group.
    names = [g["name"] for g in hotkeys["groups"]]
    assert any("DPS" in n for n in names), (
        "preview fixture lacks a group with 'DPS' in its name"
    )
    assert any("Empty" in n or "empty" in n for n in names), (
        "preview fixture lacks an empty group"
    )
    # The UI label 'All only' is derived by the page, not persisted.
    assert "All only" not in str(fixture), (
        "'All only' is a UI label and must not appear in the fixture"
    )


def test_the_preview_group_dev_methods_are_no_longer_known_gaps():
    """The five group-mutation methods were in the known-gaps list while
    dev.js lacked stubs for them.  Task 5 adds the stubs, so they must
    no longer appear in the known-gaps list AND they must be stubbed.
    """
    stubbed = _stubbed()
    for method in (
        "create_preview_cycle_group",
        "rename_preview_cycle_group",
        "delete_preview_cycle_group",
        "set_preview_cycle_group_bind",
        "set_preview_character_group",
    ):
        assert method in stubbed, (
            f"dev.js does not stub {method!r} -- it is still a known gap"
        )


# ---------------------------------------------------------------------------
# Round 1 fix: fixture consolidation, data correctness, async push, contracts
# ---------------------------------------------------------------------------


def test_preview_fixture_is_consolidated_into_named_literal():
    """dev.js must declare a single named object literal DEV_PREVIEW_HOTKEYS_FIXTURE
    that is strict JSON-compatible (no JS-specific syntax like single quotes,
    trailing commas, or unquoted keys inside the literal body).

    Both the dev getter and the mutable _devPreviewHotkeys must derive from it.
    """
    assert "DEV_PREVIEW_HOTKEYS_FIXTURE" in DEV_JS, (
        "dev.js must declare a top-level var DEV_PREVIEW_HOTKEYS_FIXTURE "
        "so shoot_screens.py can parse it as the screenshot payload"
    )
    # The named literal must be the source for the getter and mutable state.
    getter_block = DEV_JS[DEV_JS.index("api.get_preview_hotkey_state") :]
    getter_block = getter_block[: getter_block.index("\n  };")]
    assert "DEV_PREVIEW_HOTKEYS_FIXTURE" in getter_block, (
        "get_preview_hotkey_state must deep-copy from DEV_PREVIEW_HOTKEYS_FIXTURE, "
        "not maintain a separate inline literal"
    )


def test_preview_fixture_excluded_character_is_also_assigned_to_a_group():
    """The fixture must contain at least one character who is BOTH in
    excluded[] AND in group_by_character, proving the page handles the
    opted-out-but-still-assigned state correctly.

    The current fixture only excludes Zuelo (who has no group assignment)
    and omits this combination entirely.
    """
    import json as _json

    # Extract the canonical fixture from the named literal
    marker = "DEV_PREVIEW_HOTKEYS_FIXTURE"
    assert marker in DEV_JS, "DEV_PREVIEW_HOTKEYS_FIXTURE must be declared"
    raw = DEV_JS[DEV_JS.index(marker) :]
    # Find the JSON body: from the opening { to the matching }
    brace_start = raw.index("{")
    depth = 0
    end = brace_start
    for i, ch in enumerate(raw[brace_start:], brace_start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    body = raw[brace_start : end + 1]
    fixture = _json.loads(body)

    excluded = fixture.get("excluded", [])
    group_by_character = fixture.get("hotkeys", {}).get("group_by_character", {})

    excluded_and_assigned = [c for c in excluded if c in group_by_character]
    assert excluded_and_assigned, (
        "fixture must have at least one character who is both excluded[] "
        "and in group_by_character — currently no such character exists, "
        "so the opted-out-but-assigned state is never exercised"
    )


def test_preview_fixture_nonexcluded_character_without_group_assignment():
    """The fixture must contain at least one character who is NOT excluded
    AND NOT in group_by_character (the All-only path for an opted-in character).

    The current fixture has Zuelo as excluded + unassigned, but needs a
    distinct non-excluded unassigned character to exercise the All-only
    path separately from the excluded path.
    """
    import json as _json

    marker = "DEV_PREVIEW_HOTKEYS_FIXTURE"
    assert marker in DEV_JS
    raw = DEV_JS[DEV_JS.index(marker) :]
    brace_start = raw.index("{")
    depth = 0
    end = brace_start
    for i, ch in enumerate(raw[brace_start:], brace_start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    body = raw[brace_start : end + 1]
    fixture = _json.loads(body)

    roster = fixture.get("roster", [])
    excluded = set(fixture.get("excluded", []))
    group_by_character = fixture.get("hotkeys", {}).get("group_by_character", {})

    nonexcluded_unassigned = [
        c for c in roster if c not in excluded and c not in group_by_character
    ]
    assert nonexcluded_unassigned, (
        "fixture must have at least one roster member who is neither excluded "
        "nor in group_by_character -- the All-only path for an opted-in character "
        "is not exercised otherwise"
    )


def test_preview_dev_push_is_asynchronous():
    """_devPushHotkeys must use setTimeout(..., 0) to defer the push.

    A synchronous push during a mutation response means the handler runs
    inside the promise resolution, which can cause re-entrant renders and
    makes the push timing non-deterministic with respect to callers.
    Production Api._push is fired from a worker thread (effectively async);
    the dev harness must match that behaviour.
    """
    # Find the _devPushHotkeys function body
    marker = "function _devPushHotkeys"
    assert marker in DEV_JS, "_devPushHotkeys must be defined in dev.js"
    start = DEV_JS.index(marker)
    # Find the matching closing brace of this function
    brace_start = DEV_JS.index("{", start)
    depth = 0
    end = brace_start
    for i, ch in enumerate(DEV_JS[brace_start:], brace_start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    body = DEV_JS[start : end + 1]
    assert "setTimeout" in body, (
        "_devPushHotkeys must use setTimeout(..., 0) to match the async "
        "behaviour of production Api._push -- currently it calls "
        "onPreviewHotkeys synchronously"
    )


def test_preview_group_result_shape_has_all_four_required_fields():
    """_devGroupResult must return an object with exactly the four fields
    the page contracts on: applied (bool), persisted (bool), error (str|null),
    hotkeys (object).

    A partial result silently breaks the page's mutation handlers, which
    check res.applied and res.hotkeys but also pass res.error to alert_bookmarks.
    """
    marker = "function _devGroupResult"
    assert marker in DEV_JS, "_devGroupResult must be defined in dev.js"
    start = DEV_JS.index(marker)
    brace_start = DEV_JS.index("{", start)
    depth = 0
    end = brace_start
    for i, ch in enumerate(DEV_JS[brace_start:], brace_start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    body = DEV_JS[start : end + 1]
    for field in ("applied", "persisted", "error", "hotkeys"):
        assert field in body, (
            f"_devGroupResult must include the '{field}' field "
            "to match the production Api._preview_group_result shape"
        )


def test_preview_group_delete_cleans_up_group_by_character():
    """delete_preview_cycle_group must remove all group_by_character entries
    that reference the deleted group.

    Leaving stale entries means characters appear assigned to a non-existent
    group, which the page cannot recover from gracefully.
    """
    marker = "api.delete_preview_cycle_group"
    assert marker in DEV_JS, "delete_preview_cycle_group must be stubbed"
    start = DEV_JS.index(marker)
    # Find the function body (the assigned function)
    fn_start = DEV_JS.index("function", start)
    brace_start = DEV_JS.index("{", fn_start)
    depth = 0
    end = brace_start
    for i, ch in enumerate(DEV_JS[brace_start:], brace_start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    body = DEV_JS[start : end + 1]
    assert "group_by_character" in body, (
        "delete_preview_cycle_group must clean up group_by_character entries "
        "for the deleted group -- stale references break the character-row selects"
    )
    # Must remove entries (delete or reassign)
    assert "delete" in body or "splice" in body, (
        "delete_preview_cycle_group must remove stale group_by_character entries"
    )


def test_preview_dev_push_sends_full_state_not_just_hotkeys():
    """_devPushHotkeys must push the full state payload (with enabled, roster,
    excluded, etc.) not just the hotkeys sub-object.

    onPreviewHotkeys replaces state wholesale, so a push with only the
    hotkeys sub-keys as top-level fields loses enabled, roster, excluded,
    and other required state, breaking the full re-render after a mutation.
    """
    marker = "function _devPushHotkeys"
    assert marker in DEV_JS, "_devPushHotkeys must be defined in dev.js"
    start = DEV_JS.index(marker)
    brace_start = DEV_JS.index("{", start)
    depth = 0
    end = brace_start
    for i, ch in enumerate(DEV_JS[brace_start:], brace_start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    body = DEV_JS[start : end + 1]
    # Must reference the full fixture (not just _devPreviewHotkeys directly)
    # to build the full state payload before pushing it to onPreviewHotkeys.
    assert "DEV_PREVIEW_HOTKEYS_FIXTURE" in body, (
        "_devPushHotkeys must build the full state from DEV_PREVIEW_HOTKEYS_FIXTURE "
        "so onPreviewHotkeys receives enabled, roster, excluded, etc. -- "
        "currently it pushes only the hotkeys sub-object"
    )


# ---------------------------------------------------------------------------
# Round 2 fix: exact contracts — result types, delay value, payload delivery,
# per-method mutation & push, selector determinism
# ---------------------------------------------------------------------------


def _matching_brace(source: str, opening: int) -> int:
    """Return the matching brace while ignoring braces in JS strings/comments."""
    assert source[opening] == "{"
    depth = 0
    quote = None
    escaped = False
    line_comment = False
    block_comment = False
    i = opening
    while i < len(source):
        char = source[i]
        following = source[i + 1] if i + 1 < len(source) else ""
        if line_comment:
            line_comment = char != "\n"
        elif block_comment:
            if char == "*" and following == "/":
                block_comment = False
                i += 1
        elif quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        elif char == "/" and following == "/":
            line_comment = True
            i += 1
        elif char == "/" and following == "*":
            block_comment = True
            i += 1
        elif char in {"'", '"'}:
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise AssertionError(f"unbalanced JS body beginning at offset {opening}")


def _extract_fn_body(marker: str) -> str:
    """Brace-match one specific function and return only its body."""
    assert marker in DEV_JS, f"{marker!r} must be defined in dev.js"
    start = DEV_JS.index(marker)
    opening = DEV_JS.index("{", start)
    closing = _matching_brace(DEV_JS, opening)
    return DEV_JS[opening + 1 : closing]


def _extract_callback_body(source: str, marker: str) -> str:
    """Brace-match the callback introduced by marker within one function."""
    start = source.index(marker)
    opening = source.index("{", start)
    closing = _matching_brace(source, opening)
    return source[opening + 1 : closing]


def _normalise_js(source: str) -> str:
    """Remove comments and insignificant whitespace for exact lexical contracts."""
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    source = re.sub(r"(?m)^\s*//.*$", "", source)
    return re.sub(r"\s+", "", source)


def test_preview_group_result_success_values_are_correct_types():
    """_devGroupResult(true, null) must return applied:true, persisted:true,
    error:null (not undefined, not "null", not false).

    The page checks `res.applied` as a truthy boolean and passes `res.error`
    to an alert path; wrong types cause silent UI failures.
    """
    body = _extract_fn_body("function _devGroupResult")
    # Success path: applied and persisted must both be the parameter (true for
    # success) and error must coalesce null not undefined.
    assert "applied: applied" in body or "applied:applied" in body, (
        "_devGroupResult must set applied from its parameter, not hardcode it"
    )
    assert "persisted: applied" in body or "persisted:applied" in body, (
        "_devGroupResult must mirror applied into persisted"
    )
    # error must handle null explicitly (not `error: error` which would be
    # undefined when omitted, not null)
    assert (
        "error: error || null" in body
        or "error:error||null" in body
        or ("|| null" in body)
    ), "_devGroupResult must coalesce error to null: `error: error || null`"
    # hotkeys must be a deep copy (not a direct reference)
    assert "_devHotkeysCopy" in body or "JSON.parse" in body, (
        "_devGroupResult must deep-copy hotkeys via _devHotkeysCopy() or JSON.parse"
    )


def test_preview_dev_push_settimeout_delay_is_exactly_zero():
    """_devPushHotkeys must use setTimeout(function..., 0) — not 1, not 50,
    not a named variable.

    A non-zero delay means the push fires visibly later than a production
    push (which is effectively zero latency from the page's perspective),
    breaking timing parity with real mutation handlers.
    """
    body = _extract_fn_body("function _devPushHotkeys")
    # Find the setTimeout call and extract its delay argument.
    # Pattern: setTimeout(function () { ... }, <delay>)
    match = re.search(r"setTimeout\s*\([^,]+,\s*(\d+)\s*\)", body, re.DOTALL)
    assert match, "_devPushHotkeys must call setTimeout with an explicit numeric delay"
    delay = int(match.group(1))
    assert delay == 0, (
        f"_devPushHotkeys uses setTimeout delay {delay}, must be exactly 0 "
        "to match production timing"
    )


def test_preview_dev_push_calls_onPreviewHotkeys_inside_callback():
    """onPreviewHotkeys must be called inside the setTimeout callback,
    not outside it.

    If it is called outside the callback the push is still synchronous and
    the reason for the setTimeout is defeated.
    """
    body = _extract_fn_body("function _devPushHotkeys")
    # Find the setTimeout block and check that onPreviewHotkeys is inside it.
    # We look for the pattern: setTimeout(function () { ... onPreviewHotkeys ... }, 0)
    settimeout_match = re.search(
        r"setTimeout\s*\(function\s*\(\)\s*\{(.*?)\}\s*,\s*0\s*\)",
        body,
        re.DOTALL,
    )
    assert settimeout_match, (
        "_devPushHotkeys must have a setTimeout(function () {...}, 0) block"
    )
    callback_body = settimeout_match.group(1)
    assert "onPreviewHotkeys" in callback_body, (
        "onPreviewHotkeys must be called inside the setTimeout callback in "
        "_devPushHotkeys, not in the outer function body"
    )


def test_preview_dev_push_substitutes_current_hotkeys_into_full_fixture():
    """_devPushHotkeys must substitute _devPreviewHotkeys (current mutable
    state) into a deep copy of the full fixture before pushing.

    Pattern: full = deep_copy(DEV_PREVIEW_HOTKEYS_FIXTURE);
             full.hotkeys = _devHotkeysCopy();
             onPreviewHotkeys(full);
    This ensures the push carries enabled, roster, excluded, etc. from
    the canonical fixture, with the mutation applied to the hotkeys field.
    """
    body = _extract_fn_body("function _devPushHotkeys")
    # Must deep-copy the full fixture
    assert "DEV_PREVIEW_HOTKEYS_FIXTURE" in body, (
        "_devPushHotkeys must deep-copy from DEV_PREVIEW_HOTKEYS_FIXTURE"
    )
    # Must assign .hotkeys on the copy (not pass _devPreviewHotkeys directly)
    assert ".hotkeys" in body, (
        "_devPushHotkeys must assign .hotkeys on the full-fixture copy to "
        "substitute the current mutable state"
    )


def test_preview_create_method_mutates_groups_and_calls_push_and_result():
    """create_preview_cycle_group must: push a new group onto _devPreviewHotkeys.groups,
    call _devPushHotkeys(), and return _devGroupResult(true, null) on success.
    """
    body = _extract_fn_body("api.create_preview_cycle_group")
    # Must mutate groups (push or append)
    assert ".push(" in body, (
        "create_preview_cycle_group must push a new group onto groups array"
    )
    # Must call the shared push helper
    assert "_devPushHotkeys" in body, (
        "create_preview_cycle_group must call _devPushHotkeys() "
        "to broadcast the mutation"
    )
    # Must return via the shared result helper
    assert "_devGroupResult" in body, (
        "create_preview_cycle_group must return _devGroupResult(...) "
        "for a consistent result shape"
    )


def test_preview_rename_method_mutates_target_and_calls_push_and_result():
    """rename_preview_cycle_group must: find the group by id and update its
    name field, call _devPushHotkeys(), and return _devGroupResult on success.
    """
    body = _extract_fn_body("api.rename_preview_cycle_group")
    # Must assign a .name property on the found target
    assert ".name" in body, (
        "rename_preview_cycle_group must assign .name on the found group"
    )
    assert "_devPushHotkeys" in body, (
        "rename_preview_cycle_group must call _devPushHotkeys() "
        "to broadcast the mutation"
    )
    assert "_devGroupResult" in body, (
        "rename_preview_cycle_group must return _devGroupResult(...) "
        "for a consistent result shape"
    )


def test_preview_bind_method_mutates_cycle_and_calls_push_and_result():
    """set_preview_cycle_group_bind must: find the group by id and update its
    cycle field, call _devPushHotkeys(), and return _devGroupResult on success.
    """
    body = _extract_fn_body("api.set_preview_cycle_group_bind")
    # Must assign .cycle on the found target
    assert ".cycle" in body, (
        "set_preview_cycle_group_bind must assign .cycle on the found group"
    )
    assert "_devPushHotkeys" in body, (
        "set_preview_cycle_group_bind must call _devPushHotkeys() "
        "to broadcast the mutation"
    )
    assert "_devGroupResult" in body, (
        "set_preview_cycle_group_bind must return _devGroupResult(...) "
        "for a consistent result shape"
    )


def test_preview_assignment_method_mutates_gbc_and_calls_push_and_result():
    """set_preview_character_group must: update group_by_character (or delete
    entry for All-only), call _devPushHotkeys(), and return _devGroupResult.
    """
    body = _extract_fn_body("api.set_preview_character_group")
    # Must mutate group_by_character
    assert "group_by_character" in body, (
        "set_preview_character_group must mutate group_by_character"
    )
    assert "_devPushHotkeys" in body, (
        "set_preview_character_group must call _devPushHotkeys() "
        "to broadcast the mutation"
    )
    assert "_devGroupResult" in body, (
        "set_preview_character_group must return _devGroupResult(...) "
        "for a consistent result shape"
    )


def test_load_dev_preview_fixture_payload_equals_dev_fixture_parsed_by_test_helper():
    """load_dev_preview_fixture() (from shoot_screens.py) must return the
    exact same dict that the test helper _dev_preview_fixture() returns.

    Both parse the same DEV_PREVIEW_HOTKEYS_FIXTURE literal; any divergence
    means one of them is reading a different source or applying different
    parsing, which would cause the screenshot scripts to embed different
    data than what the tests verify.
    """
    import importlib.util
    import pathlib as _pathlib

    path = _pathlib.Path(__file__).resolve().parents[1] / "scripts" / "shoot_screens.py"
    spec = importlib.util.spec_from_file_location("shoot_screens", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    fixture_from_test_helper = _dev_preview_fixture()
    fixture_from_shoot = mod.load_dev_preview_fixture()
    assert fixture_from_shoot == fixture_from_test_helper, (
        "load_dev_preview_fixture() must return the same dict as the test "
        "helper -- both parse DEV_PREVIEW_HOTKEYS_FIXTURE from dev.js; "
        "a divergence means screenshot payload ≠ test-verified fixture"
    )


# ---------------------------------------------------------------------------
# Round 3 fix: strict contracts — exact keys, exact patterns, exact mutations
# ---------------------------------------------------------------------------


def test_preview_group_result_returns_exactly_four_keys():
    """_devGroupResult must return an object with EXACTLY four keys:
    applied, persisted, error, hotkeys — no more, no less.

    Any extra key (e.g. a debug field) or missing key silently breaks the
    page's mutation handler, which destructures all four.

    Strategy: parse the return-object literal from the function body and
    count the keys.  A change to five or three fails immediately.
    """
    body = _extract_fn_body("function _devGroupResult")
    # Strip line comments
    body = re.sub(r"(?m)^\s*//.*$", "", body)
    # Find the return { ... } block — the outermost object literal in the body
    ret_match = re.search(r"return\s*\{([^}]+)\}", body, re.DOTALL)
    assert ret_match, "_devGroupResult must return an object literal"
    obj_text = ret_match.group(1)
    # Extract key names: "key: ..." at comma-separated boundaries
    keys = [m.group(1).strip() for m in re.finditer(r"(\w+)\s*:", obj_text)]
    assert set(keys) == {"applied", "persisted", "error", "hotkeys"}, (
        f"_devGroupResult must return EXACTLY {{applied, persisted, error, hotkeys}}, "
        f"got {set(keys)!r} -- an extra or missing key breaks the page's mutation handler"
    )
    assert len(keys) == 4, (
        f"_devGroupResult has {len(keys)} keys, expected exactly 4: {keys!r}"
    )


def test_preview_group_result_hotkeys_from_copy_helper():
    """_devGroupResult must derive hotkeys from _devHotkeysCopy(), not from
    a direct reference to _devPreviewHotkeys or a bare JSON.parse.

    A direct reference allows the caller to mutate the returned object's
    hotkeys and affect future pushes; JSON.parse without the shared helper
    would work but bypasses the single copy-helper convention.
    """
    body = _extract_fn_body("function _devGroupResult")
    body = re.sub(r"(?m)^\s*//.*$", "", body)
    ret_match = re.search(r"return\s*\{([^}]+)\}", body, re.DOTALL)
    assert ret_match
    obj_text = ret_match.group(1)
    # hotkeys value must be _devHotkeysCopy()
    hotkeys_val = re.search(r"hotkeys\s*:\s*(.+?)(?:,|$)", obj_text, re.DOTALL)
    assert hotkeys_val, "hotkeys key not found in _devGroupResult object"
    val = hotkeys_val.group(1).strip().rstrip(",").strip()
    assert "_devHotkeysCopy" in val, (
        f"_devGroupResult hotkeys must be '_devHotkeysCopy()', got {val!r} -- "
        "a direct reference or bare JSON.parse bypasses the copy-helper convention"
    )


def test_preview_group_result_success_applied_true_persisted_true_error_null():
    """On the success path _devGroupResult(true, null) must embed the exact
    literals true, true, null — not false, not undefined, not a truthy string.

    applied: applied  → parameter mirrors through  → must be true for success
    persisted: applied → mirrors applied            → must be true for success
    error: error || null → coerces to null when no error passed
    """
    body = _extract_fn_body("function _devGroupResult")
    body = re.sub(r"(?m)^\s*//.*$", "", body)
    # persisted must mirror applied (not be hardcoded true or false)
    assert re.search(r"persisted\s*:\s*applied", body), (
        "_devGroupResult persisted must be 'applied' (mirrors parameter), not hardcoded"
    )
    # error must coerce to null via || null
    assert re.search(r"error\s*:\s*error\s*\|\|\s*null", body), (
        "_devGroupResult error must be 'error || null' to coerce undefined→null"
    )


def test_preview_dev_push_builds_full_copy_from_named_fixture():
    """_devPushHotkeys must create its full-state copy via:
        var full = JSON.parse(JSON.stringify(DEV_PREVIEW_HOTKEYS_FIXTURE));

    Any other pattern (e.g. spread, Object.assign, or copying _devPreviewHotkeys
    directly) either skips the non-hotkeys fields or fails to deep-copy nested
    objects.
    """
    body = _extract_fn_body("function _devPushHotkeys")
    body = re.sub(r"(?m)^\s*//.*$", "", body)
    # Must find the exact JSON.parse(JSON.stringify(DEV_PREVIEW_HOTKEYS_FIXTURE)) pattern
    assert re.search(
        r"JSON\.parse\s*\(\s*JSON\.stringify\s*\(\s*DEV_PREVIEW_HOTKEYS_FIXTURE\s*\)\s*\)",
        body,
    ), (
        "_devPushHotkeys must deep-copy the fixture via "
        "JSON.parse(JSON.stringify(DEV_PREVIEW_HOTKEYS_FIXTURE)) -- "
        "other patterns skip top-level non-hotkeys fields"
    )


def test_preview_dev_push_assigns_hotkeys_field_on_full_copy():
    """After the deep copy, _devPushHotkeys must assign the current mutable
    state via:  full.hotkeys = _devHotkeysCopy();

    The variable name 'full' and field name 'hotkeys' are the contract.
    Assigning to a different variable name means onPreviewHotkeys receives
    the stale fixture hotkeys, not the mutated ones.
    """
    body = _extract_fn_body("function _devPushHotkeys")
    body = re.sub(r"(?m)^\s*//.*$", "", body)
    # Must assign _devHotkeysCopy() into the .hotkeys field of the full copy
    assert re.search(r"full\.hotkeys\s*=\s*_devHotkeysCopy\(\)", body), (
        "_devPushHotkeys must assign 'full.hotkeys = _devHotkeysCopy()' "
        "on the full-fixture copy before pushing"
    )


def test_preview_dev_push_calls_window_onpreviewhotkeys_with_full():
    """Inside the setTimeout callback _devPushHotkeys must call
    window.onPreviewHotkeys(full)  — with the 'full' variable, not 'hotkeys'
    or '_devPreviewHotkeys' or any other argument.

    Passing the wrong variable sends an incomplete payload to the page and
    breaks the full-state-replace contract.
    """
    body = _extract_fn_body("function _devPushHotkeys")
    body = re.sub(r"(?m)^\s*//.*$", "", body)
    # Locate the setTimeout callback body
    cb_match = re.search(
        r"setTimeout\s*\(function\s*\(\)\s*\{(.*?)\}\s*,\s*0\s*\)",
        body,
        re.DOTALL,
    )
    assert cb_match, "_devPushHotkeys must use setTimeout(function(){...}, 0)"
    cb = cb_match.group(1)
    # Must call onPreviewHotkeys with 'full' as the sole argument
    assert re.search(r"onPreviewHotkeys\s*\(\s*full\s*\)", cb), (
        "_devPushHotkeys must call window.onPreviewHotkeys(full) inside "
        "the setTimeout callback -- passing any other variable breaks the "
        "full-state-replace contract"
    )


def test_preview_create_appends_full_group_object_with_id_name_cycle():
    """create_preview_cycle_group must append a complete group object containing
    all three required fields: id, name, cycle.

    Missing any field leaves the group manager with a malformed entry:
    - missing 'id' makes delete/rename/bind fail (they match by id)
    - missing 'name' breaks display immediately
    - missing 'cycle' causes nil-binding errors on the bind endpoint
    """
    body = _extract_fn_body("api.create_preview_cycle_group")
    body = re.sub(r"(?m)^\s*//.*$", "", body)
    # Find the groups.push({...}) call and verify all three fields are present
    push_match = re.search(r"\.push\s*\(\{([^}]*)\}\s*\)", body)
    assert push_match, (
        "create_preview_cycle_group must call groups.push({...}) "
        "to append the new group"
    )
    obj_text = push_match.group(1)
    for field in ("id", "name", "cycle"):
        assert re.search(rf"\b{field}\b\s*:", obj_text), (
            f"create_preview_cycle_group push object must include '{field}' field -- "
            "missing it leaves a malformed group entry"
        )


def test_preview_rename_assigns_name_field_on_located_group():
    """rename_preview_cycle_group must assign target.name (or group.name) after
    locating the group by id — not mutate a copy or append a new field.

    A rename that reassigns to a new variable or uses object spread would
    leave the original groups entry unchanged.
    """
    body = _extract_fn_body("api.rename_preview_cycle_group")
    body = re.sub(r"(?m)^\s*//.*$", "", body)
    # Must find an assignment of the form <var>.name = ...
    assert re.search(r"\w+\.name\s*=\s*\w", body), (
        "rename_preview_cycle_group must assign '.name' on the located group object "
        "(e.g. 'target.name = clean') -- a copy or spread won't mutate in-place"
    )


def test_preview_bind_assigns_cycle_field_on_located_group():
    """set_preview_cycle_group_bind must assign target.cycle (or group.cycle)
    after locating the group by id — not append a new property or rebuild.
    """
    body = _extract_fn_body("api.set_preview_cycle_group_bind")
    body = re.sub(r"(?m)^\s*//.*$", "", body)
    # Must find an assignment of the form <var>.cycle = ...
    assert re.search(r"\w+\.cycle\s*=\s*", body), (
        "set_preview_cycle_group_bind must assign '.cycle' on the located group object "
        "-- a copy or spread won't mutate in-place"
    )


def test_preview_assignment_both_sets_and_deletes_group_by_character():
    """set_preview_character_group must handle BOTH paths:
    - assign path:  gbc[name] = groupId  (character joins a group)
    - remove path:  delete gbc[name]      (character returns to All-only)

    A method that only supports one path silently ignores the other,
    leaving the character perpetually assigned or perpetually in All-only.
    """
    body = _extract_fn_body("api.set_preview_character_group")
    body = re.sub(r"(?m)^\s*//.*$", "", body)
    # Assignment path: gbc[name] = groupId (or equivalent bracket notation)
    assert re.search(r"gbc\s*\[\s*name\s*\]\s*=", body) or re.search(
        r"group_by_character\s*\[\s*name\s*\]\s*=", body
    ), (
        "set_preview_character_group must have an assignment path: "
        "gbc[name] = groupId — missing it means a character can never join a group"
    )
    # Delete path: delete gbc[name]
    assert re.search(r"delete\s+gbc\s*\[\s*name\s*\]", body) or re.search(
        r"delete\s+group_by_character\s*\[\s*name\s*\]", body
    ), (
        "set_preview_character_group must have a delete path: delete gbc[name] — "
        "missing it means a character can never return to All-only"
    )


def test_preview_delete_iterates_gbc_and_deletes_each_member():
    """delete_preview_cycle_group must iterate group_by_character (via forEach,
    for..in, or Object.keys loop) and delete every entry whose value matches
    the deleted group's id.

    Simply splicing the group from groups[] without cleaning up gbc leaves
    stale character assignments pointing to a ghost group id.

    This test is crafted to catch the exact membership-cleanup contract:
    it checks for both the iteration and the targeted delete, so removing
    just the forEach/cleanup loop causes a failure.
    """
    body = _extract_fn_body("api.delete_preview_cycle_group")
    body = re.sub(r"(?m)^\s*//.*$", "", body)
    # Must splice (remove group from array)
    assert "groups.splice" in body or ".splice(" in body, (
        "delete_preview_cycle_group must splice the group from the groups array"
    )
    # Must iterate gbc — forEach, for..in, or Object.keys are all acceptable
    assert re.search(r"forEach|for\s*\(|Object\.keys", body), (
        "delete_preview_cycle_group must iterate group_by_character "
        "(via forEach, for..in, or Object.keys) to remove stale memberships"
    )
    # Must delete (not just reassign) the stale gbc entries
    assert re.search(r"delete\s+gbc\s*\[", body) or re.search(
        r"delete\s+group_by_character\s*\[", body
    ), (
        "delete_preview_cycle_group must delete stale gbc entries -- "
        "reassignment or filtering without delete leaves ghost ids"
    )
    # Verify the per-entry check targets the deleted groupId (not a generic delete)
    assert "groupId" in body or "group_id" in body, (
        "delete_preview_cycle_group gbc cleanup must check the entry value "
        "against the deleted groupId -- blanket delete removes all assignments"
    )


def test_preview_delete_membership_cleanup_is_load_bearing():
    """Demonstrate that the membership-cleanup check in
    test_preview_delete_iterates_gbc_and_deletes_each_member is not satisfied
    by a body that only splices the group.

    This test is a mutation proof: we construct a minimal function body that
    performs only the splice (no forEach/delete) and verify it FAILS the
    membership-cleanup assertions.  The test itself should always PASS.
    """
    # Construct a stripped body that only splices groups — no cleanup loop
    minimal_body = (
        "api.delete_preview_cycle_group = function (groupId) {\n"
        "  var groups = _devPreviewHotkeys.groups;\n"
        "  var idx = -1;\n"
        "  for (var i = 0; i < groups.length; i++) {\n"
        "    if (groups[i].id === groupId) { idx = i; break; }\n"
        "  }\n"
        "  if (idx === -1) { return; }\n"
        "  groups.splice(idx, 1);\n"  # splice only — no gbc cleanup
        "  _devPushHotkeys();\n"
        "  return _devGroupResult(true, null);\n"
        "}"
    )
    # The forEach / for..in / Object.keys requirement must NOT be satisfied
    has_iteration = bool(re.search(r"forEach|for\s*\(|Object\.keys", minimal_body))
    # The delete gbc requirement must NOT be satisfied
    has_delete = bool(
        re.search(r"delete\s+gbc\s*\[", minimal_body)
        or re.search(r"delete\s+group_by_character\s*\[", minimal_body)
    )
    # BOTH must be absent in the minimal body to prove the tests are non-trivial
    assert not has_iteration or not has_delete, (
        "Minimal splice-only body unexpectedly satisfies the cleanup checks -- "
        "the test assertions may be too loose to catch a missing cleanup loop"
    )


# ---------------------------------------------------------------------------
# Round 4: brace-matched, normalised contracts that tie every operation to
# the lifecycle method's own parameters and local state.
# ---------------------------------------------------------------------------


def test_preview_group_result_is_the_exact_production_shape():
    body = _normalise_js(_extract_fn_body("function _devGroupResult"))
    assert body == (
        "return{applied:applied,persisted:applied,error:error||null,"
        "hotkeys:_devHotkeysCopy()};"
    )


def test_preview_group_success_lifecycle_uses_exact_result_arguments():
    markers = (
        "api.create_preview_cycle_group",
        "api.rename_preview_cycle_group",
        "api.delete_preview_cycle_group",
        "api.set_preview_cycle_group_bind",
        "api.set_preview_character_group",
    )
    result = "returnPromise.resolve(_devGroupResult(true,null));"
    for marker in markers:
        body = _normalise_js(_extract_fn_body(marker))
        assert body.count(result) == 1, (
            f"{marker} must return exactly one _devGroupResult(true, null) "
            "from its success path"
        )
        assert body.index("_devPushHotkeys();") < body.index(result), (
            f"{marker} must schedule its hotkeys push before returning success"
        )


def test_preview_dev_push_callback_has_exact_order_and_single_delivery():
    body = _extract_fn_body("function _devPushHotkeys")
    callback = _normalise_js(_extract_callback_body(body, "setTimeout(function"))
    copy = "varfull=JSON.parse(JSON.stringify(DEV_PREVIEW_HOTKEYS_FIXTURE));"
    assign = "full.hotkeys=_devHotkeysCopy();"
    deliver = "window.onPreviewHotkeys(full);"

    assert callback.count(copy) == 1
    assert callback.count(assign) == 1
    assert callback.count(deliver) == 1
    assert _normalise_js(body).count(deliver) == 1
    assert callback.index(copy) < callback.index(assign) < callback.index(deliver)


def test_preview_create_appends_exact_group_from_its_locals_before_push():
    body = _normalise_js(_extract_fn_body("api.create_preview_cycle_group"))
    make_id = "varid='g-dev-'+Date.now();"
    append = "groups.push({id:id,name:clean,cycle:''});"
    push = "_devPushHotkeys();"
    assert body.count(make_id) == 1
    assert body.count("groups.push(") == 1
    assert body.count(append) == 1
    assert body.index(make_id) < body.index(append) < body.index(push)


def _assert_target_group_mutation(marker: str, assignment: str) -> None:
    body = _normalise_js(_extract_fn_body(marker))
    locate = "if(groups[i].id===groupId){target=groups[i];break;}"
    assert body.count(locate) == 1, (
        f"{marker} must locate target from the group whose id equals groupId"
    )
    assert body.count(assignment) == 1, (
        f"{marker} must mutate that located target with {assignment}"
    )
    field = "name" if ".name=" in assignment else "cycle"
    assert re.findall(rf"(?:\w+|\w+\[[^]]+\])\.{field}=", body) == [f"target.{field}="]
    assert (
        body.index(locate) < body.index(assignment) < body.index("_devPushHotkeys();")
    )


def test_preview_rename_updates_only_the_group_located_by_group_id():
    _assert_target_group_mutation(
        "api.rename_preview_cycle_group", "target.name=clean;"
    )


def test_preview_bind_updates_only_the_group_located_by_group_id():
    _assert_target_group_mutation(
        "api.set_preview_cycle_group_bind", "target.cycle=gesture||'';"
    )


def test_preview_assignment_branches_use_requested_name_and_group_id():
    body = _normalise_js(_extract_fn_body("api.set_preview_character_group"))
    branches = _normalise_js(
        """
        if (!groupId) {
          delete gbc[name];
        } else {
          var valid = false;
          for (var i = 0; i < groups.length; i++) {
            if (groups[i].id === groupId) { valid = true; break; }
          }
          if (!valid) {
            return Promise.resolve(_devGroupResult(false, 'No group with id \\'' + groupId + '\\''));
          }
          gbc[name] = groupId;
        }
        """
    )
    assert body.count(branches) == 1
    assert body.count("deletegbc[") == 1
    assert body.count("deletegbc[name];") == 1
    assert re.findall(r"gbc\[[^]]+\]=", body) == ["gbc[name]="]
    assert body.count("gbc[name]=groupId;") == 1
    assert body.index(branches) < body.index("_devPushHotkeys();")


def test_preview_delete_removes_matched_group_and_only_its_memberships():
    body = _extract_fn_body("api.delete_preview_cycle_group")
    normal = _normalise_js(body)
    locate = "if(groups[i].id===groupId){idx=i;break;}"
    remove = "groups.splice(idx,1);"
    callback = _normalise_js(
        _extract_callback_body(body, "Object.keys(gbc).forEach(function (charName)")
    )

    assert normal.count(locate) == 1
    assert normal.count("groups.splice(") == 1
    assert normal.count(remove) == 1
    assert callback == "if(gbc[charName]===groupId){deletegbc[charName];}"
    assert normal.count("deletegbc[") == 1
    assert normal.count("deletegbc[charName];") == 1
    assert (
        normal.index(locate) < normal.index(remove) < normal.index("Object.keys(gbc)")
    )
    assert normal.index("Object.keys(gbc)") < normal.index("_devPushHotkeys();")


# ---- dev harness: identification generation contract (Round 1 HIGH) ------


def test_dev_fake_state_exposes_account_identity_available():
    """The page now gates canIdentify and es-account-tools on
    state.account_identity_available (Task 6).  The dev harness always
    points at a Tranquility fixture, so this flag must be true or every
    identity scenario renders with all controls hidden.
    """
    assert "account_identity_available: true" in DEV_JS, (
        "dev.js does not set account_identity_available: true in the eve fake "
        "state; identity controls will be hidden in every dev fixture"
    )


def test_dev_identification_generation_counter_exists():
    """Task 5 added identification_generation to every identification
    response.  The dev harness must carry a monotonic counter so that
    acceptIdentification() in evesettings.js does not reject every stub
    response as having no numeric generation field.
    """
    assert "var devIdentificationGeneration = 0;" in DEV_JS, (
        "dev.js has no devIdentificationGeneration counter; every "
        "identification stub response will be rejected by acceptIdentification()"
    )


def test_dev_identification_start_returns_identification_generation():
    """Start bumps the counter and returns it; a stale check from before
    the start is then rejected on the next acceptIdentification call.
    """
    start_body = DEV_JS.split("api.eve_settings_identification_start", 1)[1].split(
        "\n  };\n", 1
    )[0]
    assert "devIdentificationGeneration += 1" in start_body, (
        "eve_settings_identification_start does not bump devIdentificationGeneration"
    )
    assert "identification_generation: devIdentificationGeneration" in start_body, (
        "eve_settings_identification_start does not include identification_generation "
        "in its resolve payload"
    )


def test_dev_identification_cancel_returns_identification_generation():
    """Cancel bumps the counter (matching Python semantics) and returns it
    so that acceptIdentification() on the resolved promise advances the
    retained generation and any racing check resolving later is rejected.
    """
    cancel_body = DEV_JS.split("api.eve_settings_identification_cancel", 1)[1].split(
        "\n  };\n", 1
    )[0]
    assert "devIdentificationGeneration += 1" in cancel_body, (
        "eve_settings_identification_cancel does not bump devIdentificationGeneration"
    )
    assert "identification_generation: devIdentificationGeneration" in cancel_body, (
        "eve_settings_identification_cancel does not include "
        "identification_generation in its resolve payload"
    )


def test_dev_push_eve_names_carries_generation_and_deleted_ids():
    """The devPushEveNames helper (used by DEV console helpers that mutate
    eve state) must pass identification_generation and deleted_candidate_ids
    so that onEveSettingsNames' acceptIdentification gate passes and the
    push is not silently dropped.
    """
    assert "function devPushEveNames()" in DEV_JS, (
        "dev.js has no devPushEveNames helper"
    )
    helper_body = DEV_JS.split("function devPushEveNames()", 1)[1].split("}", 1)[0]
    assert "identification_generation: devIdentificationGeneration" in helper_body, (
        "devPushEveNames does not include identification_generation"
    )
    assert "deleted_candidate_ids: []" in helper_body, (
        "devPushEveNames does not include deleted_candidate_ids"
    )


def test_dev_console_eve_helpers_use_dev_push_eve_names():
    """eveNoFolder, eveUnreadable, and eveSelectiveAvailable all mutate
    eve and then push onEveSettingsNames.  After Task 6 that push must
    carry identification_generation, so they must go through
    devPushEveNames rather than calling window.onEveSettingsNames() bare.
    """
    for helper in ("eveNoFolder", "eveUnreadable", "eveSelectiveAvailable"):
        block = DEV_JS.split(helper + ":", 1)[1].split("\n    },", 1)[0]
        assert "devPushEveNames()" in block, (
            f"DEV.{helper} still calls window.onEveSettingsNames() bare "
            "instead of devPushEveNames()"
        )
        assert "window.onEveSettingsNames()" not in block, (
            f"DEV.{helper} calls window.onEveSettingsNames() without a payload"
        )


# ---- evesettings.js: hidden-route deleted-candidate guard (Round 1 MEDIUM) -


def test_deleted_candidate_paint_is_guarded_by_identity_route_open():
    """When a deletion push arrives while the account-identity sub-screen
    is closed, the page must clear local state silently rather than calling
    paintIdentification, which tries to focus an off-screen heading.  The
    paint/focus call must only happen when identityRouteOpen is true.
    """
    src = EVE_SETTINGS_JS
    handler = src.split("WM.handle('onEveSettingsNames'", 1)[1].split("\n  });", 1)[0]
    invalid_branch = handler.split("invalidatesCandidate", 1)[1].split("\n    }", 1)[0]
    assert "identityRouteOpen" in invalid_branch, (
        "the invalidatesCandidate branch in onEveSettingsNames does not check "
        "identityRouteOpen before calling paintIdentification; a deletion push "
        "while on another screen will try to focus an off-screen heading"
    )
    assert "if (identityRouteOpen)" in invalid_branch, (
        "identityRouteOpen check must be an explicit if-guard in the "
        "invalidatesCandidate branch"
    )
