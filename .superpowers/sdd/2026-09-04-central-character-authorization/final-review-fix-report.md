# Final review fix report

Worktree: `/mnt/c/dev/flygd-wingman/.worktrees/central-character-auth`
Branch: `fix/central-character-auth`
Base before this wave: `8a6def3 Polish centralized character authorization`

## Findings fixed

### IMPORTANT 1 — startup/feature warnings survive and render with authority available

- Preserved successful migration/startup warnings on `api._authority_warnings` even when `wire_eve_controllers()` successfully constructs authority and both feature controllers.
- Added construction-warning retention for a missing Fittings controller, matching the existing Skills-controller warning behavior.
- Kept the canonical `eve_characters_state()` payload as the source of shared authority warnings while authority is available.
- Updated Characters notice rendering so bounded authority warnings are shown alongside terminal authorization notices and local mutation feedback instead of being masked by either.
- Added coverage for:
  - successful migration from backup with a warning visible in `eve_characters_state()`;
  - missing Fittings-controller warning visible in the Characters and Fittings payloads;
  - multiple warning lines rendering with a terminal notice and with a local partial-cleanup warning.

### IMPORTANT 2 — active docs and docs guards use the centralized full-auth contract

- Rewrote active README authorization documentation around Settings → Characters as the sole EVE authorization/reconnect/forget surface.
- Replaced the invalid `esi-characters.read_skills.v1` scope with the exact four scopes declared by `wingman/eveauth/application.py`:
  - `esi-fittings.read_fittings.v1`
  - `esi-fittings.write_fittings.v1`
  - `esi-skills.read_skills.v1`
  - `esi-skills.read_skillqueue.v1`
- Updated README and smoke text to describe:
  - `eve_authority.json` as the credential owner;
  - older two-scope Skills grants remaining usable for Skills until reconnect;
  - every new/reconnect sign-in requesting the full four-scope set;
  - unknown returned identities being accepted only after Skills and Fittings cleanup verification;
  - known unequal owner hashes being refused without mutation;
  - `eve_skills.json` retaining Skills data but no refresh credentials.
- Removed active instructions for the retired Add-character and two-scope consent flow, manual credential editing in `eve_skills.json`, and wrong-character targeted rejection.
- Extended packaging/docs tests to derive required scopes from `eveauth.application.FULL_AUTH_SCOPES` and reject stale README/smoke phrases.
- Did not edit historical docs, prior plans, or the approved/superseded specs.

### MINOR 1 — close row menu before authority rerender

- Characters now closes the fixed overflow menu before each authority render replaces roster rows.
- The behavior test asserts the menu closes, disables its menu item, and clears the old trigger's `aria-expanded` when an authority event rerenders a different roster.

### MINOR 2 — row-specific menu accessible label

- The fixed Characters menu now labels itself `Actions for <character name>` while open.
- Closing resets the menu label to the generic `Character actions`.
- Tests cover both labels through the real Characters JavaScript harness.

### MINOR 3 — remove dead `_auth_latch`

- Removed the unused `_auth_latch` field from `AuthorityController`.
- Removed the legacy test that existed only to preserve that field.
- Grep over `wingman/` and `tests/*.py` found no remaining `_auth_latch` references.

## RED evidence

Initial focused RED after adding behavior/docs guards and before the production/doc fixes:

```bash
uv run --no-sync python -m pytest tests/test_skills_wiring.py tests/test_characters_page.py tests/test_packaging_completeness.py -q
```

Result: `7 failed, 60 passed, 1 skipped in 7.77s`.

Expected failures included:

- successful migration warning absent from `api.eve_characters_state()["warnings"]`;
- missing Fittings-controller warning absent from the Characters payload;
- Characters notice rendering only the terminal notice and masking authority warnings;
- menu-specific label and close-on-rerender behavior absent;
- README/smoke still carrying the old auth wording and invalid scope.

After the first implementation pass, focused tests exposed one stale lexical expectation in `tests/test_characters_page.py` because `render()` now closes the menu before normalizing state:

```bash
uv run --no-sync python -m pytest tests/test_skills_wiring.py tests/test_characters_page.py tests/test_packaging_completeness.py -q
```

Result: `1 failed, 66 passed, 1 skipped in 5.69s`.

The test was updated to assert the new behavior contract explicitly.

## GREEN evidence

Focused guard set:

```bash
uv run --no-sync python -m pytest tests/test_skills_wiring.py tests/test_characters_page.py tests/test_packaging_completeness.py -q
```

Result: `67 passed, 1 skipped in 5.12s`.

Focused authority/API/characters/wiring/packaging/smoke-related regression set:

```bash
uv run --no-sync python -m pytest \
  tests/test_eveauth_application.py \
  tests/test_eveauth_controller.py \
  tests/test_eveauth_lifecycle.py \
  tests/test_api_characters.py \
  tests/test_api_skills.py \
  tests/test_api_fittings.py \
  tests/test_bridge_contract.py \
  tests/test_characters_page.py \
  tests/test_settings_page.py \
  tests/test_settings_eve_gate.py \
  tests/test_skills_wiring.py \
  tests/test_fittings_wiring.py \
  tests/test_skills_page.py \
  tests/test_fittings_page.py \
  tests/test_page_conventions.py \
  tests/test_packaging_completeness.py \
  tests/test_dev_harness.py \
  tests/test_shoot_screens.py -v
```

Result: `764 passed, 1 skipped in 20.71s`.

Node syntax:

```bash
for f in wingman/web/*.js; do node --check "$f"; done
```

Result: exit 0, no output.

Static checks:

```bash
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
```

Results:

- `ruff check`: `All checks passed!`
- `ruff format --check`: `259 files already formatted`

Full suite:

```bash
uv run --no-sync python -m pytest tests/
```

Result: `5010 passed, 11 skipped in 66.95s (0:01:06)`.

Screenshot/manual rendering limitation check:

```bash
python scripts/shoot_screens.py
```

Result: unsupported in this Linux harness:

```text
InterpreterError: No Windows interpreter able to import webview and pystray was found.
Tried: nothing -- no candidates at all
Pass one with --python, or set WINGMAN_PY.
```

Manual Windows/WebView2 smoke and screenshot review remain unverified here.

## Self-review

- `git diff --check`: exit 0, no output.
- Inspected the final diff for scope expansion and stale behavior:
  - runtime changes are limited to warning retention, Characters menu/notice behavior, and removal of the unused latch;
  - README and smoke changes are limited to active central-auth guidance;
  - no historical docs, prior plans, or specs were edited;
  - tests cover each review finding and the stale-doc guard derives current full scopes from the code.
- Grep checks:
  - no `_auth_latch` references remain under `wingman/` or `tests/*.py`;
  - README and `docs/smoke-checklist.md` have no matches for the stale auth phrases guarded by packaging tests, including the invalid `esi-characters.read_skills.v1` string.

## Remaining concerns

- Windows/WebView2 manual smoke remains unverified in this Linux worktree.
- Screenshot generation remains unverified because no Windows interpreter with `webview` and `pystray` was available.
- Live CCP SSO, DPAPI, owner-mismatch, and cleanup-verification scenarios still require the manual Windows pass described in `docs/smoke-checklist.md`.
