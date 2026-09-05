# Central Character Authorization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Centralize full Skills-and-Fittings EVE authorization in Settings › Characters, remove misleading per-feature authorization controls, and repair the Fittings workspace spacing.

**Architecture:** `eveauth.AuthorityController` remains the only credential owner and gains an explicit full-authorization state machine plus named, fail-closed Skills/Fittings cleanup slots. A dedicated `characters.js` Settings module consumes a display-safe shared bridge payload and one semantic authority event; Skills and Fittings retain only task-specific state and link to Settings. Skills and Fittings share one parent workspace geometry class.

**Tech Stack:** Python 3.11+, pytest, plain ES5 JavaScript, HTML/CSS, pywebview 6.2.1, Windows DPAPI, EVE SSO PKCE, Ruff.

**Spec:** `docs/superpowers/specs/2026-09-04-central-character-authorization-design.md`

## Global Constraints

- Work in `/mnt/c/dev/flygd-wingman/.worktrees/central-character-auth` on `fix/central-character-auth`.
- Use test-first red-green-refactor for every behavior change.
- Request exactly Skills and Fittings scopes; a future capability must not silently widen consent.
- Never send tokens, owner hashes, raw scopes, claims, or lifecycle generations across the bridge.
- Never persist authority state in `settings.json`.
- Preserve DPAPI protection, lifecycle-gate ordering, atomic writes, and fitting unknown-intent safety.
- A known owner mismatch is two present, unequal owner hashes; missing hashes retain character-ID compatibility.
- Unknown-character authorization fails closed unless both required feature slots verify cleanup.
- No native `window.alert`, `window.confirm`, or `window.prompt`.
- Settings mutations distinguish refusal, partial persistence, and success.
- The page is not executed by pytest; update dev fixtures, screenshots, and the Windows smoke checklist.
- Do not edit completed records under `docs/history/`.
- Do not add dependencies or upgrade pywebview.

## File and Interface Map

- `wingman/eveauth/application.py`: explicit full-auth capability/scope declarations.
- `wingman/eveauth/cleanup.py`: shared load-health and cleanup-verification value types.
- `wingman/eveauth/controller.py`: authorization attempts, cancellation linearization, owner checks, required slots, forget aggregation, safe management state.
- `wingman/eveskills/state.py`, `wingman/evefittings/store.py`: structured cleanup-verifiability from durable loads.
- `wingman/eveskills/controller.py`, `wingman/evefittings/controller.py`: result-bearing cleanup and reconciliation.
- `wingman/__main__.py`: named Skills/Fittings slot registration; absent controllers remain unverified.
- `wingman/ui/api.py`: safe shared bridge methods and semantic event.
- `wingman/web/characters.js`: Settings section state, rendering, filtering, authorization controls, menu, and forget flow.
- `wingman/web/app.js`: handler allowlist/event fan-out, Settings-section navigation helper, EVE gating.
- `wingman/web/index.html`, `wingman/web/style.css`: Characters markup/styles, old controls removal, shared workspace geometry.
- `wingman/web/skills.js`, `wingman/web/fittings.js`: task-focused handoff to Settings.
- `wingman/web/dev.js`, `scripts/shoot_screens.py`: deterministic visual states.

---

### Task 1: Pin the Full Authorization Scope Contract

**Files:**
- Modify: `wingman/eveauth/application.py`
- Modify: `wingman/eveauth/__init__.py`
- Modify: `tests/test_eveauth_application.py`

**Interfaces:**
- Produces: `FULL_AUTH_CAPABILITIES: tuple[str, ...]`
- Produces: `FULL_AUTH_SCOPES: frozenset[str]`
- Preserves: `CAPABILITY_SCOPES`, `SKILLS_SCOPES`, `FITTINGS_SCOPES`

- [ ] **Step 1: Write failing scope-contract tests**

Add tests that pin the product decision and prove an unrelated registry entry cannot widen consent:

```python
def test_full_authorization_names_exactly_the_current_product_capabilities():
    assert application.FULL_AUTH_CAPABILITIES == (
        application.SKILLS,
        application.FITTINGS,
    )


def test_full_authorization_scopes_are_derived_from_the_explicit_capabilities():
    expected = application.SKILLS_SCOPES | application.FITTINGS_SCOPES
    assert application.FULL_AUTH_SCOPES == expected
    assert application.FULL_AUTH_SCOPES == frozenset(
        {
            "esi-skills.read_skills.v1",
            "esi-skills.read_skillqueue.v1",
            "esi-fittings.read_fittings.v1",
            "esi-fittings.write_fittings.v1",
        }
    )


def test_a_future_capability_does_not_widen_full_authorization(monkeypatch):
    monkeypatch.setitem(application.CAPABILITY_SCOPES, "future", frozenset({"future.scope"}))
    assert "future.scope" not in application.FULL_AUTH_SCOPES
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
uv run --no-sync python -m pytest tests/test_eveauth_application.py -v
```

Expected: the new tests fail because `FULL_AUTH_CAPABILITIES` and `FULL_AUTH_SCOPES` do not exist.

- [ ] **Step 3: Implement the explicit declaration**

Replace the module commentary that forbids any combined request and add:

```python
FULL_AUTH_CAPABILITIES = (SKILLS, FITTINGS)
FULL_AUTH_SCOPES = frozenset().union(
    *(CAPABILITY_SCOPES[name] for name in FULL_AUTH_CAPABILITIES)
)
```

Export both names from `wingman/eveauth/__init__.py`. Keep individual capability scope sets for authorization checks.

- [ ] **Step 4: Run focused tests and verify GREEN**

```bash
uv run --no-sync python -m pytest tests/test_eveauth_application.py tests/test_eveauth_client_id_consistency.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add wingman/eveauth/application.py wingman/eveauth/__init__.py tests/test_eveauth_application.py
git commit -m "Define full EVE authorization scopes"
```

---

### Task 2: Make Feature Cleanup Verifiable

**Files:**
- Create: `wingman/eveauth/cleanup.py`
- Modify: `wingman/eveauth/__init__.py`
- Modify: `wingman/eveskills/state.py`
- Modify: `wingman/evefittings/store.py`
- Modify: `tests/test_eveskills_state.py`
- Modify: `tests/test_evefittings_store.py`

**Interfaces:**
- Produces: `LoadHealth(cleanup_verifiable: bool, rewrite_required: bool = False)`
- Produces: `CleanupVerification(verified: bool, blocked_character_ids: frozenset[int], error: str = "")`
- Produces: `eveskills.state.load_with_health(path) -> tuple[SkillsState, list[str], LoadHealth]`
- Produces: `evefittings.store.load_fittings_with_health(path) -> tuple[FittingsState, tuple[str, ...], LoadHealth]`
- Preserves: existing two-value `load()` and `load_fittings()` APIs as wrappers

- [ ] **Step 1: Write failing load-health tests**

Cover four durable-state outcomes in both state test files:

```python
def test_missing_primary_and_backup_is_verified_first_launch(tmp_path):
    state, warnings, health = state_mod.load_with_health(tmp_path / "missing.json")
    assert state.characters == []
    assert warnings == []
    assert health.cleanup_verifiable is True


def test_unreadable_primary_and_backup_is_not_cleanup_verifiable(tmp_path, monkeypatch):
    # Arrange the existing bounded read seam to raise OSError for both copies.
    loaded, warnings, health = state_mod.load_with_health(tmp_path / "eve_skills.json")
    assert loaded.characters == []
    assert warnings
    assert health.cleanup_verifiable is False
```

Also assert that a valid primary and successfully recovered backup are verifiable, while tolerated row loss or recovery that cannot be rewritten sets `rewrite_required=True` and remains unverified until a normalized save succeeds.

- [ ] **Step 2: Run loader tests and verify RED**

```bash
uv run --no-sync python -m pytest tests/test_eveskills_state.py tests/test_evefittings_store.py -v
```

Expected: fail because the health types and loader variants are absent.

- [ ] **Step 3: Add shared cleanup value types**

Create `wingman/eveauth/cleanup.py`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class LoadHealth:
    cleanup_verifiable: bool
    rewrite_required: bool = False


@dataclass(frozen=True)
class CleanupVerification:
    verified: bool
    blocked_character_ids: frozenset[int] = frozenset()
    error: str = ""
```

Export these from `wingman/eveauth/__init__.py`.

- [ ] **Step 4: Implement structured loader variants**

Refactor each loader through one internal implementation that returns state, warnings, and `LoadHealth`; retain compatibility wrappers:

```python
def load(path: Path) -> tuple[SkillsState, list[str]]:
    state, warnings, _health = load_with_health(path)
    return state, warnings
```

Use facts from the read/recovery branch, never warning-string parsing. Classify absent primary plus absent backup as a verified first launch. Classify inaccessible/unrecoverable state and unsaved tolerant recovery as unverified.

- [ ] **Step 5: Run loader tests and verify GREEN**

```bash
uv run --no-sync python -m pytest tests/test_eveskills_state.py tests/test_evefittings_store.py -v
```

Expected: PASS with existing loader callers unchanged.

- [ ] **Step 6: Commit**

```bash
git add wingman/eveauth/cleanup.py wingman/eveauth/__init__.py \
  wingman/eveskills/state.py wingman/evefittings/store.py \
  tests/test_eveskills_state.py tests/test_evefittings_store.py
git commit -m "Report EVE feature cleanup health"
```

---

### Task 3: Return Exact Cleanup Results from Skills and Fittings

**Files:**
- Modify: `wingman/eveskills/controller.py`
- Modify: `wingman/evefittings/controller.py`
- Modify: `tests/test_eveskills_controller.py`
- Modify: `tests/test_evefittings_lifecycle.py`

**Interfaces:**
- Consumes: `LoadHealth`, `CleanupVerification`, `MutationResult`
- Changes: `authority_removed(character_id: int) -> MutationResult`
- Changes: `reconcile_characters(characters: tuple[AuthorityCharacter, ...]) -> CleanupVerification`
- Preserves: `prepare_forget(character_id) -> MutationResult`, `grant_invalidated(character_id) -> None`

- [ ] **Step 1: Write failing Skills cleanup tests**

Add tests proving cleanup is candidate-first and retryable:

```python
def test_failed_authority_removal_save_reports_the_exact_blocked_character(tmp_path, monkeypatch):
    character = state_mod.Character(character_id=42)
    controller, _pushed, _alerts = build(tmp_path, characters=(character,))
    monkeypatch.setattr(state_mod, "save", lambda *_args: (_ for _ in ()).throw(OSError("disk")))

    result = controller.authority_removed(42)

    assert result == MutationResult(True, False, "Could not save Skills cleanup.")
    verification = controller.reconcile_characters(tuple())
    assert verification.verified is True
    assert verification.blocked_character_ids == frozenset({42})


def test_successful_retry_clears_the_skills_cleanup_block(tmp_path, monkeypatch):
    character = state_mod.Character(character_id=42)
    controller, _pushed, _alerts = build(tmp_path, characters=(character,))
    original_save = state_mod.save
    calls = 0

    def fail_once(state, path):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("disk")
        original_save(state, path)

    monkeypatch.setattr(state_mod, "save", fail_once)
    assert controller.authority_removed(42).persisted is False
    assert controller.reconcile_characters(tuple()).blocked_character_ids == frozenset()
```

Assert live state is published only after a successful save so a failed write cannot erase the evidence needed for retry.

- [ ] **Step 2: Write failing Fittings cleanup tests**

Build fixtures where character 42 appears separately in presence, snapshot, and intent data. Assert each source contributes to `blocked_character_ids`, unresolved intents still refuse `prepare_forget`, successful cleanup retains library entries/collections, and failed save is retryable.

- [ ] **Step 3: Run controller tests and verify RED**

```bash
uv run --no-sync python -m pytest tests/test_eveskills_controller.py tests/test_evefittings_lifecycle.py -v
```

Expected: fail because cleanup methods return `None` and load verifiability is not retained.

- [ ] **Step 4: Implement result-bearing cleanup**

Store each controller's load health and pending blocked IDs. Build pruned candidates without mutating live state, save, then publish. Return:

```python
CleanupVerification(
    verified=self._cleanup_verifiable,
    blocked_character_ids=frozenset(self._cleanup_blocked_ids),
    error=self._cleanup_error,
)
```

For Fittings, derive orphan IDs from presences, snapshots, and intents only. Never treat library entries or collections as cleanup evidence.

- [ ] **Step 5: Run controller and domain regression tests**

```bash
uv run --no-sync python -m pytest \
  tests/test_eveskills_controller.py \
  tests/test_evefittings_lifecycle.py \
  tests/test_evefittings_copy.py \
  tests/test_evefittings_store.py -v
```

Expected: PASS; fitting entries survive character removal and unresolved intents retain their existing refusal behavior.

- [ ] **Step 6: Commit**

```bash
git add wingman/eveskills/controller.py wingman/evefittings/controller.py \
  tests/test_eveskills_controller.py tests/test_evefittings_lifecycle.py
git commit -m "Make EVE character cleanup verifiable"
```

---

### Task 4: Add Required Cleanup Slots and Truthful Forget Results

**Files:**
- Modify: `wingman/eveauth/controller.py`
- Modify: `wingman/__main__.py`
- Modify: `tests/test_eveauth_lifecycle.py`
- Modify: `tests/test_eveskills_controller.py`
- Modify: `tests/test_skills_wiring.py`
- Modify: `tests/test_fittings_wiring.py`

**Interfaces:**
- Consumes: result-bearing participant methods from Task 3
- Changes: `register_participant(capability: str, participant: CharacterParticipant) -> CleanupVerification`
- Produces internally: exact blocked-ID state and required-slot verification
- Preserves: `forget(character_id: int) -> MutationResult`

- [ ] **Step 1: Write failing required-slot tests**

Add authority lifecycle cases for:

```python
def test_unknown_id_is_blocked_while_a_required_slot_is_unverified(tmp_path):
    authority, _alerts, _launched, _listener = build(tmp_path)
    clean_skills = Participant(
        verification=CleanupVerification(True, frozenset())
    )
    authority.register_participant(application.SKILLS, clean_skills)

    assert authority._verify_unknown_character(77).applied is False


def test_an_exact_cleanup_block_does_not_block_an_unrelated_id(tmp_path):
    authority, _alerts, _launched, _listener = build(tmp_path)
    authority.register_participant(
        application.SKILLS,
        Participant(verification=CleanupVerification(True, frozenset({42}))),
    )
    authority.register_participant(
        application.FITTINGS,
        Participant(verification=CleanupVerification(True, frozenset())),
    )

    assert authority._verify_unknown_character(42).applied is False
    assert authority._verify_unknown_character(77).applied is True
```

Extend the existing lifecycle-test `Participant` fake with a `verification` constructor argument and return it from `reconcile_characters`; this keeps the test seam explicit rather than introducing magic helper functions.

Also test duplicate/unknown slot registration refusal, controller exceptions becoming unverified fixed messages, and successful verification only after both named slots report clean.

- [ ] **Step 2: Write failing forget-aggregation tests**

Assert the exact result matrix:

```python
assert refused == MutationResult(False, False, "Reconcile first.")
assert complete == MutationResult(True, True, "")
assert partial.applied is True
assert partial.persisted is False
assert "cleanup" in partial.error.lower()
```

Cover authority save failure invoking no cleanup, already-absent authority retrying cleanup, restart reconstruction from durable orphan rows, and a participant construction/load failure blocking unknown IDs.

- [ ] **Step 3: Run lifecycle/wiring tests and verify RED**

```bash
uv run --no-sync python -m pytest \
  tests/test_eveauth_lifecycle.py \
  tests/test_eveskills_controller.py \
  tests/test_skills_wiring.py \
  tests/test_fittings_wiring.py -v
```

Expected: fail against the anonymous participant list and swallowed cleanup outcomes.

- [ ] **Step 4: Implement named fail-closed slots**

Initialize slots independently of controller construction:

```python
self._participants: dict[str, CharacterParticipant | None] = {
    application.SKILLS: None,
    application.FITTINGS: None,
}
self._cleanup_verification = {
    name: CleanupVerification(False, error=f"{name.title()} cleanup is unavailable.")
    for name in self._participants
}
```

Register successful controllers by capability in `wire_eve_controllers`:

```python
if skills is not None:
    authority.register_participant(application.SKILLS, skills)
if fittings is not None:
    authority.register_participant(application.FITTINGS, fittings)
```

Absent slots remain unverified. Aggregate `authority_removed` results after durable authority removal and retain exact blocked IDs in-process. Before accepting an unknown ID, rerun reconciliation for blocked slots and require both slots to verify clean.

- [ ] **Step 5: Run lifecycle and wiring tests and verify GREEN**

```bash
uv run --no-sync python -m pytest \
  tests/test_eveauth_lifecycle.py \
  tests/test_eveskills_controller.py \
  tests/test_skills_wiring.py \
  tests/test_fittings_wiring.py \
  tests/test_main.py -v
```

Expected: PASS, including restart with one unavailable feature controller.

- [ ] **Step 6: Commit**

```bash
git add wingman/eveauth/controller.py wingman/__main__.py \
  tests/test_eveauth_lifecycle.py tests/test_eveskills_controller.py \
  tests/test_skills_wiring.py tests/test_fittings_wiring.py
git commit -m "Make global character cleanup fail closed"
```

---

### Task 5: Build the Full Authorization State Machine

**Files:**
- Modify: `wingman/eveauth/controller.py`
- Modify: `wingman/eveauth/__init__.py`
- Modify: `tests/test_eveauth_controller.py`
- Modify: `tests/test_eveauth_lifecycle.py`

**Interfaces:**
- Consumes: `FULL_AUTH_SCOPES`, required cleanup verification
- Produces: `AuthorizationCommandResult(accepted: bool, error: str = "")`
- Produces: `start_full_authorization() -> AuthorizationCommandResult`
- Produces: `cancel_authorization() -> AuthorizationCommandResult`
- Produces: read-only `authorization_activity: str` and `authorization_notice: str`
- Removes after migration: `authenticate_skills()`, `enable_capability()`

- [ ] **Step 1: Write failing asynchronous-state tests**

Pin the command semantics and runtime state:

```python
def test_start_reports_acceptance_not_completion(authority):
    result = authority.start_full_authorization()
    assert result == AuthorizationCommandResult(True, "")
    assert authority.authorization_activity == "waiting"


def test_terminal_failure_is_bounded_runtime_state(authority, failing_sso):
    authority.start_full_authorization()
    failing_sso.finish()
    assert authority.authorization_activity == "idle"
    assert authority.authorization_notice
    assert len(authority.authorization_notice) <= 500
```

Cover unconfigured build, single-flight refusal, notice clearing on a new start, success clearing notice, cancellation without an error notice, and an old worker not clearing a newer attempt.

- [ ] **Step 2: Write deterministic cancellation-race tests**

Use injected barriers rather than sleeps. Pause exchange, validation, lifecycle-gate acquisition, and immediately before save. Assert:

```python
cancel = authority.cancel_authorization()
assert cancel.accepted is True
assert persisted_authority() == original
```

Block inside `save_authority` after the linearization point and assert Cancel waits, then returns `accepted=False` because commit won.

- [ ] **Step 3: Run authorization tests and verify RED**

```bash
uv run --no-sync python -m pytest tests/test_eveauth_controller.py tests/test_eveauth_lifecycle.py -v
```

Expected: fail because current auth uses a shared latch/event and Skills-only or targeted scope selection.

- [ ] **Step 4: Implement immutable attempts and one commit boundary**

Add:

```python
@dataclass(frozen=True)
class AuthorizationCommandResult:
    accepted: bool
    error: str = ""


@dataclass(frozen=True)
class _AuthorizationAttempt:
    attempt_id: int
    cancellation_generation: int
    known_generations: tuple[tuple[int, int], ...]
    cancelled: threading.Event
```

Guard `_active_attempt`, `_next_attempt_id`, `_cancellation_generation`, `_authorization_activity`, `_authorization_notice`, and listener ownership with the authority lock. `start_full_authorization()` always passes `FULL_AUTH_SCOPES`.

After token validation and lifecycle-gate acquisition, prepare cleanup verification and token wrapping, then acquire the authority lock. Recheck attempt ID, cancellation generation, character generation, owner compatibility, and roster; retain the lock through authority persistence and the atomic activity/notice update. Publish the semantic callback only after releasing locks.

- [ ] **Step 5: Implement owner compatibility and unknown-ID verification**

Use this exact matrix:

```python
def _owner_matches(stored: str, returned: str) -> bool:
    return not stored or not returned or stored == returned


def _merged_owner(stored: str, returned: str) -> str:
    return stored or returned
```

Two present unequal hashes refuse unchanged and instruct global forget. A known hash is never replaced by blank. Unknown IDs call the Task 4 verification before save. Keep generation snapshots so a forgotten row cannot be resurrected.

- [ ] **Step 6: Make stored-token decryption failure transition state**

When `_unwrap_token` returns `None`, use the grant invalidation path to set `needs_reauth=True`, clear the unusable blob, persist if possible, publish the authority event, and return a stable `decryption_failed` reason. Do not change the rotated-token memory-only fallback.

- [ ] **Step 7: Run focused authorization tests and verify GREEN**

```bash
uv run --no-sync python -m pytest \
  tests/test_eveauth_application.py \
  tests/test_eveauth_controller.py \
  tests/test_eveauth_lifecycle.py \
  tests/test_eveskills_controller.py \
  tests/test_evefittings_lifecycle.py -v
```

Expected: PASS for all owner-hash combinations, unknown-ID blocks, cancellation winners/losers, DPAPI paths, and existing Skills-only access before upgrade.

- [ ] **Step 8: Commit**

```bash
git add wingman/eveauth/controller.py wingman/eveauth/__init__.py \
  tests/test_eveauth_controller.py tests/test_eveauth_lifecycle.py
git commit -m "Centralize full EVE authorization"
```

---

### Task 6: Expose the Safe Shared Bridge Contract

**Files:**
- Modify: `wingman/eveauth/controller.py`
- Modify: `wingman/ui/api.py`
- Modify: `wingman/web/app.js`
- Create: `tests/test_api_characters.py`
- Modify: `tests/test_eveauth_controller.py`
- Modify: `tests/test_bridge_contract.py`
- Modify: `tests/test_api.py`

**Interfaces:**
- Produces: `eve_characters_state() -> dict`
- Produces: `eve_characters_authenticate() -> dict`
- Produces: `eve_characters_cancel_auth() -> dict`
- Produces: `eve_characters_forget(character_id) -> dict`
- Produces: semantic push `onEveAuthorityChanged`
- Produces browser event: `wm:eve-authority`

- [ ] **Step 1: Write failing payload and mutation tests**

Create `tests/test_api_characters.py` with a fake authority and exact expected shapes:

```python
def test_character_state_is_display_safe(tmp_path):
    authority = Mock()
    authority.management_state.return_value = {
        "authorization_activity": "idle",
        "authorization_notice": "",
        "characters": [
            {
                "character_id": 2,
                "character_name": "Aiga Otsolen",
                "authenticated_utc": "2026-09-04T12:00:00+00:00",
                "skills": "authorized",
                "fittings": "sign_in",
                "needs_reauth": False,
                "persistence_error": "",
            }
        ],
    }
    api = make_api(tmp_path, authority=authority)

    payload = api.eve_characters_state()

    encoded = repr(payload).lower()
    for forbidden in ("refresh_token", "access_token", "owner_hash", "scopes", "claims", "generation"):
        assert forbidden not in encoded


def test_forget_preserves_all_three_result_fields(tmp_path):
    authority = Mock()
    authority.forget.return_value = MutationResult(
        True, False, "Feature cleanup is incomplete."
    )
    api = make_api(tmp_path, authority=authority)

    assert api.eve_characters_forget(42) == {
        "applied": True,
        "persisted": False,
        "error": "Feature cleanup is incomplete.",
    }
```

Import `Mock`, `make_api`, and `MutationResult` in the new test module. In `tests/test_eveauth_controller.py`, separately assert that `management_state()` sorts rows by `(character_name.casefold(), character_id)`. Also test unavailable authority, warning/message bounds, invalid IDs, authorization start acceptance, cancellation loss/win, and capability values exactly `authorized` or `sign_in`.

- [ ] **Step 2: Write failing event-contract tests**

Require the literal push and browser fan-out:

```python
assert 'self._push("onEveAuthorityChanged", {})' in API_SOURCE
assert "'onEveAuthorityChanged'" in APP_JS
assert "new CustomEvent('wm:eve-authority'" in APP_JS
```

- [ ] **Step 3: Run tests and verify RED**

```bash
uv run --no-sync python -m pytest \
  tests/test_api_characters.py tests/test_eveauth_controller.py \
  tests/test_bridge_contract.py tests/test_api.py -v
```

Expected: missing shared methods and handler.

- [ ] **Step 4: Implement one locked management snapshot**

Add `AuthorityController.management_state()` that reads activity, notice, roster, token presence, capability statuses, and bounded persistence errors from one lock-consistent snapshot. `Api.eve_characters_state()` adds `available`, `auth_configured`, and authority startup warnings without exposing internal fields.

Map controller commands without converting asynchronous acceptance into success:

```python
return {"accepted": result.accepted, "error": result.error}
```

Map `MutationResult` without collapsing it to a Boolean.

- [ ] **Step 5: Publish and fan out one semantic event**

Change `Api._eve_authority_changed()` to the literal push above. In `app.js`, own the bridge handler once and dispatch `wm:eve-authority` for page modules. Do not push a complete roster.

- [ ] **Step 6: Run focused tests and verify GREEN**

```bash
uv run --no-sync python -m pytest \
  tests/test_api_characters.py tests/test_eveauth_controller.py \
  tests/test_bridge_contract.py tests/test_api.py -v
```

Expected: PASS, including the public-attribute recursion guard.

- [ ] **Step 7: Commit**

```bash
git add wingman/eveauth/controller.py wingman/ui/api.py wingman/web/app.js \
  tests/test_api_characters.py tests/test_eveauth_controller.py \
  tests/test_bridge_contract.py tests/test_api.py
git commit -m "Expose shared EVE character authority"
```

---

### Task 7: Add Settings Navigation and the Characters Section Shell

**Files:**
- Modify: `wingman/web/app.js`
- Modify: `wingman/web/index.html`
- Create: `wingman/web/characters.js`
- Modify: `wingman/web/style.css`
- Create: `tests/test_characters_page.py`
- Modify: `tests/test_settings_page.py`
- Modify: `tests/test_settings_eve_gate.py`
- Modify: `tests/test_page_conventions.py`
- Modify: `tests/test_packaging_completeness.py`
- Modify: `.github/actions/build-installer/action.yml`

**Interfaces:**
- Consumes: Task 6 bridge methods and `wm:eve-authority`
- Produces: `WM.openSettingsSection(name)`
- Produces: Settings section key `characters`

- [ ] **Step 1: Write failing navigation and shell tests**

Assert rail/pane order is:

```python
assert rail_sections == pane_sections == [
    "uploading", "characters", "bookmarks", "previews", "alerts", "general"
]
```

Require `characters` in `WM.EVE_SECTIONS`, `characters.js` after `app.js`, first heading **EVE authorization**, and installer critical-asset coverage. Add a navigation test proving one real `wm:section` entry event and preserved `WM.last_destination`.

- [ ] **Step 2: Run shell tests and verify RED**

```bash
uv run --no-sync python -m pytest \
  tests/test_characters_page.py \
  tests/test_settings_page.py \
  tests/test_settings_eve_gate.py \
  tests/test_packaging_completeness.py -v
```

Expected: missing section, module, gate entry, and helper.

- [ ] **Step 3: Implement event-correct Settings navigation**

Refactor section selection into a private helper and add:

```javascript
WM.openSettingsSection = function (name) {
  if (WM.current_route === 'settings') {
    WM.section(name);
    return;
  }
  selectSection(name);
  WM.route('settings');
};
```

`selectSection` updates classes/current state without dispatching. `WM.route('settings')` emits the one section-entry event. Add `characters` to `WM.EVE_SECTIONS`.

- [ ] **Step 4: Add the section markup and script shell**

Add IDs for `characters-count`, `characters-authenticate`, `characters-activity`, `characters-cancel`, `characters-notice`, `characters-filter`, `characters-filter-clear`, `characters-roster`, `characters-empty`, `characters-menu`, `characters-menu-forget`, and an always-mounted `characters-live` status region. Use **EVE authorization** as the surface heading.

Create `characters.js` as an IIFE that registers no duplicate global names and initially owns section enter/leave plus safe DOM lookups. Include it in the installer critical asset check.

- [ ] **Step 5: Add bounded section geometry**

Use the existing Settings tokens. Make only `#section-characters` and its roster flex to available height; keep the roster as the scroll owner. Add `[hidden]` overrides for every new selector that sets `display`.

- [ ] **Step 6: Run shell tests and verify GREEN**

```bash
uv run --no-sync python -m pytest \
  tests/test_characters_page.py tests/test_settings_page.py \
  tests/test_settings_eve_gate.py tests/test_page_conventions.py \
  tests/test_packaging_completeness.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add wingman/web/app.js wingman/web/index.html wingman/web/characters.js \
  wingman/web/style.css .github/actions/build-installer/action.yml \
  tests/test_characters_page.py tests/test_settings_page.py \
  tests/test_settings_eve_gate.py tests/test_page_conventions.py \
  tests/test_packaging_completeness.py
git commit -m "Add Settings character management shell"
```

---

### Task 8: Render and Operate the Character Roster

**Files:**
- Modify: `wingman/web/characters.js`
- Modify: `wingman/web/style.css`
- Modify: `tests/test_characters_page.py`
- Modify: `tests/test_page_conventions.py`

**Interfaces:**
- Consumes: `eve_characters_state`, authenticate/cancel/forget bridge actions
- Consumes: `wm:section`, `wm:eve-authority`
- Produces: dense filtered roster and one reusable menu

- [ ] **Step 1: Write failing state/render tests**

Lexically pin these behaviors:

```python
assert "WM.send('eve_characters_state')" in CODE
assert "requestSequence += 1" in CODE
assert "row.skills === 'authorized'" in CODE
assert "row.fittings === 'authorized'" in CODE
assert "characters.length" in CODE
```

Require a fresh read on every Characters section entry, visible-only event re-read, stale-reply rejection, programmatic filter label, clear behavior, rendered authenticated time, and distinct empty/unavailable/no-match copy.

- [ ] **Step 2: Write failing authorization-control tests**

Require **Authenticate character…**, waiting state, duplicate-start disabling, Cancel, terminal notice rendering, and no optimistic row mutation. The start callback may show only immediate rejection; completion comes from a later state read.

- [ ] **Step 3: Write failing menu and forget tests**

Require one fixed-position menu portal with:

```html
aria-haspopup="menu"
role="menu"
role="menuitem"
```

Pin synchronized `aria-expanded`, row-specific accessible naming, viewport clamping/open-upward logic, Arrow Up/Down, Home/End, Enter/Space, Escape, outside close, and trigger focus restoration. Assert `WM.confirm` and all three forget outcomes are rendered correctly.

- [ ] **Step 4: Run page tests and verify RED**

```bash
uv run --no-sync python -m pytest tests/test_characters_page.py tests/test_page_conventions.py -v
```

Expected: the shell lacks rendering and interactions.

- [ ] **Step 5: Implement state reads and dense rendering**

Use a monotonically increasing request sequence:

```javascript
function requestState() {
  requestSequence += 1;
  var wanted = requestSequence;
  WM.send('eve_characters_state').then(function (payload) {
    if (wanted !== requestSequence || !isVisible()) return;
    render(payload);
  });
}
```

Build rows with DOM text properties only. Derive the count from `characters.length`. Render `Authorized` and `Sign in`; do not display snapshot freshness.

- [ ] **Step 6: Implement auth actions and one accessible menu**

Authentication and cancellation call shared endpoints. The menu is outside the roster scroller, uses fixed positioning, and stores its trigger/character ID. Confirm Forget with exact consequence copy, then render:

- refusal: retain row and show error;
- applied but not persisted: re-read and show cleanup warning;
- complete: re-read and announce removal.

- [ ] **Step 7: Run page tests and verify GREEN**

```bash
uv run --no-sync python -m pytest \
  tests/test_characters_page.py tests/test_page_conventions.py tests/test_bridge_contract.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add wingman/web/characters.js wingman/web/style.css \
  tests/test_characters_page.py tests/test_page_conventions.py
git commit -m "Build the character authorization roster"
```

---

### Task 9: Hand Skills and Fittings Off to Settings

**Files:**
- Modify: `wingman/web/index.html`
- Modify: `wingman/web/skills.js`
- Modify: `wingman/web/fittings.js`
- Modify: `wingman/web/style.css`
- Modify: `wingman/ui/api.py`
- Modify: `wingman/eveauth/controller.py`
- Modify: `wingman/eveskills/controller.py`
- Modify: `wingman/evefittings/controller.py`
- Modify: `tests/test_skills_page.py`
- Modify: `tests/test_fittings_page.py`
- Modify: `tests/test_api_skills.py`
- Modify: `tests/test_api_fittings.py`
- Modify: `tests/test_fittings_wiring.py`
- Modify: `tests/test_bridge_contract.py`

**Interfaces:**
- Consumes: `WM.openSettingsSection('characters')`
- Removes: old Skills/Fittings auth and forget page/API methods
- Preserves: Skills refresh and Fittings refresh/copy target eligibility

- [ ] **Step 1: Write failing Skills handoff tests**

Require `#skills-manage-characters` and its call to `WM.openSettingsSection('characters')`. Add negative assertions for `skills_add_character`, `skills_cancel_auth`, `skills_forget_character`, row **Re-authenticate**, and row Forget controls. Require the empty/recovery copy to name Settings and retain non-actionable reauthentication status.

- [ ] **Step 2: Write failing Fittings handoff tests**

Require `#fittings-manage-characters`, remove all `fittings-characters-*` overlay IDs, and forbid `fittings_enable_character`, `fittings_cancel_auth`, and `fittings_forget_character`. Pin the new empty-state sequence and copy-target text:

```text
Authenticate a character in Settings › Characters, then return and press Refresh characters.
```

Keep assertions for Fittings refresh, `STATE.characters`, copy eligibility, and the one accent action.

- [ ] **Step 3: Run handoff tests and verify RED**

```bash
uv run --no-sync python -m pytest \
  tests/test_skills_page.py tests/test_fittings_page.py \
  tests/test_api_skills.py tests/test_api_fittings.py \
  tests/test_fittings_wiring.py tests/test_bridge_contract.py -v
```

Expected: old controls and APIs are still present.

- [ ] **Step 4: Replace both controls with navigation**

Wire each **Manage characters…** button to the shell helper. Remove Skills auth progress, row action generation, confirming state, and obsolete “only surface” comments. Remove Fittings overlay state, renderers, keyboard branch, markup, and CSS. Keep task-specific refresh and copy state.

- [ ] **Step 5: Remove dead Python and dev-facing interfaces**

After verifying callers with `rg`, remove:

```text
AuthorityController.authenticate_skills
AuthorityController.enable_capability
skills_add_character / skills_cancel_auth / skills_forget_character
fittings_enable_character / fittings_cancel_auth / fittings_forget_character
```

Remove obsolete Skills controller compatibility delegates only if `rg` confirms no production caller. Remove `auth_configured` and `auth_in_progress` from feature payloads once no page consumes them.

- [ ] **Step 6: Run handoff and feature regression tests**

```bash
uv run --no-sync python -m pytest \
  tests/test_api_skills.py tests/test_api_fittings.py \
  tests/test_skills_page.py tests/test_fittings_page.py \
  tests/test_skills_wiring.py tests/test_fittings_wiring.py \
  tests/test_eveskills_controller.py tests/test_evefittings_copy.py -v
```

Expected: PASS; refresh and fitting-copy behavior are unchanged.

- [ ] **Step 7: Commit**

```bash
git add wingman/web/index.html wingman/web/skills.js wingman/web/fittings.js \
  wingman/web/style.css wingman/ui/api.py wingman/eveauth/controller.py \
  wingman/eveskills/controller.py wingman/evefittings/controller.py \
  tests/test_skills_page.py tests/test_fittings_page.py \
  tests/test_api_skills.py tests/test_api_fittings.py \
  tests/test_fittings_wiring.py tests/test_bridge_contract.py
git commit -m "Move character authorization into Settings"
```

---

### Task 10: Repair the Shared Skills and Fittings Workspace Geometry

**Files:**
- Modify: `wingman/web/index.html`
- Modify: `wingman/web/style.css`
- Modify: `tests/test_skills_page.py`
- Modify: `tests/test_fittings_page.py`

**Interfaces:**
- Produces: `.eve-workspace` parent geometry
- Produces: `.workspace-primary` heading-action alignment

- [ ] **Step 1: Write failing geometry tests**

Parse the CSS block and require all five properties:

```python
for route_id in ("route-skills", "route-fittings"):
    assert f'id="{route_id}"' in HTML
    assert "eve-workspace" in route_open_tag(route_id)

workspace = css_block(".eve-workspace")
assert "grid-template-columns: 214px minmax(0, 1fr)" in workspace
assert "gap: 12px" in workspace
assert "padding: 12px" in workspace
assert "min-height: 0" in workspace
```

Require `.eve-workspace.active { display: grid; }` and a shared rule that gives both primary actions `margin-left:auto` and `align-self:center`.

- [ ] **Step 2: Run geometry tests and verify RED**

```bash
uv run --no-sync python -m pytest tests/test_skills_page.py tests/test_fittings_page.py -v
```

Expected: Fittings lacks the parent grid/inset/gap and shared action alignment.

- [ ] **Step 3: Implement the shared parent and action classes**

Use:

```css
.eve-workspace {
  display: none;
  grid-template-columns: 214px minmax(0, 1fr);
  gap: 12px;
  padding: 12px;
  min-height: 0;
}
.eve-workspace.active { display: grid; }
.skills-head > .workspace-primary { margin-left: auto; align-self: center; }
```

Add `eve-workspace` to both route roots and `workspace-primary` to **Copy plan** and **Copy selected**. Remove the superseded `#route-skills` geometry and `#skills-copy-plan` alignment declarations without changing the rail or pane child styles.

- [ ] **Step 4: Run geometry and convention tests**

```bash
uv run --no-sync python -m pytest \
  tests/test_skills_page.py tests/test_fittings_page.py tests/test_page_conventions.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add wingman/web/index.html wingman/web/style.css \
  tests/test_skills_page.py tests/test_fittings_page.py
git commit -m "Share EVE workspace geometry"
```

---

### Task 11: Add Dev Scenarios, Screenshot Coverage, and Current Documentation

**Files:**
- Modify: `wingman/web/dev.js`
- Modify: `scripts/shoot_screens.py`
- Modify: `tests/test_dev_harness.py`
- Modify: `tests/test_shoot_screens.py`
- Modify: `tests/test_packaging_completeness.py`
- Modify: `README.md`
- Modify: `DESIGN.md`
- Modify: `docs/smoke-checklist.md`
- Modify: `.pi/prompts/screenshots.md`

**Interfaces:**
- Produces dev scenarios: `full`, `partial`, `reauthentication`, `warning`, `empty`, `waiting`, `terminal-failure`, `partial-cleanup`, `maximum-50`, `unavailable`
- Removes screenshot: `fittings-characters`
- Adds screenshots: `settings-characters`, `settings-characters-waiting`, `settings-characters-narrow`, `fittings-narrow`

- [ ] **Step 1: Write failing fixture and screenshot inventory tests**

Require exact scenario names, 50 unique IDs in `maximum-50`, no credential/hash/raw-scope fields, and shared bridge doubles. Require the new screenshot inventory and absence of `fittings-characters`.

Generalize `Screen` with an explicit floor-size field rather than adding key-specific branches:

```python
@dataclass(frozen=True)
class Screen:
    key: str
    label: str
    route: str
    section: str | None = None
    eve: bool = False
    at_floor: bool = False
```

- [ ] **Step 2: Run dev/screenshot tests and verify RED**

```bash
uv run --no-sync python -m pytest \
  tests/test_dev_harness.py tests/test_shoot_screens.py \
  tests/test_packaging_completeness.py -v
```

Expected: missing character fixtures/screens and obsolete Fittings overlay staging.

- [ ] **Step 3: Implement safe deterministic dev scenarios**

Add shared `eve_characters_*` doubles and one fixture table in `dev.js`. Mutations update only fake authority state and invoke `window.onEveAuthorityChanged({reason: ...})`; they never fabricate credentials or call production writers. Remove obsolete per-feature auth doubles.

- [ ] **Step 4: Update screenshot staging**

Remove old Fittings Characters reset/setup code. Add read-only staging for normal, waiting, partial-cleanup, and 50-row states. The narrow setup opens the overflow menu on the last visible row through real page controls. Add a floor-sized Fittings capture proving the repaired inset, rail width, gap, and action placement.

- [ ] **Step 5: Update current documentation and copy**

Update README and smoke checks to describe:

- Settings › Characters as the sole authorization/forget surface;
- all four Skills-and-Fittings scopes;
- existing Skills-only compatibility;
- generic returned-character matching;
- known-owner mismatch refusal and missing-owner compatibility;
- cancellation winner/loser behavior;
- partial cleanup and blocked re-add;
- 50-row keyboard/menu checks;
- Fittings spacing at 100%, 125%, 150%, and 200% scaling.

Update `DESIGN.md` statements that call Skills the authorization/forget surface and comments/counts that describe five Settings entries or three EVE-gated sections. Do not alter historical documents.

- [ ] **Step 6: Run fixture, screenshot, and documentation tests**

```bash
uv run --no-sync python -m pytest \
  tests/test_dev_harness.py tests/test_shoot_screens.py \
  tests/test_packaging_completeness.py tests/test_characters_page.py \
  tests/test_skills_page.py tests/test_fittings_page.py -v
```

Expected: PASS.

- [ ] **Step 7: Run the stale-contract scan**

```bash
rg -n \
  --glob '!docs/history/**' \
  --glob '!docs/superpowers/specs/**' \
  --glob '!docs/superpowers/plans/**' \
  "Enable fittings|skills_add_character|skills_forget_character|fittings_enable_character|fittings_forget_character|fittings_cancel_auth" \
  wingman README.md DESIGN.md docs/smoke-checklist.md .pi/prompts
```

Expected: no obsolete active product-contract references. Negative assertions remain in tests, and approved historical/specification records are excluded rather than rewritten.

- [ ] **Step 8: Commit**

```bash
git add wingman/web/dev.js scripts/shoot_screens.py \
  tests/test_dev_harness.py tests/test_shoot_screens.py \
  tests/test_packaging_completeness.py README.md DESIGN.md \
  docs/smoke-checklist.md .pi/prompts/screenshots.md
git commit -m "Document centralized EVE authorization"
```

---

### Task 12: Polish and Verify the Complete Change

**Files:**
- Review all files changed since `97f5c1f`
- Update only files required by verified findings

**Interfaces:**
- Consumes all prior task deliverables
- Produces a review-ready branch with fresh verification evidence

- [ ] **Step 1: Run focused integration gates**

```bash
uv run --no-sync python -m pytest \
  tests/test_eveauth_application.py \
  tests/test_eveauth_controller.py \
  tests/test_eveauth_lifecycle.py \
  tests/test_api_characters.py \
  tests/test_bridge_contract.py \
  tests/test_characters_page.py \
  tests/test_settings_page.py \
  tests/test_settings_eve_gate.py \
  tests/test_skills_page.py \
  tests/test_fittings_page.py \
  tests/test_page_conventions.py \
  tests/test_packaging_completeness.py -v
```

Expected: PASS.

- [ ] **Step 2: Run the full automated suite and static gates**

```bash
uv run --no-sync python -m pytest tests/
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
```

Expected: all tests pass, Ruff reports no lint or formatting errors.

- [ ] **Step 3: Run the required changed-code polish pass**

Invoke `polish-core --fix` against the implementation range beginning at `97f5c1f`. Inspect every edit, reject scope expansion, and rerun Step 1 and Step 2 after accepted fixes.

- [ ] **Step 4: Inspect the final diff for scope and dead paths**

```bash
git diff --check 97f5c1f..HEAD
git diff --stat 97f5c1f..HEAD
git status --short
rg -n "TO[D]O|FIX[M]E|console\.log|pdb\.set_trace" wingman tests scripts
```

Expected: no whitespace errors, unintended debug output, placeholders, dead old authorization controls, or uncommitted files.

- [ ] **Step 5: Run manual rendering and Windows checks**

Generate the screenshot inventory:

```bash
python scripts/shoot_screens.py
```

Then execute the updated `docs/smoke-checklist.md` in Windows/WebView2, including 840x625 at 100%, 125%, 150%, and 200%; keyboard-only menu operation; real new/existing/partial authorization; cancellation; owner mismatch where controlled credentials permit; partial cleanup/restart; and repaired Fittings spacing. Record anything not executable as an explicit remaining risk rather than claiming it passed.

- [ ] **Step 6: Commit any verified polish or documentation corrections**

```bash
git add -u
git commit -m "Polish centralized character authorization"
```

Skip this commit only if the polish pass and final verification produce no file changes.
