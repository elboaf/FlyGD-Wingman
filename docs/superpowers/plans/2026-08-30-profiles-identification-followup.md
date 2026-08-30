# Complete Profiles Account Identification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Profiles account identification collect a unique EVE Online username, save the first confirmed character atomically, guide users through up to three confirmed characters, and support identifying several accounts in one visit.

**Architecture:** Python remains authoritative for persisted account names, unique ownership, the three-character maximum, and the exact candidate produced by the current observation. The page renders a five-step state machine and may make impossible actions unavailable, but every invariant is rechecked by synchronous request/response API methods. Existing bridge pushes remain unchanged.

**Tech Stack:** Python 3.12+, pytest, plain HTML/CSS, ES5-style JavaScript, pywebview request/response bridge, `?dev=1` browser harness.

**Spec:** `docs/profiles-identity-backups-design.md`

## Global Constraints

- Work only in the linked worktree `/mnt/c/dev/flygd-wingman-worktrees/profiles-identification-followup`.
- Preserve the focused chromeless `accountidentity` sub-route and keep account management out of the main Profiles copy card.
- The required account name is the EVE Online username supplied by the user; store it only in local `settings.json`, never send it over the network, and never include it in logs.
- Replace the unreleased `account_aliases` model with `account_names`; do not add compatibility migration code.
- Account names are trimmed, non-empty, at most 80 characters, and globally unique under `casefold()` while preserving display capitalization.
- An account may have at most three confirmed characters, and one character may belong to at most one account.
- Never infer association from availability or timestamps. Every new or moved link is user-confirmed.
- Wingman must never move or resize an EVE client window.
- Every non-method `Api` attribute remains underscore-prefixed.
- Use no new Python push handler unless implementation evidence makes one necessary. If added, update all three bridge-contract points.
- Free-text fields commit on Enter or an explicit button, never on blur and never before the first payload renders.
- Use `.check`/`.radio` wrappers, existing color tokens, existing button vocabulary, and explicit `[hidden]` CSS overrides where a selector sets `display`.
- Treat 840x625 CSS pixels as the window floor. Manually inspect that viewport and a wider viewport.
- Do not claim the optional “move an in-game window” example works without a live EVE verification.
- Preserve all backup and retention behavior merged in PR #128.

## File Structure

- Modify `wingman/settings.py`: replace the persisted alias map and normalize unique names plus bounded character rosters.
- Modify `wingman/evesettings/identity.py`: keep pure identity-label construction aligned with required account names.
- Modify `wingman/ui/api.py`: expose renamed payloads/endpoints, retain the offered candidate, serialize confirmation, and enforce all roster invariants.
- Modify `wingman/web/index.html`: provide semantic containers and controls for the name and roster steps.
- Modify `wingman/web/evesettings.js`: render and drive the five-step identification flow and manual management.
- Modify `wingman/web/style.css`: style only the new state structure using existing tokens and controls.
- Modify `wingman/web/dev.js`: support deterministic identification scenarios through `?dev=1&identity=<state>`.
- Modify `docs/smoke-checklist.md`: replace the original happy-path checks with the complete flow and Windows-only verification gap.
- Modify `tests/test_settings.py`, `tests/test_settings_evesettings.py`: pin defaults and normalization.
- Modify `tests/test_evesettings_identity.py`: pin account-label behavior after the model rename.
- Modify `tests/test_api_evesettings.py`: pin endpoint, candidate, atomicity, uniqueness, capacity, move, and payload behavior.
- Modify `tests/test_profiles_page.py`: pin markup, state flow, copy, actions, accessibility, and the renamed bridge methods.
- Modify `tests/test_dev_harness.py`: pin every required dev scenario and bridge double.
- Verify `tests/test_bridge_contract.py`: its generic send-to-callable-method scan covers the renamed and added request/response methods without a test-specific allowlist.

---

### Task 1: Persist Required Unique Account Names and Bounded Rosters

**Files:**
- Modify: `wingman/settings.py:218-226,506-547`
- Modify: `tests/test_settings.py:96-104`
- Modify: `tests/test_settings_evesettings.py:51-76`

**Interfaces:**
- Produces: `validated_eve_settings(raw) -> dict` containing `account_names: dict[str, str]` and `account_characters: dict[str, list[str]]`.
- Invariant: every retained association key also exists in `account_names`; every list contains at most three unique decimal character IDs; names are case-insensitively unique.
- Removes: `account_aliases` from defaults and normalized output.

- [ ] **Step 1: Replace default-shape expectations with `account_names`**

Update `tests/test_settings.py` and the fresh-default assertions in `tests/test_settings_evesettings.py` so the expected section contains:

```python
"eve_settings": {
    "root": None,
    "server": None,
    "profile": None,
    "auto_keep": 10,
    "account_names": {},
    "account_characters": {},
}
```

Assert that mutating one returned `account_names` or `account_characters` mapping does not affect a later default.

- [ ] **Step 2: Write failing normalization tests**

Replace the alias-era normalization test with focused tests covering:

```python
def test_account_names_are_trimmed_bounded_and_casefold_unique():
    out = settings.validated_eve_settings({
        "account_names": {
            "10": "  LoginName  ",
            "11": "loginname",
            "12": "x" * 100,
            "bad": "ignored",
        }
    })
    assert out["account_names"] == {"10": "LoginName", "12": "x" * 80}


def test_links_require_a_name_and_keep_first_three_valid_unclaimed_ids():
    out = settings.validated_eve_settings({
        "account_names": {"10": "First", "11": "Second"},
        "account_characters": {
            "10": ["20", "20", "bad", "21", "22", "23"],
            "11": ["20", "24", "25", "26"],
            "12": ["27"],
        },
    })
    assert out["account_characters"] == {
        "10": ["20", "21", "22"],
        "11": ["24", "25", "26"],
    }


def test_unreleased_alias_key_is_dropped():
    out = settings.validated_eve_settings({
        "account_aliases": {"10": "Old"},
        "account_characters": {"10": ["20"]},
    })
    assert out["account_names"] == {}
    assert out["account_characters"] == {}
```

Also assert that a valid name with no links is retained.

- [ ] **Step 3: Run the normalization tests and confirm the intended failure**

Run:

```bash
uv run --no-sync python -m pytest tests/test_settings.py tests/test_settings_evesettings.py -q
```

Expected: failures mention missing `account_names`, retained `account_aliases`, missing name uniqueness, and rosters longer than three.

- [ ] **Step 4: Implement normalization in dependency order**

Change `_eve_settings_defaults()` to return `account_names`. In `validated_eve_settings()`:

```python
names = raw.get("account_names")
claimed_names: set[str] = set()
if isinstance(names, dict):
    for account_id, name in names.items():
        if not _decimal_id(account_id) or not isinstance(name, str):
            continue
        cleaned = name.strip()[:80]
        folded = cleaned.casefold()
        if not cleaned or folded in claimed_names:
            continue
        claimed_names.add(folded)
        section["account_names"][account_id] = cleaned

associations = raw.get("account_characters")
claimed_characters: set[str] = set()
if isinstance(associations, dict):
    for account_id, character_ids in associations.items():
        if account_id not in section["account_names"] or not isinstance(character_ids, list):
            continue
        valid: list[str] = []
        for character_id in character_ids:
            if (
                not _decimal_id(character_id)
                or character_id in claimed_characters
                or character_id in valid
            ):
                continue
            valid.append(character_id)
            claimed_characters.add(character_id)
            if len(valid) == 3:
                break
        if valid:
            section["account_characters"][account_id] = valid
```

Do not read `account_aliases`. Preserve the existing per-entry defensive posture for all unrelated settings.

- [ ] **Step 5: Run focused settings tests**

Run:

```bash
uv run --no-sync python -m pytest tests/test_settings.py tests/test_settings_evesettings.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit the schema change**

```bash
git add wingman/settings.py tests/test_settings.py tests/test_settings_evesettings.py
git commit -m "feat: require unique names for identified accounts"
```

---

### Task 2: Rename Account Identity Payloads and Harden Manual Management

**Files:**
- Modify: `wingman/evesettings/identity.py`
- Modify: `wingman/ui/api.py:3735-3811,4129-4193`
- Modify: `tests/test_evesettings_identity.py`
- Modify: `tests/test_api_evesettings.py:948-1035`

**Interfaces:**
- Consumes: normalized `account_names` and `account_characters` from Task 1.
- Produces: account payload field `account_name: str`; `eve_settings_set_account_name(account_id: str, name: str) -> dict`; hardened `eve_settings_set_account_characters(account_id: str, character_ids: list) -> dict`.
- Removes: payload field `alias` and method `eve_settings_set_account_alias`.

- [ ] **Step 1: Write failing pure-label and API payload tests**

Rename alias-oriented tests and fixtures to `account_names`. Assert:

```python
account = api.eve_settings_state()["accounts"][0]
assert account["account_name"] == "LoginName"
assert "alias" not in account
assert account["display_name"] == "LoginName"
assert account["display_meta"] == "Aiga Otsolen + 1 · 10"
```

Keep raw numeric fallback assertions for unidentified accounts and backup labels.

- [ ] **Step 2: Write failing account-name endpoint tests**

Cover these exact outcomes:

```python
assert api.eve_settings_set_account_name("10", " LoginName ")["applied"] is True
assert api._eve_section()["account_names"] == {"10": "LoginName"}

result = api.eve_settings_set_account_name("11", "loginname")
assert result == {
    "applied": False,
    "persisted": False,
    "error": "That EVE Online username is already assigned to another account.",
}

assert api.eve_settings_set_account_name("10", "")["applied"] is False
assert api.eve_settings_set_account_name("10", "x" * 81)["applied"] is False
```

Assert renaming account `10` to `LOGINNAME` is allowed because uniqueness excludes itself, and a renamed account retains its character links.

- [ ] **Step 3: Write failing roster-invariant tests**

Add tests proving:

- an unnamed destination refuses character links;
- three unique IDs apply;
- a fourth unique ID is refused without mutating either account;
- duplicate IDs do not consume slots;
- an unknown character is refused;
- moving a character to a destination with room removes it from the old account;
- moving to a full destination leaves the old owner unchanged;
- removing every character retains `account_names[account_id]`.

Use exact expected error copy:

```python
"Name this account before adding characters."
"An EVE account can have up to three characters."
```

- [ ] **Step 4: Run focused tests and verify failure**

Run:

```bash
uv run --no-sync python -m pytest \
  tests/test_evesettings_identity.py \
  tests/test_api_evesettings.py \
  -k 'account or identity_editor or associating' -q
```

Expected: FAIL on alias-era fields/methods and missing uniqueness/capacity checks.

- [ ] **Step 5: Rename the identity producer and payload**

Update `account_identity()` parameter names and callers from aliases to names without changing its single-producer role. In `Api.eve_settings_state()`, emit:

```python
item["account_name"] = (section.get("account_names") or {}).get(
    record.file_id, ""
)
item["character_ids"] = list(
    (section.get("account_characters") or {}).get(record.file_id, [])
)
```

Update backup and formation label callers to consume the same producer.

- [ ] **Step 6: Implement the account-name endpoint**

Replace `eve_settings_set_account_alias` with `eve_settings_set_account_name`. Validate account presence, non-empty trimmed value, 80-character maximum, and case-insensitive uniqueness excluding `account_id` before calling:

```python
settings_mod.update_section(
    self._state.settings,
    "eve_settings",
    {"account_names": names},
)
```

Never interpolate the account name into logs. On `OSError`, keep the existing generic user-facing save failure.

- [ ] **Step 7: Validate the entire destination roster before moving ownership**

In `eve_settings_set_account_characters`, build and validate `wanted` first. Reject an unnamed account or `len(wanted) > 3` before removing IDs from any other account. Only after every validation passes should the method construct the final associations and persist them once.

- [ ] **Step 8: Run focused tests**

Run:

```bash
uv run --no-sync python -m pytest \
  tests/test_evesettings_identity.py \
  tests/test_api_evesettings.py \
  -k 'account or identity_editor or associating' -q
```

Expected: PASS.

- [ ] **Step 9: Commit the identity API change**

```bash
git add wingman/evesettings/identity.py wingman/ui/api.py \
  tests/test_evesettings_identity.py tests/test_api_evesettings.py
git commit -m "feat: enforce account identity invariants"
```

---

### Task 3: Make Identification Confirmation Python-Owned and Atomic

**Files:**
- Modify: `wingman/ui/api.py:370-380,4030-4115,4195-4268`
- Verify: `tests/test_api.py`
- Modify: `tests/test_api_evesettings.py:1037-1090`

**Interfaces:**
- Produces: private `_eve_identification_candidate: tuple[str, tuple[str, ...]] | None`.
- Produces: `eve_settings_identification_confirm(account_id: str, character_id: str, account_name: str) -> dict` using the standard `{applied, persisted, error}` result.
- Preserves: existing start/check/cancel method names and no new push handler.

- [ ] **Step 1: Pin the private candidate attribute**

Rely on the existing generic public-attribute test in `tests/test_api.py`, and add API tests asserting a new `Api` starts with both identification fields empty:

```python
assert api._eve_identification is None
assert api._eve_identification_candidate is None
```

No non-method public attribute may be introduced.

- [ ] **Step 2: Write failing candidate lifecycle tests**

Cover:

- `identification_start` clears an old candidate;
- a candidate result stores `(account_id, offered_character_ids)`;
- no-change, ambiguity, invalidation, cancel, root change, server/profile change, and route-equivalent cancellation clear the candidate where they clear the snapshot;
- EVE-still-running leaves the snapshot but clears any obsolete candidate;
- the no-change error is exactly:

```text
No account and character changes were found. Make a small settings change in the client, then close it completely and check again.
```

- [ ] **Step 3: Write failing atomic confirmation tests**

Use a real temporary settings document and monkeypatch `settings_mod.update_section` where necessary. Assert:

- no pending candidate is refused;
- an account or character not in the latest candidate is refused;
- blank, overlong, and duplicate names write neither map;
- successful confirmation writes `account_names` and `account_characters` in one `update_section` call;
- an `OSError` writes neither map, returns a retryable error, and retains the candidate;
- success clears snapshot and candidate;
- an existing name can be passed unchanged and does not conflict with itself;
- a character already on the candidate account is a successful no-op;
- a candidate account with three different links is refused;
- a character owned by another account moves only when destination capacity permits.

- [ ] **Step 4: Write the concurrency regression test**

Arrange two calls against one pending candidate and an injected blocking `update_section`. Assert that only one call can consume and persist the candidate; the other is refused as busy or stale. The test must exercise the existing `_eve_mutation` lock rather than a test-only lock.

- [ ] **Step 5: Run identification API tests and verify failure**

Run:

```bash
uv run --no-sync python -m pytest \
  tests/test_api.py \
  tests/test_api_evesettings.py \
  -k 'public_attributes or identification' -q
```

Expected: FAIL because candidate storage and `eve_settings_identification_confirm` do not exist.

- [ ] **Step 6: Add candidate storage and centralized clearing**

Initialize:

```python
self._eve_identification = None
self._eve_identification_candidate = None
```

Add a private helper used by start, cancel, root selection, and profile selection:

```python
def _eve_clear_identification(self) -> None:
    self._eve_identification = None
    self._eve_identification_candidate = None
```

Replace direct snapshot clearing at relevant call sites with this helper. Do not change unrelated mutation behavior.

- [ ] **Step 7: Store only candidates produced by the latest check**

Serialize `eve_settings_identification_check` with `_eve_mutation` using the same non-blocking posture as `_eve_hold`, but return semantic identification errors rather than opening a second alert. Clear an obsolete candidate before each comparison. On a valid result set:

```python
self._eve_identification_candidate = (
    account_id,
    tuple(changed.characters),
)
```

Return the same candidate payload already used by the page.

- [ ] **Step 8: Implement atomic confirmation under the mutation lock**

`eve_settings_identification_confirm` must:

1. acquire `_eve_mutation` non-blocking;
2. compare the submitted account and character with `_eve_identification_candidate`;
3. validate the current name map, uniqueness excluding the account itself, current ownership, and destination capacity;
4. build final `account_names` and `account_characters` without mutating the live section first;
5. call one `settings_mod.update_section()` with both maps;
6. clear snapshot and candidate only after success;
7. release the lock in `finally`.

Return field-shaped errors so the name step can render inline. Keep the supplied username out of logger messages.

- [ ] **Step 9: Run focused API tests**

Run:

```bash
uv run --no-sync python -m pytest \
  tests/test_api.py \
  tests/test_api_evesettings.py \
  -k 'public_attributes or identification' -q
```

Expected: PASS.

- [ ] **Step 10: Commit atomic confirmation**

```bash
git add wingman/ui/api.py tests/test_api_evesettings.py
git commit -m "feat: confirm identified accounts atomically"
```

---

### Task 4: Build the Five-Step Identification Interface

**Files:**
- Modify: `wingman/web/index.html:1443-1496`
- Modify: `wingman/web/evesettings.js:20-340,650-860`
- Modify: `wingman/web/style.css:2872-2914`
- Modify: `tests/test_profiles_page.py:680-780`
- Verify: `tests/test_bridge_contract.py`

**Interfaces:**
- Consumes: account payloads with `account_name`, `character_ids`, and existing display labels.
- Consumes: `eve_settings_identification_confirm`, `eve_settings_set_account_name`, and `eve_settings_set_account_characters`.
- Produces: page states `idle`, `watching`, `candidate`, `name`, and `roster`; failure responses render as waiting variants.

- [ ] **Step 1: Write failing lexical tests for markup and copy**

Update `tests/test_profiles_page.py` to require semantic containers and controls for:

```text
ai-intro
es-identify-candidate
ai-name-step
es-account-name
es-account-name-save
ai-roster-step
ai-roster-heading
ai-roster-count
ai-roster-characters
ai-roster-add-row
ai-roster-character
ai-roster-add
ai-roster-empty
ai-roster-done
ai-identify-another
```

Require the exact generic instruction and recovery copy from the spec. Assert that no optional account-name placeholder or `account alias` user-facing text remains.

- [ ] **Step 2: Write failing lexical tests for bridge calls and state behavior**

Replace old completion assertions with checks that:

- `eve_settings_identification_confirm` and `eve_settings_set_account_name` are literal `WM.send` targets;
- `eve_settings_set_account_alias` is absent;
- Enter on `es-account-name` activates the same save path as the button;
- existing-name candidates call atomic confirmation without entering the name step;
- `Done` routes to Profiles;
- `Identify another account` returns to idle without leaving the sub-route;
- the roster count derives from `state.accounts` and `account_name`;
- add controls are hidden at three or when no remaining characters exist;
- move confirmation still uses `WM.confirm` and names both accounts.

- [ ] **Step 3: Write failing accessibility and hierarchy tests**

Assert:

- step headings are programmatically focusable with `tabindex="-1"`;
- step transitions call `.focus()` on the newly visible heading;
- `ai-roster-count` has `role="status"`;
- `es-account-name` uses `aria-describedby` pointing to its hint and error/status elements;
- waiting makes **Check changes** accent;
- candidate makes **Link character** accent;
- name makes **Save and continue** accent;
- roster makes **Add character** accent only while addition is available, otherwise **Done** is accent;
- no state has two `.btn.acc` controls.

- [ ] **Step 4: Run page and bridge tests and verify failure**

Run:

```bash
uv run --no-sync python -m pytest \
  tests/test_profiles_page.py \
  tests/test_bridge_contract.py -q
```

Expected: FAIL on old completion markup, alias bridge name, missing name/roster controls, and absent accessibility behavior.

- [ ] **Step 5: Replace the old completion block with name and roster markup**

Keep the route and top `‹ Profiles` control. Add separate hidden sections for the name and roster steps. Use labels associated with controls, `role="status"` for changing status/count text, and existing `.row`, `.lab`, `.field`, `.btn`, and `.linkbtn` vocabulary. Include explicit `[hidden]` CSS overrides for every new selector that declares `display`.

- [ ] **Step 6: Refactor rendering around one explicit step variable**

Replace `identityComplete` with page-owned state such as:

```javascript
var identityStep = 'idle';
var identifyCandidate = null;
var pendingCharacterId = '';
var rosterAccountId = '';
```

Create one `paintIdentification(step, message)` that hides every inactive step, assigns exactly one accent action, preserves the top route exit, and moves focus only when the step actually changes. Failure statuses from check remain in `watching` with actionable status copy.

- [ ] **Step 7: Implement candidate-to-name and existing-name branches**

On **Link character**:

- ensure the selected character is one offered by `identifyCandidate`;
- use the existing move-confirm helper when another account owns it;
- if the account has `account_name`, call `eve_settings_identification_confirm` immediately with that name and show the roster after refresh;
- otherwise store `pendingCharacterId`, show the required name step, and persist nothing.

On **Save and continue** or Enter, call `eve_settings_identification_confirm`. Keep the typed value and name step on refusal. On success, refresh state and open the roster for the confirmed account.

- [ ] **Step 8: Render and operate the bounded roster**

Render confirmed names and `N of 3 characters linked`. Build the remaining dropdown from `state.identity_characters`, excluding only characters already linked to the destination. If the destination has three links or no remaining discovered character, hide the add row and show the corresponding message. Otherwise, use the existing complete-roster endpoint to add one selected character after any required move confirmation.

**Done** calls the existing route-return path. **Identify another account** clears page-owned pending state, calls identification cancel defensively, and returns to idle on the same route. Derive `<named> of <discovered>` from `state.accounts.filter(account_name)` and `state.accounts.length`.

- [ ] **Step 9: Update manual management**

Rename fields and methods from alias to account name, remove optional copy, submit name changes on Enter or **Apply**, and preserve entered text on refusal. Hide manual add controls at three links and rely on Python for final enforcement. Keep removing a link separate from deleting or clearing the retained name.

- [ ] **Step 10: Style the new steps at the established measure**

Use the existing 620px shell, spacing tokens, borders, and typography. Do not add cards, gradients, colors, layout-property animation, or a new modal. Ensure the roster and actions fit 840x625 without horizontal scrolling and the route remains the only scroll owner.

- [ ] **Step 11: Run page and bridge tests**

Run:

```bash
uv run --no-sync python -m pytest \
  tests/test_profiles_page.py \
  tests/test_bridge_contract.py -q
```

Expected: PASS.

- [ ] **Step 12: Check JavaScript syntax**

Run:

```bash
node --check wingman/web/evesettings.js
```

Expected: exit 0.

- [ ] **Step 13: Commit the guided interface**

```bash
git add wingman/web/index.html wingman/web/evesettings.js \
  wingman/web/style.css tests/test_profiles_page.py tests/test_bridge_contract.py
git commit -m "feat: guide complete account identification"
```

---

### Task 5: Make Every Identification State Visually Reproducible

**Files:**
- Modify: `wingman/web/dev.js:999-1195`
- Modify: `tests/test_dev_harness.py`

**Interfaces:**
- Consumes: `?dev=1&identity=<state>`.
- Produces deterministic scenarios: `idle`, `waiting`, `none`, `ambiguous`, `candidate-multiple`, `pending-name`, `existing-name`, `roster-one`, `roster-two`, `roster-three`, `roster-empty`, `move`, and `full`.
- Doubles: `eve_settings_identification_confirm`, `eve_settings_set_account_name`, and the hardened complete-roster method.

- [ ] **Step 1: Write failing fixture-contract tests**

In `tests/test_dev_harness.py`, assert that each required state token appears exactly once in a state table, that the query uses `URLSearchParams`, and that the generic bridge-double scan sees the new confirm/name endpoints and no alias endpoint.

Assert fixture rosters obey the production invariants: every linked account has a unique non-empty `account_name`, no account has more than three characters, and a character is not linked twice.

- [ ] **Step 2: Run harness tests and verify failure**

Run:

```bash
uv run --no-sync python -m pytest tests/test_dev_harness.py -q
```

Expected: FAIL because the state selector and new endpoint doubles do not exist.

- [ ] **Step 3: Add an explicit scenario table**

Parse:

```javascript
var identityScenario = new URLSearchParams(window.location.search)
  .get('identity') || 'idle';
```

Use one object/table to define each check result and seeded account roster. Do not spread scenario conditionals through unrelated Profiles fixtures. Keep the ordinary `?dev=1` default equivalent to `idle`.

- [ ] **Step 4: Double the renamed and atomic endpoints faithfully**

The confirm double must reject a pair outside the latest fake candidate, enforce case-insensitive unique names and three slots, update both maps together, and return `{applied, persisted, error}`. The manual name and roster doubles enforce the same visible outcomes as Python so browser review cannot approve an impossible state.

- [ ] **Step 5: Run harness and syntax tests**

Run:

```bash
uv run --no-sync python -m pytest tests/test_dev_harness.py -q
node --check wingman/web/dev.js
```

Expected: PASS and exit 0.

- [ ] **Step 6: Inspect all states in a browser**

Serve `wingman/web/`, then open each `identity` state at:

- 840x625 CSS pixels;
- 1280x800 CSS pixels.

For each state verify: one clear primary action, no horizontal scrolling, route-level scrolling only, visible Done escape where applicable, correct focus destination, no clipped username/character selector, and no add affordance at three. Record any live-EVE-only gaps rather than guessing.

- [ ] **Step 7: Commit deterministic visual fixtures**

```bash
git add wingman/web/dev.js tests/test_dev_harness.py
git commit -m "test: expose account identification browser states"
```

---

### Task 6: Update Operational Verification and Run Final Gates

**Files:**
- Modify: `docs/smoke-checklist.md:2590-2660`
- Verify: all changed files

**Interfaces:**
- Consumes: completed behavior from Tasks 1-5.
- Produces: a reviewer-usable Windows smoke procedure and final verification evidence.

- [ ] **Step 1: Update the Profiles smoke checklist**

Replace the original single-link completion language with checks for:

- the required in-client settings change;
- no-change recovery copy;
- pending match discarded before account-name save;
- atomic unique username plus first link;
- case-insensitive duplicate refusal;
- one-, two-, and three-character roster completion;
- no remaining discovered characters;
- confirmed moves and refused moves to full accounts;
- re-identifying an already named account;
- Identify another account and current-profile progress;
- retained names after removing every character;
- explicit `?dev=1&identity=<state>` viewport checks;
- the remaining requirement for a real Windows/live-EVE smoke pass.

Do not claim the “move an in-game window” example is valid unless this implementation session actually verifies both files are dirtied.

- [ ] **Step 2: Run focused behavior tests**

Run:

```bash
uv run --no-sync python -m pytest \
  tests/test_settings.py \
  tests/test_settings_evesettings.py \
  tests/test_evesettings_identity.py \
  tests/test_api.py \
  tests/test_api_evesettings.py \
  tests/test_profiles_page.py \
  tests/test_dev_harness.py \
  tests/test_bridge_contract.py -q
```

Expected: PASS.

- [ ] **Step 3: Run JavaScript syntax checks**

Run:

```bash
node --check wingman/web/evesettings.js
node --check wingman/web/dev.js
```

Expected: both exit 0.

- [ ] **Step 4: Commit smoke documentation**

```bash
git add docs/smoke-checklist.md
git commit -m "docs: expand account identification smoke coverage"
```

- [ ] **Step 5: Run `polish-core --fix` and inspect its edits**

Run the repository-required changed-code polish against `13290ae`. Accept only high-confidence fixes within this feature's scope. Inspect `git diff` after the pass and rerun any focused test affected by its edits.

- [ ] **Step 6: Run full verification from a clean command line**

Run:

```bash
uv run --no-sync python -m pytest tests/
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
node --check wingman/web/evesettings.js
node --check wingman/web/dev.js
git diff --check 13290ae..HEAD
git status --short
```

Expected: pytest passes with only documented skips; Ruff lint and format pass; both JavaScript files parse; diff check reports nothing; status contains no uncommitted files.

- [ ] **Step 7: Perform or explicitly defer the Windows/live-EVE smoke pass**

If a Windows EVE installation is available, execute the updated Profiles checklist. Otherwise record explicitly that automated tests and `?dev=1` inspection passed but the real file-dirtying identification path still requires Windows/live-EVE verification.

- [ ] **Step 8: Run `change-explainer` for the completion report**

Review the final diff against `docs/profiles-identity-backups-design.md`, report exact verification performed, identify any deferred live-EVE check, and call out the account-name privacy model, atomic confirmation boundary, and maximum-three normalization for reviewers.
