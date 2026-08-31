# Profiles Copy-First Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Profiles a focused EVE-settings copy workflow, with account identities that are safe to recognize and dedicated Profiles-owned Backups and Formations subroutes.

**Architecture:** Keep `evesettings.js` as the sole owner of Profiles state, backup rendering, backup mutations, and `onEveSettingsDone`. Add one chromeless `backups` route in the existing router, move backup markup there without adding a bridge endpoint, and pass the existing account payload explicitly into `formations.js`. Preserve Python ownership of copy outcomes and all filesystem safety rules.

**Tech Stack:** Python 3.11+, plain HTML/CSS/ES5 JavaScript, pywebview 6.2.1, pytest lexical UI tests, Ruff, Windows WebView2 manual verification.

**Spec:** `docs/superpowers/specs/2026-08-31-profiles-copy-first-design.md`

## Global Constraints

- Windows-only, dark-only desktop UI with a minimum 840×625 CSS viewport at every display scaling.
- No framework, build step, bundler, or new runtime dependency.
- `evesettings.js` remains the only owner of `onEveSettingsDone`.
- Every new route belongs in `WM.route`; every Profiles-owned route belongs in `WM.EVE_ROUTES`; chromeless children belong in `WM.CHROMELESS_ROUTES`.
- Python owns filesystem validation, containment, EVE-running enforcement, backup-first mutation, pruning, formation validation, and successful-copy quantities.
- Do not change copy, restore, pruning, formation validation, or backup-file semantics.
- Do not infer backup events from timestamps or add per-target copy progress.
- Use `.check` and `.radio` wrappers, token colors only, visible `:focus-visible`, and explicit `[hidden]` overrides where a selector sets `display`.
- The page has no executable JavaScript test harness. Extend lexical tests and complete the Windows smoke pass.

## File map

- `wingman/evesettings/identity.py`: canonical account display identity.
- `wingman/ui/api.py`: canonical identity propagation into backup payloads.
- `wingman/web/index.html`: Profiles shell, Backups subroute, copy follow-up, and formation account selector markup.
- `wingman/web/app.js`: route registration, Profiles-child highlighting, chromeless routing, and EVE-gate eviction.
- `wingman/web/evesettings.js`: Profiles and Backups state/rendering, filtering, disclosures, copy labels, and completion follow-up.
- `wingman/web/formations.js`: session account list, account switching, dirty confirmation, and load-failure recovery.
- `wingman/web/style.css`: context/tool layout, Backups route, disclosure menu, copy feedback, and formation rail selector.
- `wingman/web/dev.js`: deterministic visual fixtures for new routes and states.
- `scripts/shoot_screens.py`: Backups route capture.
- `tests/test_evesettings_identity.py`: Python account-label contract.
- `tests/test_profiles_page.py`: Profiles and Backups lexical contracts.
- `tests/test_page_conventions.py`: route ownership and single-handler invariants.
- `tests/test_dev_harness.py`: fixture coverage and production-shape assertions.
- `tests/test_shoot_screens.py`: screenshot inventory and EVE-gate counts.
- `docs/smoke-checklist.md`: rendered and Windows-only checks.

---

### Task 1: Make account identity recognizable on every surface

**Files:**
- Modify: `wingman/evesettings/identity.py:88-112`
- Modify: `wingman/ui/api.py:3772-3832`
- Modify: `tests/test_evesettings_identity.py:17-36`
- Modify: `tests/test_api_evesettings.py:983-1005`
- Test: `tests/test_evesettings_identity.py`
- Test: `tests/test_api_evesettings.py`

**Interfaces:**
- Consumes: `account_identity(account_id: str, account_names: dict, associations: dict, character_name: Callable) -> dict`
- Produces: one canonical `{primary, secondary, option}` representation consumed by `Api._eve_identity()`, source options, target rows, copy confirmations, and formation account choices; `_eve_backup_identity()` explicitly preserves its primary and secondary strings in backup payloads.

- [ ] **Step 1: Add failing tests for both reachable account states**

Persisted character links require a named account, so do not add a formatter-only linked-but-unnamed case. Replace the two current display tests with explicit named and unknown cases:

```python
def test_named_account_leads_with_name_and_keeps_roster_and_id_secondary():
    got = identity.account_identity(
        "10",
        {"10": "LoginName"},
        {"10": ["20", "21", "22"]},
        lambda ident: {"20": "Aiga", "21": "Beta", "22": "Gamma"}[ident],
    )
    assert got == {
        "primary": "LoginName",
        "secondary": "Aiga + 2 · Account 10",
        "option": "LoginName · Aiga + 2 · Account 10",
    }


def test_unknown_account_never_renders_as_a_bare_number():
    assert identity.account_identity("10", {}, {}, lambda _ident: "unused") == {
        "primary": "Account 10",
        "secondary": "Not identified",
        "option": "Account 10 · Not identified",
    }
```

- [ ] **Step 2: Run the identity tests and verify the expected failures**

Run:

```bash
uv sync --locked --extra dev
uv run --no-sync python -m pytest tests/test_evesettings_identity.py -q
```

Expected: both display tests fail because IDs are currently emitted without the `Account` noun and unknown accounts have no secondary status.

- [ ] **Step 3: Update the canonical identity composition**

Implement the branch structure in `account_identity()` without changing its return shape:

```python
if account_name:
    primary = account_name
    secondary_parts = [character_summary] if character_summary else []
    secondary_parts.append(f"Account {account_id}")
else:
    primary = f"Account {account_id}"
    secondary_parts = ["Not identified"]
secondary = " · ".join(secondary_parts)
```

Keep `option` derived from `primary` and `secondary`; do not add page-side identity formatting.

Update `_eve_backup_identity()` so an account backup returns the canonical identity without replacing its secondary text:

```python
identity = self._eve_identity(f"{item.stem}.dat")
return identity["primary"], identity["secondary"]
```

Retain the existing character and profile behavior. Add API tests showing that a named account backup carries its character summary plus `Account <id>`, while an unidentified backup carries `Account <id>` plus `Not identified` without duplicating the ID.

- [ ] **Step 4: Run identity and API tests**

Run:

```bash
uv run --no-sync python -m pytest tests/test_evesettings_identity.py tests/test_api_evesettings.py -q
```

Expected: PASS. Update API expectations only where they assert the old canonical account labels.

- [ ] **Step 5: Commit the identity contract**

```bash
git add wingman/evesettings/identity.py wingman/ui/api.py \
  tests/test_evesettings_identity.py tests/test_api_evesettings.py
git commit -m "fix: make EVE account identities recognizable"
```

---

### Task 2: Establish the copy-first route structure

**Files:**
- Modify: `wingman/web/index.html:1180-1591`
- Modify: `wingman/web/app.js:135-205,262`
- Modify: `wingman/web/evesettings.js:570-673,1051-1150`
- Modify: `wingman/web/style.css:2470-2983,3607-3667`
- Modify: `tests/test_profiles_page.py`
- Modify: `tests/test_page_conventions.py:2338-2390`
- Test: `tests/test_profiles_page.py`
- Test: `tests/test_page_conventions.py`

**Interfaces:**
- Produces route name `backups`, DOM route `route-backups`, entry control `es-backups-open`, Back control `es-backups-back`, and the existing backup IDs moved intact.
- Preserves existing IDs used by `evesettings.js`: `es-backup-profile`, `es-auto-keep`, `es-auto-keep-apply`, `es-auto-keep-status`, `es-backup-note`, `es-backup-head`, `es-backups`, and `es-backups-more`.

- [ ] **Step 1: Add failing route and markup tests**

Add `BACKUPS_ROUTE` extraction beside `ACCOUNT_ROUTE` in `tests/test_profiles_page.py`, then assert:

```python
def test_profiles_opens_backups_without_mounting_the_archive_inline():
    assert 'id="es-backups-open"' in BODY
    assert '<h2>Backups</h2>' not in BODY
    assert "function openBackups()" in CODE
    assert "WM.route('backups')" in CODE


def test_backups_is_a_chromeless_profiles_subroute():
    assert 'id="route-backups"' in HTML
    assert "backups: 'route-backups'" in APP
    assert 'data-route="backups"' not in HTML
    for declaration in ("WM.CHROMELESS_ROUTES", "WM.EVE_ROUTES"):
        block = re.search(declaration + r" = \[([^]]+)\]", APP)
        assert block and "'backups'" in block.group(1)
    assert "name === 'backups'" in APP
```

Update existing backup-card tests to inspect `BACKUPS_ROUTE` rather than `BODY`. Keep the test that verifies the copy promise remains on the main Profiles route.

- [ ] **Step 2: Run the route tests and verify they fail**

Run:

```bash
uv run --no-sync python -m pytest \
  tests/test_profiles_page.py \
  tests/test_page_conventions.py::test_the_formation_editor_is_a_route_the_title_bar_never_shows \
  -q
```

Expected: FAIL because `route-backups` and the new tool controls do not exist.

- [ ] **Step 3: Move markup and register the route**

In `index.html`:

- Give the folder card a dedicated `es-context-card` class.
- Add an `es-profile-tools` row after the context card with `es-backups-open`.
- Leave the existing Probe Formations card and `es-formations-account` selector intact until Task 5, so this commit has no dead formation references.
- Move the complete Backups card into a new sibling `<div class="route" id="route-backups">`.
- Add a Backups header containing `<button class="btn" id="es-backups-back">&lsaquo; Profiles</button>` and `<h1>Backups</h1>`.
- Move the existing backup controls and list intact. Task 3 adds filtering and the retention disclosure so this route-shell commit contains no inert controls.

In `app.js`:

```javascript
WM.CHROMELESS_ROUTES = ['firstrun', 'formations', 'accountidentity', 'backups'];
```

Add `backups: 'route-backups'` to the route map, treat it as a Profiles child in the `lit` calculation, and add it to `WM.EVE_ROUTES`.

In `evesettings.js`, add a minimal working entry and exit before committing the shell:

```javascript
function openBackups() {
  backupVisible = 20;
  WM.route('backups');
  renderBackups();
  refresh();
}
```

Wire `es-backups-open` to `openBackups` and `es-backups-back` to `WM.route('evesettings')`. Treat `backups` as a state-fetching route in the existing `wm:route` listener, without registering another bridge handler.

- [ ] **Step 4: Implement the layout without changing behavior**

In `style.css`:

- Remove the Profiles-only backup-card width rules that assumed the card lived in the main route.
- Make `.es-context-card` use the available route width while retaining path truncation.
- Add `.es-profile-tools` as a wrapping, quiet action row outside the copy card.
- Give `#route-backups` one route-level scrollbar and a bounded content column with an uncapped backup list.
- Style `#es-retention` and its summary as a standard disclosure, not a nested card.
- Leave the formation rail geometry unchanged until Task 5.
- Add explicit `[hidden]` overrides for every new selector that sets `display`.

- [ ] **Step 5: Run focused route tests**

Run:

```bash
uv run --no-sync python -m pytest tests/test_profiles_page.py tests/test_page_conventions.py -q
```

Expected: PASS. The moved backup tests must still enforce one scrollbar, full-width rows, and the shared retention note.

- [ ] **Step 6: Commit the route shell**

```bash
git add wingman/web/index.html wingman/web/app.js wingman/web/evesettings.js \
  wingman/web/style.css tests/test_profiles_page.py tests/test_page_conventions.py
git commit -m "refactor: split Profiles tools into focused routes"
```

---

### Task 3: Implement the Backups subroute and accessible row actions

**Files:**
- Modify: `wingman/web/index.html:1387-1440`
- Modify: `wingman/web/evesettings.js:570-673,740-780,1051-1150`
- Modify: `wingman/web/style.css:2528-2590,2949-2983`
- Modify: `tests/test_profiles_page.py`
- Test: `tests/test_profiles_page.py`

**Interfaces:**
- Consumes: existing `openBackups()`, `state.backups`, `state.auto_keep`, `mutate(method, ...)`, and the existing backup bridge methods.
- Produces: `backupMatches(item, needle)` and one page-owned backup route using the existing `onEveSettingsDone` registration.

- [ ] **Step 1: Add failing lexical tests for route ownership and filtering**

Add tests that require `evesettings.js`, rather than a new module, to own the route:

```python
def test_backups_route_reuses_profiles_state_and_completion_owner():
    assert "WM.route('backups')" in CODE
    assert "event.detail === 'backups'" in CODE
    assert CODE.count("WM.handle('onEveSettingsDone'") == 1
    assert "WM.formationsDone" in CODE


def test_backup_filter_matches_tokens_and_visible_words():
    matcher = re.search(r"function backupMatches\(item, needle\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert matcher
    body = matcher.group(1)
    for value in ("display_name", "display_meta", "item.kind", "item.origin", "Automatic", "Manual"):
        assert value in body


def test_backup_actions_use_an_accessible_disclosure():
    render = re.search(r"function renderBackups\(\) \{(.*?)\n  \}", CODE, re.DOTALL)
    assert render
    body = render.group(1)
    assert "details" in body and "summary" in body
    assert "aria-label" in body
    assert "Escape" in body
    assert ".focus()" in body
```

Also add assertions for `No backups match this filter`, `Clear filter`, and one-open-at-a-time disclosure behavior.

- [ ] **Step 2: Run the backup tests and verify they fail**

Run:

```bash
uv run --no-sync python -m pytest tests/test_profiles_page.py -q
```

Expected: FAIL because filtering, the Backups route hooks, and disclosure rows are absent.

- [ ] **Step 3: Add Backups route state and filtering**

In `index.html`, add `es-backup-filter` and `es-backup-filter-clear` above the list, and wrap the existing retention controls in a native `<details id="es-retention">` disclosure.

In `evesettings.js`, add page-owned state:

```javascript
var backupFilter = '';
var backupVisible = 20;

function backupMatches(item, needle) {
  var origin = item.origin === 'auto' ? 'Automatic' : 'Manual';
  return [item.display_name, item.display_meta, item.kind, item.origin, origin]
    .join(' ').toLowerCase().indexOf(needle) !== -1;
}
```

`renderBackups()` must filter before slicing, keep `backupVisible` relative to the filtered list, distinguish no backups from no matches, and derive both backup-note mount points from the existing single `note` string.

Extend `openBackups()` to clear the filter before resetting `backupVisible`, routing, rendering, and refreshing state. Wire:

- `es-backup-filter` input to update `backupFilter` and rerender.
- `es-backup-filter-clear` to clear the field and rerender.
- Route entry for `backups` to refresh state and resolve names without resetting copy selections or the copy-complete follow-up.

- [ ] **Step 4: Replace repeated Delete buttons with row disclosures**

For each backup row, build a native `details` element with a `summary` trigger and one Delete button. Use an accessible label containing `item.display_name` and `whenText(item.created)`. On toggle, close every other open backup disclosure. On Escape:

```javascript
if (event.key === 'Escape' && menu.open) {
  menu.open = false;
  trigger.focus();
}
```

Keep Restore as the visible `.btn`. Keep Delete as `.btn danger` inside the disclosure and call the existing `eve_settings_delete_backup` mutation. Do not register another bridge handler.

- [ ] **Step 5: Add focused disclosure and filter styles**

Use existing tokens and button/menu geometry. Ensure:

- Closed summaries have a clear hover and focus state.
- The open menu does not use backdrop blur or a new color palette.
- `[hidden]` wins wherever new rules set `display`.
- Rows retain aligned Date, Target, and Actions tracks.
- The route owns scrolling.

- [ ] **Step 6: Run backup and convention tests**

Run:

```bash
uv run --no-sync python -m pytest tests/test_profiles_page.py tests/test_page_conventions.py -q
```

Expected: PASS, including exactly one `onEveSettingsDone` owner.

- [ ] **Step 7: Commit the Backups subroute behavior**

```bash
git add wingman/web/index.html wingman/web/evesettings.js wingman/web/style.css \
  tests/test_profiles_page.py
git commit -m "feat: add focused Profiles backup manager"
```

---

### Task 4: Clarify copy scope and lifecycle feedback

**Files:**
- Modify: `wingman/web/index.html:1286-1385`
- Modify: `wingman/web/evesettings.js:18-220,680-790,797-850,1037-1050,1138-1150`
- Modify: `wingman/web/style.css:2822-2955`
- Modify: `tests/test_profiles_page.py`
- Test: `tests/test_profiles_page.py`

**Interfaces:**
- Consumes: existing `chosenTargets()`, `mutate()`, global Python status, and `onEveSettingsDone({ok})`.
- Produces: `pendingMutation`, `copyFollowup`, dynamic copy-button labels, and `es-copy-followup` with `es-copy-view-backups`.
- Does not change the bridge payload or infer successful counts.

- [ ] **Step 1: Add failing tests for exact copy semantics and labels**

Update the selective-copy assertion and add lifecycle checks:

```python
def test_selective_copy_explains_recognized_and_other_settings():
    assert (
        "Checked groups are copied as a unit. Unchecked groups stay unchanged. "
        "Everything else is copied."
    ) in BODY


def test_bulk_controls_name_their_scope():
    assert '>Select shown</button>' in BODY
    assert '>Clear selection</button>' in BODY


def test_copy_button_and_followup_do_not_infer_python_results():
    paint = re.search(r"function paintCommit\(\) \{(.*?)\n  \}", CODE, re.DOTALL).group(1)
    assert "Copy to " in paint
    assert "Copy operation in progress" in paint
    assert 'id="es-copy-followup"' in BODY
    assert 'id="es-copy-view-backups"' in BODY
    assert "backups created" not in CODE.lower()
```

Add a test proving the follow-up is set only when `pendingMutation === 'eve_settings_copy' && payload.ok`, survives routing to Backups and back, and clears on source, kind, server, profile, root, or a new copy. Also assert that successful backup, restore, retention, and formation operations do not clear the copy target selection.

- [ ] **Step 2: Run the copy-page tests and verify they fail**

Run:

```bash
uv run --no-sync python -m pytest tests/test_profiles_page.py -q
```

Expected: FAIL on old labels, old explanatory copy, static button text, and missing follow-up.

- [ ] **Step 3: Update copy markup and rendering**

In `index.html`:

- Replace the selective-copy sentence with the exact tested sentence.
- Rename the bulk buttons.
- Add a hidden `es-copy-followup` immediately after the commit row with text `Copy complete.` and a subordinate `es-copy-view-backups` link button.

In `evesettings.js`:

```javascript
var pendingMutation = '';
var copyFollowup = false;
```

Have `mutate(method, ...)` set `pendingMutation = method`; starting `eve_settings_copy` clears `copyFollowup`. If the bridge refuses to start a worker, clear `pendingMutation` before calling `setBusy(false)`. `paintCommit()` derives singular or plural action labels from `chosenTargets()` and uses `Copy operation in progress…` only while `busy && pendingMutation === 'eve_settings_copy'`. Do not display a target-progress fraction.

In the sole `onEveSettingsDone` handler, capture the completed method, clear `pendingMutation`, and then clear busy state. Set `copyFollowup = true` and clear selection only when the completed method was a successful copy. Successful backup, restore, retention, or formation operations must not clear copy selections. Failed copies leave the follow-up false. `es-copy-view-backups` calls the same `openBackups()` function as the top tool.

Clear `copyFollowup` when root, server, profile, kind, or source changes. Do not clear it merely because the user visits Backups and returns.

- [ ] **Step 4: Add account-identification summary rendering**

Reuse `state.accounts` and `account.account_name` to calculate the named count. Render the summary and **Identify accounts…** only in Accounts mode. Source and target labels must use Python's `name`, `display_name`, and `display_meta`; do not recreate the three identity branches in JavaScript.

Offer **Identify accounts…** only when both `state.accounts.length` and `state.identity_characters.length` are nonzero, matching `eve_settings_identification_start()` preconditions. Otherwise keep the source disabled where its list is empty and render one exact primary-route message:

- No accounts: `No accounts found in this profile. Launch a character, make a small settings change, then close EVE completely.`
- No characters: `No characters found in this profile. Launch a character, make a small settings change, then close EVE completely.`

Add lexical tests for both messages and for the button-availability guard, so the page cannot route into a guaranteed backend refusal.

- [ ] **Step 5: Style feedback and verify accessibility**

Keep `es-copy-followup` quiet and non-live because the global status strip announces completion. Add an explicit hidden override. Preserve the existing EVE warning pill and one-accent-per-screen rule.

- [ ] **Step 6: Run focused tests**

Run:

```bash
uv run --no-sync python -m pytest \
  tests/test_profiles_page.py \
  tests/test_api_evesettings.py \
  tests/test_evesettings_selective.py \
  -q
```

Expected: PASS with unchanged Python copy semantics and global success text.

- [ ] **Step 7: Commit copy workflow improvements**

```bash
git add wingman/web/index.html wingman/web/evesettings.js wingman/web/style.css \
  tests/test_profiles_page.py
git commit -m "feat: focus Profiles copy workflow"
```

---

### Task 5: Move account selection into the formation editor

**Files:**
- Modify: `wingman/web/index.html:1431-1439,1542-1547`
- Modify: `wingman/web/evesettings.js:636-665,1048-1058`
- Modify: `wingman/web/formations.js:42-48,185-245,620-750`
- Modify: `wingman/web/style.css:3637-3667`
- Modify: `tests/test_page_conventions.py:2338-2460`
- Modify: `tests/test_profiles_page.py`
- Test: `tests/test_page_conventions.py`
- Test: `tests/test_profiles_page.py`

**Interfaces:**
- Consumes: account objects from `eve_settings_state`, each containing `path` and canonical `name`.
- Produces: `WM.openFormations(accounts, preferredPath)` where `accounts` is an array of `{path, name}` compatible objects and `preferredPath` is a string or empty string.
- Preserves: `WM.formationsDone(payload)` as the forwarded completion hook.

- [ ] **Step 1: Add failing formation handoff and switching tests**

Add `FORMATIONS = (WEB / "formations.js").read_text(encoding="utf-8")` beside the existing source constants. Then add lexical tests requiring the new signature and dirty guard:

```python
def test_profiles_passes_accounts_into_the_formation_editor():
    assert "WM.openFormations(state.accounts" in CODE
    assert "WM.openFormations = function (accounts, preferredPath)" in FORMATIONS


def test_formation_account_switch_guards_dirty_edits():
    assert "WM.el('fm-account').addEventListener('change'" in FORMATIONS
    switch = FORMATIONS[FORMATIONS.index("WM.el('fm-account').addEventListener('change'") :]
    assert "state.dirty" in switch
    assert "Discard changes?" in switch
    assert "WM.el('fm-account').value = state.path" in switch
```

Add assertions that initial-load failure still routes to Profiles, switch failure does not route away, and `onEveSettingsDone` ownership remains unchanged.

- [ ] **Step 2: Run the formation UI tests and verify they fail**

Run:

```bash
uv run --no-sync python -m pytest tests/test_page_conventions.py tests/test_profiles_page.py -q
```

Expected: FAIL because `WM.openFormations` accepts only a path and the rail has no account selector.

- [ ] **Step 3: Move the formation entry markup and pass canonical account choices**

In `index.html`:

- Move the existing `es-formations-open` button into the `es-profile-tools` row created in Task 2.
- Remove the old `es-formations-card` and `es-formations-account` selector completely.
- Replace `<span class="fm-account" id="fm-account"></span>` in the formation rail with `<select id="fm-account" class="field" aria-label="Account"></select>`.

In `evesettings.js`, remove `renderFormationsCard()` and its dedicated selector references. Paint the top tool's availability from `state.formations_available && state.accounts.length`. On click:

```javascript
var preferred = kind() === 'accounts' ? WM.el('es-source').value : '';
WM.openFormations(state.accounts, preferred);
```

Pass the account objects unchanged so `formations.js` uses their canonical `name` values.

- [ ] **Step 4: Render and retain account selection in `formations.js`**

Add module state for the supplied account list and last successful path. `WM.openFormations(accounts, preferredPath)` must:

1. Copy only `{path, name}` into module state.
2. Choose the last successful path if still present.
3. Otherwise choose `preferredPath` if present.
4. Otherwise choose the first account path.
5. Render the selector, route to `formations`, and perform an initial load.

Update `load()` with an explicit switch/entry mode. On initial failure, preserve the current route-back behavior. On switch failure, leave `state.formations` untouched, restore the selector to `state.path`, clear busy state, and show the error without routing away.

- [ ] **Step 5: Guard dirty account switches**

On `fm-account` change:

- Load immediately when `state.dirty` is false.
- When dirty, call the existing `WM.confirm('Discard changes?', ...)` pattern.
- On confirmation, clear dirty state and load the new account in switch mode.
- On cancellation, restore `fm-account.value = state.path` and retain all edits.
- Disable the account selector whenever `state.busy` is true.

Do not persist the selected account to settings.

- [ ] **Step 6: Run formation and API tests**

Run:

```bash
uv run --no-sync python -m pytest \
  tests/test_page_conventions.py \
  tests/test_profiles_page.py \
  tests/test_evesettings_formations.py \
  tests/test_api_evesettings.py \
  -q
```

Expected: PASS. Existing unit conversion, ID stability, mutation-lock, and async revision guards remain intact.

- [ ] **Step 7: Commit formation account switching**

```bash
git add wingman/web/index.html wingman/web/evesettings.js wingman/web/formations.js \
  wingman/web/style.css tests/test_page_conventions.py tests/test_profiles_page.py
git commit -m "feat: switch accounts inside formation editor"
```

---

### Task 6: Complete development fixtures, screenshot coverage, and smoke checks

**Files:**
- Modify: `wingman/web/dev.js:960-1415`
- Modify: `tests/test_dev_harness.py:160-330`
- Modify: `scripts/shoot_screens.py:35-75`
- Modify: `tests/test_shoot_screens.py:30-105`
- Modify: `docs/smoke-checklist.md:2529-2835`
- Test: `tests/test_dev_harness.py`
- Test: `tests/test_shoot_screens.py`

**Interfaces:**
- Produces deterministic `?dev=1` states for Backups, account identity labels, copy busy/follow-up, and formation account switching.
- Adds `Screen("profiles-backups", "Profiles - Backups", "backups", None, True)` to the real Windows screenshot inventory.

- [ ] **Step 1: Add failing development-fixture tests**

Require fixture selectors and canonical account labels:

```python
def test_profiles_fixture_covers_new_visual_states():
    for query in ("backups", "copy", "formations-account"):
        assert ".get('" + query + "')" in DEV_JS
    for state in ("empty", "unreadable", "filtered"):
        assert "'" + state + "'" in DEV_JS
    assert "Copy operation in progress" in DEV_JS
    assert "Copy complete" in DEV_JS


def test_dev_account_labels_match_the_python_identity_contract():
    assert "Account " in DEV_JS
    assert "Not identified" in DEV_JS
```

Prefer deriving expected account representations in Python tests from `identity.account_identity()` rather than hand-maintaining a second algorithm.

- [ ] **Step 2: Add the Backups screenshot and update count expectations**

Add:

```python
Screen("profiles-backups", "Profiles - Backups", "backups", None, True),
```

Do not exclude the route: its route-entry handler loads state without a setup hook. Update `test_gate_on_shoots_every_screen` from 10 to 11 and the gate-off skipped count from 6 to 7. Keep gate-off reachable screens unchanged at four.

Run:

```bash
uv run --no-sync python -m pytest tests/test_dev_harness.py tests/test_shoot_screens.py -q
```

Expected: FAIL until `dev.js` and the screenshot inventory agree with the new route and states.

- [ ] **Step 3: Implement deterministic dev states**

In `dev.js`:

- Build fixture account labels with the same two reachable states as `identity.account_identity()` and add a test that compares serialized expected values from Python.
- Support `?backups=empty`, `?backups=unreadable`, and `?backups=filtered`; route to `backups` after the first Profiles payload renders.
- Support `?copy=busy` and `?copy=success` without changing production code paths.
- Supply at least two formation accounts and support a formation-account switching scenario.
- Keep delayed mutation and delayed formation reads so the existing async windows remain visible.

- [ ] **Step 4: Update the smoke checklist to the new information architecture**

Revise `## Profiles` so it checks:

- Full-width compact profile context and top tool row
- Account identification count and the named and unidentified account-label states
- No-account and no-character guidance, with **Identify accounts…** unavailable in both states
- **Select shown**, **Clear selection**, dynamic copy labels, neutral busy wording, global completion, and local **View backups** follow-up
- Backups round-trip state preservation

Add a `### Backups` subsection checking:

- Empty, unreadable, filtered, and cleared-filter states
- One route scrollbar at 840×625 and wide widths
- Restore visibility and keyboard-accessible Delete disclosure
- Escape focus return and one-open-at-a-time behavior
- Retention confirmation and manual-backup exemption

Revise `## Probe formations` so it checks initial account choice, clean switching, dirty confirm/cancel, failed entry, failed switching, and session-only last-account behavior.

Update the Look and Feel screenshot count to `11/11`, or `4/11` with seven EVE-gated screens skipped.

- [ ] **Step 5: Run fixture, screenshot, and all focused Profiles tests**

Run:

```bash
uv run --no-sync python -m pytest \
  tests/test_dev_harness.py \
  tests/test_shoot_screens.py \
  tests/test_profiles_page.py \
  tests/test_page_conventions.py \
  tests/test_evesettings_identity.py \
  tests/test_evesettings_formations.py \
  tests/test_api_evesettings.py \
  -q
```

Expected: PASS.

- [ ] **Step 6: Commit tooling and documentation**

```bash
git add wingman/web/dev.js scripts/shoot_screens.py \
  tests/test_dev_harness.py tests/test_shoot_screens.py docs/smoke-checklist.md
git commit -m "test: cover copy-first Profiles flows"
```

---

### Task 7: Run final quality and regression gates

**Files:**
- Review only: all files changed since `68b94ba`

**Interfaces:**
- Consumes: completed Tasks 1 through 6.
- Produces: a clean, verified branch ready for manual Windows rendering and review.

- [ ] **Step 1: Inspect the complete diff against the approved spec**

Run:

```bash
git diff --check 68b94ba..HEAD
git diff --stat 68b94ba..HEAD
git diff 68b94ba..HEAD -- \
  wingman/evesettings/identity.py \
  wingman/web/index.html wingman/web/app.js wingman/web/evesettings.js \
  wingman/web/formations.js wingman/web/style.css wingman/web/dev.js \
  scripts/shoot_screens.py tests docs/smoke-checklist.md
```

Confirm there is no new bridge endpoint, no second `onEveSettingsDone` registration, no nested backup scrollbar, no inferred timestamp grouping, no per-target progress protocol, no unrelated refactor, and no debug output.

- [ ] **Step 2: Run formatting and lint gates**

Run:

```bash
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
```

Expected: both commands exit 0.

- [ ] **Step 3: Run the complete automated suite**

Run:

```bash
uv run --no-sync python -m pytest tests/
```

Expected: PASS with no failures.

- [ ] **Step 4: Exercise the browser harness**

Open `wingman/web/index.html?dev=1` and each new query-string state from Task 6. Verify the browser console has no handler-registration, missing-element, or bridge-double errors. Check the Profiles, Backups, and Formations routes at 840×625 and a wide viewport.

- [ ] **Step 5: Run the Windows smoke subset**

On Windows, execute the revised Profiles, Backups, and Probe formations sections in `docs/smoke-checklist.md`, including 100% and 200% display scaling. Run `scripts/shoot_screens.py` and verify an 11-screen manifest with a populated `profiles-backups` capture.

- [ ] **Step 6: Review and commit any verification-only corrections**

If verification required changes, rerun the affected focused tests and commit only those corrections:

```bash
git add -u
git commit -m "fix: address Profiles verification findings"
```

If no files changed, do not create an empty commit.
