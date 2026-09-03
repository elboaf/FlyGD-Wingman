# Character Fittings Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persistent, consolidated EVE fitting library and an explicit, additive workflow for copying selected fittings across a user's authorized characters.

**Architecture:** Extract app-wide EVE identity and OAuth ownership from `eveskills` into `eveauth`, with capability-specific scopes and one lifecycle gate per character. Add `evefittings` as a separate single-writer subsystem for canonical fitting data, curation, authoritative snapshots, and durable copy intents; expose it through a paged Fittings destination without changing the no-framework web stack.

**Tech Stack:** Python 3.11, stdlib dataclasses/threading/urllib/hashlib/json, DPAPI on Windows, EVE SSO/ESI, pywebview 6.2.1, plain HTML/CSS/ES5 JavaScript, pytest, Ruff, PyInstaller/Inno Setup.

**Spec:** `docs/superpowers/specs/2026-09-03-character-fittings-design.md`

## Global Constraints

- Read `CLAUDE.md`, `PRODUCT.md`, `DESIGN.md`, and the spec before each task; repository instructions override this plan.
- Work only in the linked worktree on `feature/fittings-management`; do not write to the primary checkout.
- Use TDD for every behavior: failing focused test, minimal implementation, passing focused test, then broader regression.
- Preserve existing Skills behavior and existing `eve_skills.json` data throughout migration.
- Existing Skills-only grants must keep working; fitting scopes are requested only after explicit per-character opt-in.
- Never follow authenticated redirects or log bearer/refresh tokens.
- ESI creates are exactly one network attempt; timeout, no response, `408`, `5xx`, and malformed `201` are Unknown.
- Persist a per-pair intent before every fitting POST; never send when intent persistence fails.
- Never delete or replace a remote fitting. No polling, background synchronization, EFT import/export, fitting-only onboarding, telemetry, framework, build step, or bundler.
- Fitting equivalence ignores numbered positions within high, medium, low, rig, subsystem, and service racks; cargo, drones, fighters, charges, scripts, type IDs, and quantities remain identity.
- Every authoritative remote snapshot is all-or-nothing. Bounds refuse data; they never silently truncate curated content or authoritative presence.
- Keep `Api` non-method attributes underscore-prefixed and use literal `_push("handler", payload)` adapters so bridge tests can see them.
- The viewport floor is 840×625 CSS pixels. The fourth destination requires measured title-bar clearance before the full route is built.
- Python package additions must be listed explicitly in `pyproject.toml`.
- Run after every task: `uv run --no-sync python -m pytest tests/`, `uv run --extra dev ruff check .`, and `uv run --extra dev ruff format --check .`.
- Do not claim the Windows UI or EVE authorization path is verified without completing the corresponding manual smoke steps on Windows.

## File Structure

### Shared EVE infrastructure

- Create `wingman/eveauth/__init__.py`: narrow public capability and authority exports.
- Create `wingman/eveauth/application.py`: shared EVE application identity, endpoints, and capability scope sets.
- Create `wingman/eveauth/{dpapi,tokens,jwt,loopback,sso}.py`: moved authorization primitives.
- Create `wingman/eveauth/state.py`: authority-only state and atomic persistence.
- Create `wingman/eveauth/migration.py`: non-mutating legacy inspection and ordered split migration.
- Create `wingman/eveauth/controller.py`: credential lifecycle, authorization, token refresh, lifecycle leases, generations, and global forget.
- Create `wingman/eveesi.py`: shared secure read transport and one-attempt mutation transport.
- Keep `wingman/eveskills/{application,dpapi,tokens,jwt,loopback,sso,esi}.py` as compatibility re-exports until all callers and tests use the new owners.

### Fittings subsystem

- Create `wingman/evefittings/__init__.py`: minimal public controller export.
- Create `wingman/evefittings/contracts.py`: pinned ESI limits, routes, flags, state/page/operation bounds.
- Create `wingman/evefittings/model.py`: remote validation, canonicalization, templates, fingerprints, metadata, collections, and supersession.
- Create `wingman/evefittings/store.py`: fitting state, backups, tolerant local recovery, and intent recovery.
- Create `wingman/evefittings/names.py`: rebuildable type-name cache.
- Create `wingman/evefittings/controller.py`: workspace queries, refresh/import, curation, preflight, copy, reconciliation, and shutdown.

### Web and integration

- Create `wingman/web/fittings.js`: Fittings route, overlays, paging, curation, and copy progress.
- Modify `wingman/web/index.html`, `app.js`, and `style.css`: destination, markup, handlers, route gate, and two-pane styling.
- Modify `wingman/ui/api.py`: thin Fittings bridge and literal push adapters.
- Modify `wingman/__main__.py`: build and connect authority, Skills, and Fittings controllers.
- Modify `wingman/paths.py`, `pyproject.toml`, build checks, dev harness, screenshot inventory, README, DESIGN, and smoke checklist.

---

### Task 1: Pin Fitting Contracts and Add One-Attempt ESI Mutations

**Files:**
- Create: `wingman/evefittings/__init__.py`
- Create: `wingman/evefittings/contracts.py`
- Create: `wingman/eveesi.py`
- Create: `tests/test_evefittings_contracts.py`
- Create: `tests/test_eveesi_mutation.py`
- Create: `tests/fixtures/evefittings/get-small.json`
- Create: `tests/fixtures/evefittings/get-equivalent-slots.json`
- Create: `tests/fixtures/evefittings/get-invalid-flag.json`
- Modify: `wingman/eveskills/esi.py`
- Modify: `tests/test_eveskills_esi.py`

**Interfaces:**
- Produces: `EsiClient.get(...) -> EsiResponse`, compatibility re-exported from `eveskills.esi`.
- Produces: `EsiClient.post_once(path, body, *, token) -> MutationResponse`.
- Produces: fitting route, schema, flag, cache, page, state, and operation constants.

- [ ] **Step 1: Add sanitized contract fixtures**

Record representative payloads containing high/medium/low modules, rigs, subsystems, cargo, drones, fighters, charges, duplicate type rows, different numbered-slot order, and schema-defined `Invalid`. Use synthetic names and IDs; include no character identity or token.

- [ ] **Step 2: Write failing contract tests**

```python
from wingman.evefittings import contracts


def test_create_contract_is_pinned_to_current_esi_limits():
    assert contracts.READ_SCOPE == "esi-fittings.read_fittings.v1"
    assert contracts.WRITE_SCOPE == "esi-fittings.write_fittings.v1"
    assert contracts.MAX_NAME_CHARS == 50
    assert contracts.MAX_DESCRIPTION_CHARS == 500
    assert contracts.MAX_CREATE_ITEMS == 512
    assert contracts.READ_CACHE_SECONDS == 300
    assert contracts.MAX_COPY_WRITES == 20


def test_local_bounds_are_explicit_refusal_boundaries():
    assert contracts.MAX_REMOTE_FITTINGS == 500
    assert contracts.MAX_LIBRARY_ENTRIES == 10_000
    assert contracts.MAX_COLLECTIONS == 200
    assert contracts.MAX_ALIASES_PER_ENTRY == 100
    assert contracts.PAGE_SIZE == 100
    assert contracts.MAX_OPERATION_RECORDS == 200
    assert contracts.MAX_STATE_BYTES == 64 * 1024 * 1024
```

- [ ] **Step 3: Run the contract tests and confirm red**

Run: `uv run --no-sync python -m pytest tests/test_evefittings_contracts.py -v`
Expected: FAIL because `wingman.evefittings.contracts` does not exist.

- [ ] **Step 4: Implement the constants and accepted-flag inventory**

```python
READ_SCOPE = "esi-fittings.read_fittings.v1"
WRITE_SCOPE = "esi-fittings.write_fittings.v1"
GET_PATH = "/characters/{character_id}/fittings"
POST_PATH = "/characters/{character_id}/fittings"
MAX_NAME_CHARS = 50
MAX_DESCRIPTION_CHARS = 500
MAX_CREATE_ITEMS = 512
READ_CACHE_SECONDS = 300
MAX_COPY_WRITES = 20
MAX_REMOTE_FITTINGS = 500
MAX_LIBRARY_ENTRIES = 10_000
MAX_COLLECTIONS = 200
MAX_COLLECTION_NAME_CHARS = 80
MAX_ALIASES_PER_ENTRY = 100
PAGE_SIZE = 100
MAX_OPERATION_RECORDS = 200
MAX_STATE_BYTES = 64 * 1024 * 1024
```

Declare `ACCEPTED_FLAGS` from the pinned OpenAPI enum, including `Invalid`; derive rack mappings from that inventory and assert there are no unclassified accepted flags.

- [ ] **Step 5: Write failing one-attempt transport tests**

```python
def test_post_once_never_retries_a_timeout():
    calls = []

    def transport(request, timeout=None):
        calls.append(request)
        raise TimeoutError("after send")

    result = EsiClient(user_agent="test", transport=transport).post_once(
        "/characters/42/fittings", {"name": "Fit"}, token="long-secret-token"
    )

    assert len(calls) == 1
    assert result.response_received is False
    assert result.status is None
    assert "long-secret-token" not in result.error


def test_post_once_preserves_a_real_500_as_received():
    result = client_for_http_error(500).post_once(PATH, BODY, token=TOKEN)
    assert result.response_received is True
    assert result.status == 500
```

Also cover `201`, malformed `201`, `408`, `420`, `429`, bounded response bodies/headers, redirect refusal, and token redaction.

- [ ] **Step 6: Run mutation tests and confirm red**

Run: `uv run --no-sync python -m pytest tests/test_eveesi_mutation.py -v`
Expected: FAIL because `wingman.eveesi` and `MutationResponse` do not exist.

- [ ] **Step 7: Extract secure transport and implement `post_once`**

```python
@dataclass(frozen=True)
class MutationResponse:
    response_received: bool
    status: int | None
    data: object
    error: str
    headers: dict[str, str]


def post_once(self, path: str, body, *, token: str) -> MutationResponse:
    """Make exactly one request; never synthesize or retry an outcome."""
```

Reuse path hardening, no-redirect opener, bounded reads, sanitization, redaction, and rate-header extraction. Keep existing GET and `/universe/ids/` behavior unchanged. Make `wingman/eveskills/esi.py` re-export the shared symbols rather than duplicate active logic.

- [ ] **Step 8: Run focused and compatibility tests**

Run: `uv run --no-sync python -m pytest tests/test_evefittings_contracts.py tests/test_eveesi_mutation.py tests/test_eveskills_esi.py -v`
Expected: PASS.

- [ ] **Step 9: Run full gates and commit**

```bash
git add wingman/eveesi.py wingman/evefittings wingman/eveskills/esi.py tests/test_eveesi_mutation.py tests/test_evefittings_contracts.py tests/test_eveskills_esi.py tests/fixtures/evefittings
git commit -m "feat: pin fitting contracts and safe mutation transport"
```

---

### Task 2: Extract Shared Authentication Primitives and Capability Scopes

**Files:**
- Create: `wingman/eveauth/__init__.py`
- Create: `wingman/eveauth/application.py`
- Create: `wingman/eveauth/{dpapi,tokens,jwt,loopback,sso}.py`
- Modify: `wingman/eveskills/{application,dpapi,tokens,jwt,loopback,sso}.py`
- Create: `tests/test_eveauth_application.py`
- Create: `tests/test_eveauth_sso.py`
- Modify: `tests/test_eveskills_paths.py`
- Modify: `tests/test_eveskills_sso.py`
- Modify: `tests/test_eveskills_jwt.py`
- Modify: `tests/test_eveskills_loopback.py`
- Modify: `tests/test_eveskills_tokens.py`
- Modify: `tests/test_eveskills_dpapi.py`

**Interfaces:**
- Produces: `SKILLS`, `FITTINGS`, `SKILLS_SCOPES`, `FITTINGS_SCOPES`, `CAPABILITY_SCOPES`.
- Produces: `sso.authorize_url(pkce, scopes)` with no implicit all-scope default.
- Preserves: existing `eveskills.*` imports through compatibility modules.

- [ ] **Step 1: Write failing capability and explicit-scope tests**

```python
def test_capabilities_have_separate_scope_sets():
    assert application.CAPABILITY_SCOPES[application.SKILLS] == frozenset(
        {"esi-skills.read_skills.v1", "esi-skills.read_skillqueue.v1"}
    )
    assert application.CAPABILITY_SCOPES[application.FITTINGS] == frozenset(
        {"esi-fittings.read_fittings.v1", "esi-fittings.write_fittings.v1"}
    )


def test_authorize_url_uses_only_explicit_scopes():
    url = sso.authorize_url(pkce, application.SKILLS_SCOPES)
    assert query_of(url)["scope"] == " ".join(sorted(application.SKILLS_SCOPES))
    assert "esi-fittings" not in url
```

- [ ] **Step 2: Run tests and confirm red**

Run: `uv run --no-sync python -m pytest tests/test_eveauth_application.py tests/test_eveauth_sso.py -v`
Expected: FAIL because `eveauth` does not exist.

- [ ] **Step 3: Move primitives and add compatibility exports**

Move implementation ownership into `eveauth`; keep old modules as narrow imports such as:

```python
from ..eveauth.sso import *  # noqa: F403 - compatibility surface during migration
```

Prefer explicit exports where monkeypatch-sensitive tests require module ownership. Update production consumers to patch/inject the symbol they actually use rather than aliasing `sys.modules`.

- [ ] **Step 4: Make scope choice mandatory**

```python
def authorize_url(pkce: Pkce, scopes: Iterable[str]) -> str:
    requested = tuple(sorted(frozenset(scopes)))
    if not requested:
        raise ValueError("At least one EVE scope is required.")
```

Update existing Skills callers and tests to pass `SKILLS_SCOPES` explicitly. Do not define an authorization path that defaults to all capabilities.

- [ ] **Step 5: Run all authentication compatibility tests**

Run: `uv run --no-sync python -m pytest tests/test_eveauth_application.py tests/test_eveauth_sso.py tests/test_eveskills_paths.py tests/test_eveskills_sso.py tests/test_eveskills_jwt.py tests/test_eveskills_loopback.py tests/test_eveskills_tokens.py tests/test_eveskills_dpapi.py -v`
Expected: PASS.

- [ ] **Step 6: Run full gates and commit**

```bash
git add wingman/eveauth wingman/eveskills tests/test_eveauth_application.py tests/test_eveauth_sso.py tests/test_eveskills_*.py
git commit -m "refactor: extract shared EVE authentication primitives"
```

---

### Task 3: Add Authority State and Fail-Closed Legacy Migration

**Files:**
- Create: `wingman/eveauth/state.py`
- Create: `wingman/eveauth/migration.py`
- Create: `tests/test_eveauth_state.py`
- Create: `tests/test_eveauth_migration.py`
- Create: `tests/fixtures/eveauth/legacy-valid.json`
- Create: `tests/fixtures/eveauth/legacy-empty.json`
- Modify: `wingman/paths.py:111-127`
- Modify: `wingman/eveskills/state.py`
- Modify: `tests/test_eveskills_state.py`
- Modify: `tests/test_paths.py`

**Interfaces:**
- Produces: `AuthorityCharacter`, `AuthorityState`, `load_authority`, `save_authority`.
- Produces: `LegacyDisposition`, `LegacyLoadResult`, `MigrationResult`, `inspect_legacy_skills`, `migrate_legacy_skills`.
- Produces paths: `eve_authority_file()` and `eve_fittings_file()`.

- [ ] **Step 1: Write failing authority-state round-trip tests**

```python
def test_authority_round_trip_keeps_only_identity_and_credentials(tmp_path):
    original = AuthorityState(characters=[authority_character(42)])
    save_authority(tmp_path / "eve_authority.json", original)
    loaded, warnings = load_authority(tmp_path / "eve_authority.json")
    assert loaded == original
    assert warnings == ()
    assert "active_levels" not in (tmp_path / "eve_authority.json").read_text()
```

Cover 50-character bound, scope bound, DPAPI blob text bound, duplicate IDs, atomic replacement, sibling backup, permissions, corrupt-file preservation, and bounded reads.

- [ ] **Step 2: Write failing non-mutating migration-inspection tests**

```python
def test_access_failure_is_failed_not_absent(tmp_path, monkeypatch):
    path = tmp_path / "eve_skills.json"
    path.write_text("{}")
    monkeypatch.setattr(Path, "open", raising_permission_error_for(path))
    result = inspect_legacy_skills(path)
    assert result.disposition is LegacyDisposition.FAILED
    assert result.state is None


def test_inspection_never_moves_or_rewrites_corrupt_evidence(tmp_path):
    path = tmp_path / "eve_skills.json"
    path.write_text("not json")
    before = tuple(tmp_path.iterdir())
    result = inspect_legacy_skills(path)
    assert result.disposition is LegacyDisposition.FAILED
    assert tuple(tmp_path.iterdir()) == before
```

Cover genuinely absent, primary valid, primary corrupt plus valid backup (`RECOVERED`), both unreadable, oversized, and empty-but-valid documents.

- [ ] **Step 3: Run migration tests and confirm red**

Run: `uv run --no-sync python -m pytest tests/test_eveauth_state.py tests/test_eveauth_migration.py -v`
Expected: FAIL because authority state and migration modules do not exist.

- [ ] **Step 4: Implement structured non-mutating inspection**

```python
class LegacyDisposition(Enum):
    ABSENT = "absent"
    LOADED = "loaded"
    RECOVERED = "recovered"
    FAILED = "failed"


@dataclass(frozen=True)
class LegacyLoadResult:
    state: SkillsState | None
    disposition: LegacyDisposition
    warnings: tuple[str, ...]
    error: str
```

Read primary and backup directly through bounded parsing helpers that perform no rename, restore, preserve, chmod, or save side effect.

- [ ] **Step 5: Write failing ordered-migration tests**

Inject save functions and record calls. Assert authority saves first, Skills stripping second; failure before authority writes nothing; failure after authority leaves resumable authority; corrupt existing authority never falls back to legacy; and no completion marker is written for `FAILED`.

- [ ] **Step 6: Implement ordered migration and paths**

```python
def eve_authority_file() -> Path:
    return state_dir() / "eve_authority.json"


def eve_fittings_file() -> Path:
    return state_dir() / "eve_fittings.json"
```

`migrate_legacy_skills` proceeds only for `ABSENT`, `LOADED`, or `RECOVERED`, saves authority first, then saves stripped Skills state with `authority_migrated: true`. Existing valid authority is one-way authoritative.

- [ ] **Step 7: Run focused migration and legacy-state suites**

Run: `uv run --no-sync python -m pytest tests/test_eveauth_state.py tests/test_eveauth_migration.py tests/test_eveskills_state.py tests/test_paths.py -v`
Expected: PASS.

- [ ] **Step 8: Run full gates and commit**

```bash
git add wingman/eveauth/state.py wingman/eveauth/migration.py wingman/eveskills/state.py wingman/paths.py tests/test_eveauth_state.py tests/test_eveauth_migration.py tests/test_eveskills_state.py tests/test_paths.py tests/fixtures/eveauth
git commit -m "feat: add shared EVE authority migration"
```

---

### Task 4: Implement Authority Controller and Lifecycle Leases

**Files:**
- Create: `wingman/eveauth/controller.py`
- Create: `tests/test_eveauth_controller.py`
- Create: `tests/test_eveauth_lifecycle.py`
- Modify: `wingman/eveauth/__init__.py`

**Interfaces:**
- Produces immutable `AuthorityCharacter`, `AccessTokenResult`, `MutationResult`, and `LifecycleLease`.
- Produces `AuthorityController.characters`, `character`, `capability_status`, `access_token`, `lifecycle`, `authenticate_skills`, `enable_capability`, `cancel_auth`, `forget`, `register_participant`, and `shutdown`.
- Produces participant hooks `prepare_forget`, `authority_removed`, `grant_invalidated`, and `reconcile_characters`.

- [ ] **Step 1: Write failing capability and token-refresh tests**

```python
def test_skills_capability_accepts_a_skills_only_grant(authority):
    assert authority.capability_status(42, SKILLS) == "enabled"
    assert authority.capability_status(42, FITTINGS) == "enable"


def test_fitting_403_does_not_delete_shared_credentials(authority):
    authority.record_operation_error(42, FITTINGS, 403, "Forbidden")
    assert authority.character(42).grant_invalid is False
    assert authority.has_refresh_token(42)
```

Cover validated-claim scope subsets, `invalid_grant`, identity mismatch, owner mismatch, token rotation, rotation save failure retaining the new token in memory, and one refresh call across concurrent consumers.

- [ ] **Step 2: Run controller tests and confirm red**

Run: `uv run --no-sync python -m pytest tests/test_eveauth_controller.py -v`
Expected: FAIL because `AuthorityController` does not exist.

- [ ] **Step 3: Implement authority ownership and capability access**

```python
@dataclass(frozen=True)
class AccessTokenResult:
    token: str | None
    error: str
    grant_invalidated: bool


@contextmanager
def lifecycle(self, character_id: int, capability: str) -> Iterator[LifecycleLease]:
    gate = self._lifecycle_gate(character_id)
    with gate:
        character = self._required_capability(character_id, capability)
        yield LifecycleLease(character, capability, character.generation)
```

Use per-character `threading.RLock`; never hold the authority document lock while launching the browser or waiting for loopback.

- [ ] **Step 4: Write failing lifecycle-generation and participant tests**

Cover late authorization after forget, forget waiting for an active lease, participant refusal before authority removal, authority-save failure leaving participant state untouched, participant cleanup after persisted removal, and lock ordering.

- [ ] **Step 5: Implement exact-character upgrades and global forget**

`enable_capability(character_id, FITTINGS)` captures `(character_id, generation)`, requests `SKILLS_SCOPES | FITTINGS_SCOPES`, waits without a lifecycle lease, then reacquires and commits only if both still match. `forget` calls every participant's `prepare_forget`, persists authority removal, increments generation, then calls `authority_removed`.

- [ ] **Step 6: Run focused authority suites**

Run: `uv run --no-sync python -m pytest tests/test_eveauth_controller.py tests/test_eveauth_lifecycle.py -v`
Expected: PASS.

- [ ] **Step 7: Run full gates and commit**

```bash
git add wingman/eveauth/controller.py wingman/eveauth/__init__.py tests/test_eveauth_controller.py tests/test_eveauth_lifecycle.py
git commit -m "feat: add shared EVE authority controller"
```

---

### Task 5: Adapt Skills and Application Wiring to Shared Authority

**Files:**
- Modify: `wingman/eveskills/controller.py:233-345,934-1699`
- Modify: `wingman/eveskills/state.py:65-89,320-419`
- Modify: `wingman/__main__.py:598-632,705-715,859`
- Modify: `wingman/ui/api.py:379-449,5832-5953`
- Modify: `tests/test_eveskills_controller.py`
- Modify: `tests/test_eveskills_state.py`
- Modify: `tests/test_skills_wiring.py`
- Modify: `tests/test_main.py`
- Modify: `tests/test_api_skills.py`

**Interfaces:**
- Consumes: `AuthorityController` and `lifecycle(..., SKILLS)`.
- Produces: `SkillsController` with Skills-only state and a `CharacterParticipant` implementation.
- Preserves all existing public Skills bridge methods and payload shapes.

- [ ] **Step 1: Write failing integration tests for shared ownership**

```python
def test_skills_controller_contains_no_refresh_token_after_migration(controller):
    assert not hasattr(controller._state.characters[0], "refresh_token_blob")


def test_skills_forget_uses_global_authority(api, authority):
    api.skills_forget_character("42")
    assert authority.forget_calls == [42]
```

Add tests that character names/scopes are joined from authority, Skills refresh requests only the Skills capability, fitting-scope absence does not affect Skills, and late GET results are dropped after global forget.

- [ ] **Step 2: Run focused tests and confirm red**

Run: `uv run --no-sync python -m pytest tests/test_eveskills_controller.py tests/test_skills_wiring.py tests/test_api_skills.py -v`
Expected: FAIL against embedded credential ownership.

- [ ] **Step 3: Remove credential fields and token logic from Skills state/controller**

Keep character ID, levels, queue, group, Skills ETags, fetch time, and Skills error in Skills state. Delegate access-token acquisition, authorization, cancellation, and forget to authority. Join immutable authority snapshots while building route payloads.

- [ ] **Step 4: Wire startup migration and controller composition**

Build order in `__main__.py`:

```python
migration = migrate_legacy_skills(paths.eve_skills_file(), paths.eve_authority_file())
authority = build_authority_controller(migration)
skills = build_skills_controller(api, authority)
authority.register_participant(skills)
```

If migration is failed, construct safe unavailable EVE controllers and surface the actionable migration error; do not create empty authority.

- [ ] **Step 5: Preserve bridge compatibility and shutdown order**

Keep `skills_add_character`, `skills_cancel_auth`, and `skills_forget_character`; route them to authority. Shutdown feature workers before authority so no consumer can request a token after authority teardown.

- [ ] **Step 6: Run Skills regression set**

Run: `uv run --no-sync python -m pytest tests/test_eveskills_controller.py tests/test_eveskills_state.py tests/test_eveskills_sso.py tests/test_eveskills_jwt.py tests/test_skills_wiring.py tests/test_api_skills.py tests/test_main.py -v`
Expected: PASS.

- [ ] **Step 7: Run full gates and commit**

```bash
git add wingman/eveskills wingman/eveauth wingman/__main__.py wingman/ui/api.py tests/test_eveskills_controller.py tests/test_eveskills_state.py tests/test_skills_wiring.py tests/test_api_skills.py tests/test_main.py
git commit -m "refactor: move Skills onto shared EVE authority"
```

---

### Task 6: Add and Measure the Fourth Destination Shell

**Files:**
- Create: `wingman/web/fittings.js`
- Create: `tests/test_fittings_page.py`
- Modify: `wingman/web/index.html:26-33,1800-1925,2067-2074`
- Modify: `wingman/web/app.js:49-78,139-193,240-282`
- Modify: `wingman/web/style.css:455-531`
- Modify: `tests/test_settings_eve_gate.py`
- Modify: `tests/test_page_conventions.py`
- Modify: `docs/smoke-checklist.md`
- Modify: `DESIGN.md`

**Interfaces:**
- Produces: EVE-gated `fittings` route and route-enter call to `fittings_state`.
- Produces: measured title-bar decision before full Fittings UI work.

- [ ] **Step 1: Write failing route and EVE-gate tests**

Assert the Fittings nav button, route map, `WM.EVE_ROUTES`, remembered-destination repair, leave event, script inclusion, and exactly four destinations.

- [ ] **Step 2: Run route tests and confirm red**

Run: `uv run --no-sync python -m pytest tests/test_fittings_page.py tests/test_settings_eve_gate.py tests/test_page_conventions.py -v`
Expected: FAIL because the route does not exist.

- [ ] **Step 3: Add the minimal route shell**

```html
<button class="navbtn" id="nav-fittings" data-route="fittings">Fittings</button>
...
<div class="route" id="route-fittings" aria-labelledby="nav-fittings"></div>
<script src="fittings.js"></script>
```

Register only the route-entry lifecycle and a safe unavailable-state render. Do not build the full workspace yet.

- [ ] **Step 4: Run focused route tests**

Run: `uv run --no-sync python -m pytest tests/test_fittings_page.py tests/test_settings_eve_gate.py tests/test_page_conventions.py tests/test_bridge_contract.py -v`
Expected: PASS.

- [ ] **Step 5: Measure title-bar geometry on Windows before continuing**

At the 840px floor, record CSS-pixel values for titlebar client width, nav left/right edges, window-control edges, drag-region width, `scrollWidth`, and `clientWidth` at 100%, 125%, 150%, and 200% scaling. Acceptance:

```text
scrollWidth == clientWidth
close button right edge <= titlebar client width
drag region width >= 105 CSS px
all four destination labels remain visible
```

If any condition fails, stop this plan and return to design approval for a navigation treatment. Do not reduce the 105px drag floor.

- [ ] **Step 6: Record the measured decision**

Update `DESIGN.md` with measurements and resolve or narrow its existing title-bar uncertainty. Add the repeatable check to `docs/smoke-checklist.md`.

- [ ] **Step 7: Run full gates and commit**

```bash
git add wingman/web/fittings.js wingman/web/index.html wingman/web/app.js wingman/web/style.css tests/test_fittings_page.py tests/test_settings_eve_gate.py tests/test_page_conventions.py DESIGN.md docs/smoke-checklist.md
git commit -m "feat: add measured Fittings destination shell"
```

---

### Task 7: Implement the Fitting Domain Model and Durable Store

**Files:**
- Create: `wingman/evefittings/model.py`
- Create: `wingman/evefittings/store.py`
- Create: `tests/test_evefittings_model.py`
- Create: `tests/test_evefittings_store.py`
- Modify: `wingman/evefittings/__init__.py`

**Interfaces:**
- Produces: `validate_remote_snapshot`, `canonicalize`, `fingerprint`, `canonical_equal`, `deployment_template`, `normalized_name_key`, and supersession validation.
- Produces: immutable `RemoteFitting`, `CanonicalContent`, `LibraryEntry`, `Presence`, `WriteIntent`, `FittingsState`.
- Produces: `load_fittings(path)` and `save_fittings(path, state)`.

- [ ] **Step 1: Write failing canonicalization tests from fixtures**

```python
def test_numbered_slot_order_is_equivalent(fixtures):
    left, right = validate_remote_snapshot(fixtures.equivalent_slots)
    assert canonicalize(left) == canonicalize(right)
    assert fingerprint(canonicalize(left)) == fingerprint(canonicalize(right))
    assert left.items != right.items


def test_digest_match_still_compares_full_content(monkeypatch):
    monkeypatch.setattr(model, "_digest", lambda _: "collision")
    assert not model.canonical_equal(content_for(100), content_for(200))
```

Cover rack normalization, cargo/drone/fighter distinctions, charges/scripts, quantity aggregation, unknown flag rejecting the complete snapshot, `Invalid` producing no deployment template, and NFC+casefold names.

- [ ] **Step 2: Run model tests and confirm red**

Run: `uv run --no-sync python -m pytest tests/test_evefittings_model.py -v`
Expected: FAIL because model types/functions do not exist.

- [ ] **Step 3: Implement strict remote validation and pure identity functions**

```python
def normalized_name_key(name: str) -> str:
    return unicodedata.normalize("NFC", name).casefold()


def fingerprint(content: CanonicalContent, *, version=FINGERPRINT_VERSION) -> str:
    encoded = json.dumps(content.key(), separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(f"{version}:{encoded}".encode("ascii")).hexdigest()
```

A canonicalization-rule change requires an explicit state migration; loading never silently rewrites identity.

- [ ] **Step 4: Write failing store and recovery tests**

Cover stable IDs, source/deployment templates, aliases, collections by ID, acyclic same-hull supersession, presence discovery batch/time, authoritative snapshot overlay separation, bounded reads, backup recovery, corrupt preservation, deterministic alias eviction, and no silent curated-entry eviction.

```python
def test_startup_converts_in_flight_to_unknown(tmp_path):
    save_fittings(path, state_with_intent("in_flight"))
    loaded, _ = load_fittings(path)
    assert loaded.intents[0].status == "unknown"
```

- [ ] **Step 5: Run store tests and confirm red**

Run: `uv run --no-sync python -m pytest tests/test_evefittings_store.py -v`
Expected: FAIL because persistence does not exist.

- [ ] **Step 6: Implement the single-writer state format and bounds**

Use the repository's `atomicio` and existing Skills-state recovery shape. Local recovery may drop one malformed entry with a warning; remote validation remains all-or-nothing. Completed operation history prunes oldest-first beyond 200 records; unresolved intents never prune.

- [ ] **Step 7: Run focused model/store tests**

Run: `uv run --no-sync python -m pytest tests/test_evefittings_contracts.py tests/test_evefittings_model.py tests/test_evefittings_store.py -v`
Expected: PASS.

- [ ] **Step 8: Run full gates and commit**

```bash
git add wingman/evefittings tests/test_evefittings_model.py tests/test_evefittings_store.py
git commit -m "feat: add durable consolidated fitting model"
```

---

### Task 8: Add Read-Only Refresh, Import, and Type-Name Enrichment

**Files:**
- Create: `wingman/evefittings/names.py`
- Create: `wingman/evefittings/controller.py`
- Create: `tests/test_evefittings_names.py`
- Create: `tests/test_evefittings_refresh.py`
- Modify: `wingman/paths.py`
- Modify: `wingman/__main__.py`
- Modify: `tests/test_main.py`

**Interfaces:**
- Consumes: authority lifecycle/access-token APIs, retrying `EsiClient.get`, model/store contracts.
- Produces: `FittingsController.workspace`, `detail`, `refresh`, curation methods, participant hooks, and `shutdown`.
- Produces: bounded rebuildable `TypeNameCache`.

- [ ] **Step 1: Write failing refresh tests**

```python
def test_valid_refresh_imports_and_records_discovery(controller):
    result = controller.refresh([42])
    entry = controller.entry_for_content(expected_content)
    presence = controller.presence(42, entry.id)
    assert result["ok"] is True
    assert presence.first_seen_utc is not None
    assert presence.discovered_batch_id == result["batch_id"]


def test_malformed_refresh_retains_prior_presence(controller):
    controller.seed_authoritative_presence()
    controller.esi.queue(malformed_snapshot())
    controller.refresh([42])
    assert controller.has_seeded_presence()
    assert controller.character_status(42).stale is True
```

Cover sequential/single-flight all-character refresh, `304`, oversized response, unknown flag, `Invalid` entry, deduplication into an older entry with new presence discovery, and failed save preserving prior durable state.

- [ ] **Step 2: Run refresh tests and confirm red**

Run: `uv run --no-sync python -m pytest tests/test_evefittings_refresh.py -v`
Expected: FAIL because the controller does not exist.

- [ ] **Step 3: Implement lifecycle-gated authoritative refresh**

Acquire `authority.lifecycle(character_id, FITTINGS)` before the final authority check and hold it through GET, strict validation, feature-state lock, and atomic save. Never acquire lifecycle while holding the feature lock. Replace only authoritative presence; keep pending/unknown intents as a separate overlay.

- [ ] **Step 4: Write failing non-blocking name-cache tests**

Assert bounded batch lookup, cache save/load, unresolved `Type 12345` fallback, cosmetic failure not rolling back import, and names excluded from canonical identity.

- [ ] **Step 5: Implement `TypeNameCache` and best-effort enrichment**

Use an unauthenticated batch ID-to-name endpoint through the shared secure client. Keep enrichment outside the refresh transaction; emit a semantic update when names arrive.

- [ ] **Step 6: Wire controller construction without startup network calls**

Build the controller in `__main__.py`, register it as an authority participant, and inject it into `Api` through an underscore-prefixed `_fittings` field. Construction and route opening read local state only.

- [ ] **Step 7: Run focused refresh/name/main suites**

Run: `uv run --no-sync python -m pytest tests/test_evefittings_refresh.py tests/test_evefittings_names.py tests/test_main.py tests/test_api.py -v`
Expected: PASS.

- [ ] **Step 8: Run full gates and commit**

```bash
git add wingman/evefittings wingman/paths.py wingman/__main__.py wingman/ui/api.py tests/test_evefittings_refresh.py tests/test_evefittings_names.py tests/test_main.py
git commit -m "feat: import character fittings from ESI"
```

---

### Task 9: Add Paged Bridge APIs and Curation Workspace

**Files:**
- Create: `tests/test_api_fittings.py`
- Create: `tests/test_fittings_wiring.py`
- Modify: `wingman/evefittings/controller.py`
- Modify: `wingman/ui/api.py:379-449,580-612,5832-5953`
- Modify: `wingman/web/app.js:49-78`
- Modify: `wingman/web/index.html`
- Modify: `wingman/web/fittings.js`
- Modify: `wingman/web/style.css`
- Modify: `tests/test_bridge_contract.py`
- Modify: `tests/test_fittings_page.py`
- Modify: `tests/test_page_conventions.py`

**Interfaces:**
- Produces bridge methods named in the approved spec: state/detail/refresh/enable/cancel/forget, collection CRUD, metadata, supersession, delete, preflight/start/cancel copy.
- Produces literal `onFittingsChanged` and `onFittingsProgress` pushes.
- Produces paged workspace queries with `PAGE_SIZE == 100`.

- [ ] **Step 1: Write failing controller-query and API tests**

```python
def test_workspace_returns_one_bounded_page(controller):
    payload = controller.workspace({"collection_id": "all", "page": 2})
    assert len(payload["rows"]) <= 100
    assert "details" not in payload["rows"][0]


def test_api_fittings_state_is_a_thin_delegate(api, fittings):
    assert api.fittings_state({"page": 1}) == fittings.workspace.return_value
    fittings.workspace.assert_called_once_with({"page": 1})
```

Cover search, ship filter, collection, superseded/unfiled derived views, stable sorting, page bounds, detail, curation persistence outcomes, delete refusal while present, and unavailable-controller fallbacks.

- [ ] **Step 2: Run API tests and confirm red**

Run: `uv run --no-sync python -m pytest tests/test_api_fittings.py tests/test_fittings_wiring.py -v`
Expected: FAIL because bridge methods do not exist.

- [ ] **Step 3: Implement controller queries and thin bridge methods**

Add private literal adapters:

```python
def _push_fittings_changed(self, payload) -> None:
    self._push("onFittingsChanged", payload)


def _push_fittings_progress(self, payload) -> None:
    self._push("onFittingsProgress", payload)
```

Do not add a generic dynamic handler-name adapter.

- [ ] **Step 4: Write failing lexical workspace tests**

Assert handler registration, two-pane structure, collection rail, Unfiled/Superseded, generated checkbox wrappers, one accent action, text-property rendering, app-owned dialogs, route leave cleanup, and no full-library push.

- [ ] **Step 5: Build the curation workspace**

Implement collection rail, search, ship filter, paging, expandable one-at-a-time detail, source/character presence, recent-import filter, metadata editing, collections, supersession, and `Characters…` overlay. Keep selection page-owned until curation or preflight crosses the bridge.

- [ ] **Step 6: Run focused web/bridge tests**

Run: `uv run --no-sync python -m pytest tests/test_api_fittings.py tests/test_fittings_wiring.py tests/test_fittings_page.py tests/test_bridge_contract.py tests/test_page_conventions.py tests/test_settings_eve_gate.py -v`
Expected: PASS.

- [ ] **Step 7: Manually open all local `?dev=1` Fittings states**

Verify default, Unfiled, Superseded, search-empty, expanded detail, stale character, unresolved names, `Invalid` non-deployable, collection dialogs, and 100-row paging. Record failures before commit; do not infer rendering from pytest.

- [ ] **Step 8: Run full gates and commit**

```bash
git add wingman/evefittings/controller.py wingman/ui/api.py wingman/web/app.js wingman/web/index.html wingman/web/fittings.js wingman/web/style.css tests/test_api_fittings.py tests/test_fittings_wiring.py tests/test_fittings_page.py tests/test_bridge_contract.py tests/test_page_conventions.py
git commit -m "feat: add fitting library workspace"
```

---

### Task 10: Add Capability Upgrade, Copy Preflight, and Durable Writes

**Files:**
- Create: `tests/test_evefittings_copy.py`
- Modify: `wingman/eveauth/controller.py`
- Modify: `wingman/evefittings/controller.py`
- Modify: `wingman/evefittings/store.py`
- Modify: `wingman/ui/api.py`
- Modify: `wingman/web/fittings.js`
- Modify: `tests/test_eveauth_controller.py`
- Modify: `tests/test_api_fittings.py`
- Modify: `tests/test_fittings_page.py`

**Interfaces:**
- Consumes: explicit Fittings capability upgrade and `EsiClient.post_once`.
- Produces: bounded ephemeral preflight tickets and durable operation/intents.
- Produces: `preflight_copy`, `start_copy`, and `cancel_copy`.

- [ ] **Step 1: Write failing row-specific capability-upgrade tests**

Assert the upgrade requests Skills+Fittings scopes for the selected existing row, rejects another returned character, generation-checks after browser wait, preserves Skills authority on save failure, and never widens generic Skills authorization.

- [ ] **Step 2: Write failing preflight tests**

```python
def test_preflight_classifies_each_pair(controller):
    result = controller.preflight_copy([FIT_A, FIT_B], [ALICE, BOB])
    assert result["counts"] == {
        "ready": 1,
        "present": 1,
        "conflict": 1,
        "unavailable": 1,
    }


def test_preflight_never_exceeds_twenty_writes(controller):
    result = controller.preflight_copy(many_fits(), many_characters())
    assert result["accepted"] is False
    assert result["error"] == "Split this copy into batches of 20 fittings or fewer."
```

Cover NFC+casefold conflict, alternate name validation, non-deployable entry, missing scope, stale snapshot, unresolved intent, known capacity error, and exact-content skip.

- [ ] **Step 3: Run upgrade/preflight tests and confirm red**

Run: `uv run --no-sync python -m pytest tests/test_eveauth_controller.py tests/test_evefittings_copy.py -v`
Expected: FAIL because upgrade and preflight behavior is incomplete.

- [ ] **Step 4: Implement capability upgrade and bounded preflight tickets**

Tickets contain stable fitting/character IDs, chosen names, confirmed maximum write count, creation time, and an unguessable ID. Keep at most 20 live tickets and expire them after 15 minutes. `start_copy` may reduce writes during revalidation but may never introduce a pair not confirmed by the ticket.

- [ ] **Step 5: Write failing intent-before-send and outcome tests**

```python
def test_intent_is_saved_before_post(controller, events):
    controller.start_copy(PREFLIGHT_ID)
    assert events.index("save:in_flight") < events.index("post_once")


def test_failed_intent_save_sends_nothing(controller):
    controller.store.fail_next_save()
    result = controller.start_copy(PREFLIGHT_ID)
    assert controller.esi.post_calls == []
    assert result["status"] == "persistence_failed"
```

Cover valid `201`, malformed `201`, timeout, no response, `408`, `420`, `429`, `4xx`, `5xx`, cancellation, result-save failure, exact one transport call, and operation IDs.

- [ ] **Step 6: Implement sequential lifecycle-gated copy**

For every pair: acquire lifecycle lease, revalidate, lock feature state, persist `in_flight`, release feature lock while retaining lifecycle lease, call `post_once`, lock state, persist outcome, then release lifecycle lease. Never acquire lifecycle while feature lock is held.

Stop the batch on `420`, `429`, or outcome-persistence failure. Continue after deterministic ordinary rejection. Mark timeout/no response/`408`/`5xx`/malformed `201` Unknown.

- [ ] **Step 7: Implement preflight and result overlays**

Show exact writes before confirmation; allow alternate name or skip for each conflict; show Success, Already present, Conflict/Skipped, Failed, Unknown, Unattempted due to throttle, and Cancelled. Unknown has no Retry action.

- [ ] **Step 8: Run focused copy/API/page suites**

Run: `uv run --no-sync python -m pytest tests/test_eveauth_controller.py tests/test_evefittings_copy.py tests/test_api_fittings.py tests/test_fittings_page.py tests/test_eveesi_mutation.py -v`
Expected: PASS.

- [ ] **Step 9: Run full gates and commit**

```bash
git add wingman/eveauth/controller.py wingman/evefittings wingman/ui/api.py wingman/web/fittings.js tests/test_eveauth_controller.py tests/test_evefittings_copy.py tests/test_api_fittings.py tests/test_fittings_page.py
git commit -m "feat: copy fittings with durable write intents"
```

---

### Task 11: Complete Reconciliation and Cross-Feature Lifecycle Safety

**Files:**
- Create: `tests/test_evefittings_lifecycle.py`
- Modify: `wingman/eveauth/controller.py`
- Modify: `wingman/evefittings/controller.py`
- Modify: `wingman/evefittings/store.py`
- Modify: `wingman/eveskills/controller.py`
- Modify: `wingman/__main__.py`
- Modify: `tests/test_eveauth_lifecycle.py`
- Modify: `tests/test_evefittings_refresh.py`
- Modify: `tests/test_evefittings_copy.py`
- Modify: `tests/test_eveskills_controller.py`

**Interfaces:**
- Finalizes: lifecycle lock ordering, unresolved-intent reconciliation, global forget, ownership invalidation, startup pruning, and shutdown.

- [ ] **Step 1: Write failing crash/reconciliation tests**

```python
def test_pre_horizon_refresh_cannot_resolve_unknown(controller, clock):
    controller.seed_unknown(sent_at=clock.now())
    controller.refresh([42])
    assert controller.intent_status(42, FIT_A) == "unknown"


def test_post_horizon_authoritative_absence_resolves_unknown(controller, clock):
    controller.seed_unknown(sent_at=clock.now())
    clock.advance(seconds=301)
    controller.refresh([42], force_unconditional=True)
    assert controller.has_unresolved_intent(42, FIT_A) is False
```

Also require an unconditional post-horizon `200`; a `304` cannot resolve Unknown.

- [ ] **Step 2: Write failing race tests**

Use events/barriers to cover:

- forget during in-flight POST waits, then refuses if outcome is Unknown;
- forget between copy pairs prevents later sends;
- refresh cannot overwrite pending/unknown overlays;
- capability callback after forget fails generation check;
- owner change invalidates both feature snapshots;
- authority-save failure prevents derived cleanup;
- startup reconciliation prunes orphan Skills/presence only after valid authority load;
- shutdown cancellation leaves honest operation counts.

- [ ] **Step 3: Run lifecycle tests and confirm red**

Run: `uv run --no-sync python -m pytest tests/test_eveauth_lifecycle.py tests/test_evefittings_lifecycle.py -v`
Expected: FAIL until all race policies are implemented.

- [ ] **Step 4: Implement reconciliation and participant coordination**

Unresolved intent keys are `(character_id, canonical_content)`. A post-horizon authoritative snapshot resolves to Success/presence when content exists and resolves to safe absence when it does not. Persist resolution before unblocking preflight or forget.

- [ ] **Step 5: Implement shutdown and startup ordering**

Startup: migrate authority, load authority, load feature states, convert `in_flight` to Unknown, reconcile derived rows, then expose routes. Shutdown: cancel fitting copy/refresh, wait bounded worker time, shut down Skills workers, then authority/listener.

- [ ] **Step 6: Run all authority/Skills/Fittings concurrency suites**

Run: `uv run --no-sync python -m pytest tests/test_eveauth_controller.py tests/test_eveauth_lifecycle.py tests/test_evefittings_refresh.py tests/test_evefittings_copy.py tests/test_evefittings_lifecycle.py tests/test_eveskills_controller.py tests/test_main.py -v`
Expected: PASS without hangs; repeat once with `-x` to catch leaked synchronization state.

- [ ] **Step 7: Request an independent correctness review**

Review only authority migration, lock ordering, write intents, reconciliation, and forget races against the spec. Resolve Blocking/HIGH correctness findings before proceeding.

- [ ] **Step 8: Run full gates and commit**

```bash
git add wingman/eveauth wingman/evefittings wingman/eveskills/controller.py wingman/__main__.py tests/test_eveauth_lifecycle.py tests/test_evefittings_lifecycle.py tests/test_evefittings_refresh.py tests/test_evefittings_copy.py tests/test_eveskills_controller.py tests/test_main.py
git commit -m "fix: harden fitting lifecycle reconciliation"
```

---

### Task 12: Finish Packaging, Dev Scenarios, Documentation, and Smoke Coverage

**Files:**
- Modify: `pyproject.toml:75-96`
- Modify: `.github/actions/build-installer/action.yml:100-130,349-380`
- Modify: `wingman/web/dev.js`
- Modify: `scripts/shoot_screens.py`
- Modify: `tests/test_packaging_completeness.py`
- Modify: `tests/test_dev_harness.py`
- Modify: `tests/test_shoot_screens.py`
- Modify: `docs/smoke-checklist.md`
- Modify: `README.md`
- Modify: `PRODUCT.md` if the accepted product wording needs the new secondary destination listed
- Modify: `DESIGN.md` with settled measured route/chrome behavior
- Modify: `docs/assets/wingman-screenshot.png` only after a real Windows capture

**Interfaces:**
- Completes installed/frozen package inclusion, deterministic browser fixtures, screenshot inventory, operator documentation, and release prerequisites.

- [ ] **Step 1: Write failing packaging and dev-harness tests**

Assert `wingman.eveauth` and `wingman.evefittings` in setuptools packages, build import checks for both controllers, explicit `fittings.js` presence, complete fake bridge methods, Fittings scenarios, EVE-gate-off skip behavior, and screenshot-stage counts derived from one inventory.

- [ ] **Step 2: Run packaging/dev tests and confirm red**

Run: `uv run --no-sync python -m pytest tests/test_packaging_completeness.py tests/test_dev_harness.py tests/test_shoot_screens.py -v`
Expected: FAIL until package/build/dev inventories include Fittings.

- [ ] **Step 3: Complete package and frozen-build declarations**

Add:

```toml
"wingman.eveauth",
"wingman.evefittings",
```

Require build-time imports of `AuthorityController` and `FittingsController`; require `fittings.js` beside existing page scripts.

- [ ] **Step 4: Add deterministic dev and screenshot states**

Include library default, Unfiled, Superseded, recent alliance import, expanded fit, characters/access, stale refresh, name conflict, 20-write preflight, progress, partial result, Unknown result, and non-deployable `Invalid` fit. Fabricated data remains only in `dev.js`.

- [ ] **Step 5: Update product and user documentation**

Document:

- Fittings as a secondary fleet-preparation destination;
- alliance ingestion through in-game Personal Fittings;
- local persistent library and state paths;
- fitting read/write scopes and per-character consent;
- explicit additive writes and no automatic deletion/replacement;
- Unknown outcome/reconciliation behavior;
- global Forget character semantics;
- EVE gate behavior; and
- external release prerequisite that the registered EVE application accepts both fitting scopes.

- [ ] **Step 6: Extend the Windows smoke checklist**

Add exact checks for migration from a pre-feature file, Skills-only continuity, row-bound capability upgrade, wrong-character refusal, imports and deduplication, recent/source filtering, collection curation, copy classifications, cache horizon, ambiguous result, cancellation, throttle, forget races, restart after each durable mutation, installed `fittings.js`, and title-bar geometry at all supported scaling.

- [ ] **Step 7: Run all automated gates**

```bash
uv run --no-sync python -m pytest tests/
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
git diff --check
```

Expected: 0 failures and 0 formatting/lint errors.

- [ ] **Step 8: Run the complete Windows manual pass**

Use a registered EVE application configured for both fitting scopes. Complete every new `docs/smoke-checklist.md` item on a real Windows/WebView2 install, including DPI measurements and a real Personal Fittings read/create. Record any unverified destructive or network state explicitly; never substitute `?dev=1` for live authorization/write verification.

- [ ] **Step 9: Inspect final diff and run polish**

Run `polish-core --fix` as required by repository workflow, inspect every edit, rerun all automated gates, check for debug output/placeholders/dead compatibility code, and use `change-explainer` for the reviewer-facing completion summary.

- [ ] **Step 10: Commit the completion slice**

```bash
git add pyproject.toml .github/actions/build-installer/action.yml wingman/web/dev.js scripts/shoot_screens.py tests/test_packaging_completeness.py tests/test_dev_harness.py tests/test_shoot_screens.py docs/smoke-checklist.md README.md PRODUCT.md DESIGN.md docs/assets/wingman-screenshot.png
git commit -m "docs: complete fittings release integration"
```

If the screenshot was not changed because the Windows capture is unavailable, omit it from `git add` and state that remaining manual risk in the completion report.

---

## Final Verification

- [ ] Confirm every spec section maps to at least one task above.
- [ ] Confirm no remote DELETE route or mutation retry exists.
- [ ] Confirm a Skills-only token still refreshes Skills after migration.
- [ ] Confirm migration failure writes neither authority nor completion marker.
- [ ] Confirm no POST occurs without a prior durable `in_flight` intent.
- [ ] Confirm every Unknown outcome blocks retry and global forget until post-cache-horizon authoritative reconciliation.
- [ ] Confirm full pytest, Ruff check, Ruff format check, packaging checks, and `git diff --check` pass.
- [ ] Confirm manual Windows status is reported exactly, including any unrun checks.
