# Screenshot walk matrix consolidation results

## Scope and authority

- Source baseline: `30422062dd23870a7356608c57f6bb625acaecab`.
- Design: `docs/superpowers/specs/2026-09-22-screenshot-walk-consolidation-design.md`.
- Plan: `docs/superpowers/plans/2026-09-22-screenshot-walk-consolidation.md`.
- Scope: three Python-side `shoot.walk()` orchestration matrices only.
- Explicit exclusions: production tooling, JavaScript fixtures, semantic screenshot matrices, worker isolation, workflows, budgets, sharding, dependencies, and packaging.

## Baseline inventory

| File | Cases |
|---|---:|
| `tests/test_shoot_screens.py` | 246 |
| `tests/test_new_screenshots.py` | 90 |
| `tests/test_current_screenshots.py` | 160 |
| `tests/test_fittings_page.py` | 101 |
| **Total** | **597** |

- All-node normalized SHA-256: `4ff87df92ef58977cd8e5b99b85ca52dddd330f4fc86b037d5f6d209e99de6e7` (597 unique IDs).
- Selected-matrix normalized SHA-256: `16b6a82074fed21183937de1538c8cbffdc8359b01f7a96aada9bfd82bde3069` (71 unique IDs).
- Baseline collection assertions confirmed the exact per-file counts above and rejected duplicate identities.
- Before mutation, the approved retained selectors passed as 12 current-owner cases plus five exact gap/failed-postcondition cases: `17 passed` total.

## Mutation evidence

Every mutation below was applied only to `scripts/shoot_screens.py`, tested against retained representatives, reverted before the next mutation, and followed by `git diff --exit-code -- scripts/shoot_screens.py` with exit code 0. No test was changed for a witness.

### Preparation before section entry

Temporary mutation: swapped the early-owner preparation and `WM.openSettingsSection(...)` evaluations.

Command:

```bash
uv run --no-sync python -m pytest \
  tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans \
  -k 'populated or history' -q
```

Intended failure: every retained non-prepare-failure case rejects `entry` occurring before `prepare` at `assert calls.index(expressions["prepare"]) < calls.index(expressions["entry"])`.

Observed: `10 failed, 2 passed, 48 deselected`. The two `prepare` injected-failure cases passed and were not required witnesses. Failed IDs:

- `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[None-settings-companions-populated]` — ordering assertion reported `2 < 1`.
- `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[None-settings-fleet-sharing-history-narrow]` — ordering assertion reported `3 < 2`.
- `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[entry-settings-companions-populated]` — preparation was absent after injected entry failure (`ValueError: ... is not in list`) at the ordering assertion.
- `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[entry-settings-fleet-sharing-history-narrow]` — preparation was absent after injected entry failure (`ValueError: ... is not in list`) at the ordering assertion.
- `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[stage-settings-companions-populated]` — ordering assertion reported `2 < 1`.
- `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[stage-settings-fleet-sharing-history-narrow]` — ordering assertion reported `3 < 2`.
- `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[verify-settings-companions-populated]` — ordering assertion reported `2 < 1`.
- `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[verify-settings-fleet-sharing-history-narrow]` — ordering assertion reported `3 < 2`.
- `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[capture-settings-companions-populated]` — ordering assertion reported `2 < 1`.
- `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[capture-settings-fleet-sharing-history-narrow]` — ordering assertion reported `3 < 2`.

Restoration proof: the swapped lines were restored and the source-only diff check exited 0.

### Cleanup after failed capture or verification

Temporary mutation: moved cleanup after the screenshot call so cleanup ran only after a successful capture, while viewport restoration remained in `finally`.

Command:

```bash
uv run --no-sync python -m pytest \
  'tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[capture-settings-companions-populated]' \
  'tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[capture-settings-fleet-sharing-history-narrow]' \
  'tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails[fittings-copy-progress]' \
  -q
```

Intended failure: cleanup must still execute when capture or verification raises.

Observed: `3 failed`.

- `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[capture-settings-companions-populated]` failed `assert expressions["cleanup"] in calls`; `WM.companionsScreenshot(null);` was absent.
- `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[capture-settings-fleet-sharing-history-narrow]` failed `assert expressions["cleanup"] in calls`; the paired Fleet cleanup expression was absent.
- `tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails[fittings-copy-progress]` failed `assert expressions[-1] == shoot.new_screen_cleanup_script(screen)`; the final expression was the failed verifier rather than Fittings cleanup.

Restoration proof: the nested cleanup `finally` was restored and the source-only diff check exited 0.

### Verification before capture

Temporary mutation: moved screenshot capture before verifier evaluation.

Command:

```bash
uv run --no-sync python -m pytest \
  'tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails[fittings-copy-progress]' \
  'tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails[settings-previews-groups]' \
  -q
```

Intended failure: a rejected postcondition must not produce a capture.

Observed: `2 failed`.

- `tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails[fittings-copy-progress]` failed `assert captures == []`; observed `[True]`.
- `tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails[settings-previews-groups]` failed `assert captures == []`; observed `[True]`.

Restoration proof: verifier-before-capture order was restored and the source-only diff check exited 0.

### Floor viewport override

Temporary mutation: removed the early-owner `set_device_metrics_override(width=840, height=625)` call.

Command:

```bash
uv run --no-sync python -m pytest \
  'tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[None-settings-fleet-sharing-history-narrow]' \
  -q
```

Intended failure: floor viewport setup must precede preparation.

Observed: `1 failed`. `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[None-settings-fleet-sharing-history-narrow]` failed at `assert calls.index("floor") < calls.index(expressions["prepare"])` with `ValueError: 'floor' is not in list`.

Restoration proof: the override call was restored and the source-only diff check exited 0.

### Floor viewport restoration

Temporary mutation: replaced only `cdp.clear_device_metrics_override()` with `pass`. This is the smallest syntactically valid equivalent of the requested call removal; deleting the call alone would leave an empty `if screen.at_floor:` suite and make the mutant fail to import instead of testing restoration behavior.

Command:

```bash
uv run --no-sync python -m pytest \
  'tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[capture-settings-fleet-sharing-history-narrow]' \
  'tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture[settings-wanderer-controls-narrow]' \
  -q
```

Intended failure: the final operation for floor captures must restore device metrics.

Observed: `2 failed`.

- `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[capture-settings-fleet-sharing-history-narrow]` failed `assert calls[-1] == "clear"`; the last call was paired Fleet cleanup.
- `tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture[settings-wanderer-controls-narrow]` failed `assert operations[-1] == "clear"`; the last operation was `WM.wandererScreenshot(null);`.

Restoration proof: `cdp.clear_device_metrics_override()` was restored and the source-only diff check exited 0.

### Tool fixture attribution

Temporary mutation: changed `if screen.key in _TOOL_SCREEN_FIXTURES:` to `if False and screen.key in _TOOL_SCREEN_FIXTURES:`.

Command:

```bash
uv run --no-sync python -m pytest \
  'tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture[settings-wanderer-controls-narrow]' \
  -q
```

Intended failure: a tool-fixture representative must report `DEV_TOOL_SCREENSHOT_FIXTURE`.

Observed: `1 failed`. `tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture[settings-wanderer-controls-narrow]` failed at `assert shots[0]["fixture"] == "wingman/web/dev.js:" + marker` with `KeyError: 'fixture'`.

Restoration proof: the tool-fixture condition was restored and the source-only diff check exited 0.

### No-fixture attribution

Temporary mutation: changed the Fittings fixture branch to `elif screen.route in {"fittings", "evesettings"}:`.

Command:

```bash
uv run --no-sync python -m pytest \
  'tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture[profiles-copy-scope]' \
  -q
```

Intended failure: the live Profiles representative must not report a synthetic fixture.

Observed: `1 failed`. `tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture[profiles-copy-scope]` failed `assert "fixture" not in shots[0]`; the mutant added `wingman/web/dev.js:DEV_FITTINGS_SCREENSHOT_FIXTURE`.

Restoration proof: the route condition was restored to Fittings only and the source-only diff check exited 0.

### Fittings fixture attribution

Temporary mutation: changed `elif screen.route == "fittings":` to `elif False and screen.route == "fittings":`.

Command:

```bash
uv run --no-sync python -m pytest \
  'tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture[fittings-copy-preflight-bottom-narrow]' \
  -q
```

Intended failure: a Fittings representative must report `DEV_FITTINGS_SCREENSHOT_FIXTURE`.

Observed: `1 failed`. `tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture[fittings-copy-preflight-bottom-narrow]` failed at `assert shots[0]["fixture"] == "wingman/web/dev.js:" + marker` with `KeyError: 'fixture'`.

Restoration proof: the Fittings fixture condition was restored and the source-only diff check exited 0.

### Unmodified post-mutation baseline

Command:

```bash
uv run --no-sync python -m pytest \
  tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans \
  tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture \
  tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails \
  -q
```

Result: `71 passed in 4.57s`. A final `git diff --exit-code -- scripts/shoot_screens.py` exited 0.

## Removed-to-retained mapping

### Current-owner walk

The current-owner walk matrix decreased from 60 to 12 identities. Each removed identity maps to the retained representative for the same failure phase, preserving success or the injected `prepare`, `entry`, `stage`, `verify`, or `capture` phase exactly.

| Removed ID | Retained ID |
|---|---|
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[None-settings-companions-detail-narrow]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[None-settings-companions-populated]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[None-settings-companions-add]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[None-settings-companions-populated]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[None-settings-companions-source-narrow]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[None-settings-companions-populated]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[None-settings-wanderer]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[None-settings-companions-populated]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[None-settings-wanderer-narrow]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[None-settings-companions-populated]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[None-settings-fleet-characters-narrow]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[None-settings-fleet-sharing-history-narrow]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[None-settings-fleet-sharing]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[None-settings-fleet-sharing-history-narrow]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[None-settings-fleet-sharing-details]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[None-settings-fleet-sharing-history-narrow]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[prepare-settings-companions-detail-narrow]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[prepare-settings-companions-populated]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[prepare-settings-companions-add]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[prepare-settings-companions-populated]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[prepare-settings-companions-source-narrow]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[prepare-settings-companions-populated]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[prepare-settings-wanderer]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[prepare-settings-companions-populated]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[prepare-settings-wanderer-narrow]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[prepare-settings-companions-populated]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[prepare-settings-fleet-characters-narrow]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[prepare-settings-fleet-sharing-history-narrow]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[prepare-settings-fleet-sharing]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[prepare-settings-fleet-sharing-history-narrow]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[prepare-settings-fleet-sharing-details]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[prepare-settings-fleet-sharing-history-narrow]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[entry-settings-companions-detail-narrow]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[entry-settings-companions-populated]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[entry-settings-companions-add]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[entry-settings-companions-populated]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[entry-settings-companions-source-narrow]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[entry-settings-companions-populated]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[entry-settings-wanderer]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[entry-settings-companions-populated]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[entry-settings-wanderer-narrow]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[entry-settings-companions-populated]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[entry-settings-fleet-characters-narrow]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[entry-settings-fleet-sharing-history-narrow]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[entry-settings-fleet-sharing]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[entry-settings-fleet-sharing-history-narrow]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[entry-settings-fleet-sharing-details]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[entry-settings-fleet-sharing-history-narrow]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[stage-settings-companions-detail-narrow]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[stage-settings-companions-populated]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[stage-settings-companions-add]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[stage-settings-companions-populated]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[stage-settings-companions-source-narrow]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[stage-settings-companions-populated]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[stage-settings-wanderer]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[stage-settings-companions-populated]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[stage-settings-wanderer-narrow]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[stage-settings-companions-populated]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[stage-settings-fleet-characters-narrow]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[stage-settings-fleet-sharing-history-narrow]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[stage-settings-fleet-sharing]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[stage-settings-fleet-sharing-history-narrow]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[stage-settings-fleet-sharing-details]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[stage-settings-fleet-sharing-history-narrow]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[verify-settings-companions-detail-narrow]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[verify-settings-companions-populated]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[verify-settings-companions-add]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[verify-settings-companions-populated]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[verify-settings-companions-source-narrow]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[verify-settings-companions-populated]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[verify-settings-wanderer]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[verify-settings-companions-populated]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[verify-settings-wanderer-narrow]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[verify-settings-companions-populated]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[verify-settings-fleet-characters-narrow]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[verify-settings-fleet-sharing-history-narrow]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[verify-settings-fleet-sharing]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[verify-settings-fleet-sharing-history-narrow]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[verify-settings-fleet-sharing-details]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[verify-settings-fleet-sharing-history-narrow]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[capture-settings-companions-detail-narrow]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[capture-settings-companions-populated]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[capture-settings-companions-add]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[capture-settings-companions-populated]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[capture-settings-companions-source-narrow]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[capture-settings-companions-populated]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[capture-settings-wanderer]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[capture-settings-companions-populated]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[capture-settings-wanderer-narrow]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[capture-settings-companions-populated]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[capture-settings-fleet-characters-narrow]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[capture-settings-fleet-sharing-history-narrow]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[capture-settings-fleet-sharing]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[capture-settings-fleet-sharing-history-narrow]` |
| `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[capture-settings-fleet-sharing-details]` | `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[capture-settings-fleet-sharing-history-narrow]` |

PENDING — Task 3 will record the remaining six gap and failed-postcondition mappings.

## Local verification

PENDING — Task 4 will record final inventory, order, full-suite, executable, native, lint, format, and changed-path evidence.

## Hosted evidence

PENDING — no hosted or overall-runtime claim.
