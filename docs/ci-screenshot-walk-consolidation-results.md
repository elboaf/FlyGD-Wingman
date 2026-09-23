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

### Gap walk

| Removed ID | Retained ID |
|---|---|
| `tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture[fittings-metadata-narrow]` | `tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture[fittings-copy-preflight-bottom-narrow]` |
| `tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture[fittings-copy-result-bottom-narrow]` | `tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture[fittings-copy-preflight-bottom-narrow]` |

### Failed postcondition walk

| Removed ID | Retained ID |
|---|---|
| `tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails[fittings-detail]` | `tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails[fittings-copy-progress]` |
| `tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails[fittings-copy-result]` | `tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails[fittings-copy-progress]` |
| `tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails[fittings-copy-limit]` | `tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails[fittings-copy-progress]` |
| `tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails[settings-characters-partial-cleanup]` | `tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails[settings-previews-groups]` |

## Local verification

### Exact final inventory

The final four-file collection contains exactly 543 unique node IDs, a reduction
of exactly 54 from the 597-ID baseline. The normalized forward-order hashes are:

- Baseline, 597 IDs: `4ff87df92ef58977cd8e5b99b85ca52dddd330f4fc86b037d5f6d209e99de6e7`.
- Final, 543 IDs: `0142f2bec02e99ca96859c7e58044dd413e7c3026f82e907b8bf267e8c53d04d`.

| File | Baseline | Final | Delta |
|---|---:|---:|---:|
| `tests/test_shoot_screens.py` | 246 | 240 | -6 |
| `tests/test_new_screenshots.py` | 90 | 90 | 0 |
| `tests/test_current_screenshots.py` | 160 | 112 | -48 |
| `tests/test_fittings_page.py` | 101 | 101 | 0 |
| **Total** | **597** | **543** | **-54** |

The exact set audit passed: all 597 baseline and all 543 final IDs were unique,
`baseline - final` contained exactly the 54 IDs represented by the mapping tables
above, `final - baseline` was empty, and every removed ID belonged to one of the
three authorized walk matrices. The mapping audit counted only table rows with
two test node IDs, avoiding the four one-node baseline inventory rows; it found
exactly 54 removed-to-retained rows.

### Mutation restoration

All eight mutation probes recorded above failed at their intended retained
witness assertion. Each temporary `scripts/shoot_screens.py` mutation was restored
before the next probe, the unmodified 71-case pre-consolidation selection passed,
and final protected-path and changed-path checks found no source mutation residue.

### Order isolation

The generated node lists each contained all 543 final identities. The forward
list hash is the final normalized hash above; the reverse-list SHA-256 is
`2a2be39e384f80b1252b048b92eb2550b43f3af30a4e7e20d14ca1796cf391bd`, and
the deterministic seed-`30422062` shuffled-list SHA-256 is
`dbb302db92e18c1d786d52934c1bbad68b80a72530774b0a4e6e2fc99ba5ff4e`.

| Execution order | Result |
|---|---|
| Normal file order | 543 passed in 78.88s |
| Reverse file order | 543 passed in 77.56s |
| Forward collected-node order | 543 passed in 75.49s |
| Reverse collected-node order | 543 passed in 75.30s |
| Deterministic shuffled-node order, seed `30422062` | 543 passed in 75.20s |

The harness permission policy rejected the plan's literal shell command
substitution and a subsequent `xargs` attempt without an available approval UI.
The five runs therefore used Python `subprocess.run(..., check=True)` with the
same pytest executable, options, file arguments, and exact generated node lists;
no ordering plugin or altered selection was used.

### Release codec prerequisite

`cargo build --locked --release --manifest-path
packaging/settings-codec/Cargo.toml --target-dir
packaging/settings-codec/target` completed successfully in 4.83s. The release
binary was copied to this checkout's ignored `packaging/bin`, and
`codec.codec_available()` asserted true. The ignored `packaging/bin/` and
`packaging/settings-codec/target/` outputs did not create tracked changes.

### Focused and full pytest

The focused four-file run passed **543 tests with zero skips, failures, or
errors in 77.38s**. Its JUnit contains 543 cases and has SHA-256
`6f0d8271cef20ada85e2ab482f9498b8e254253e384bdf8207555142e5c07552`.

The complete local suite passed **16,632 tests with 14 skips, zero failures, and
zero errors in 554.01s (9m14s)**. Its JUnit contains 16,646 cases and has
SHA-256 `18aab0c99bf620ba4065081dae5f9abb94907218b98d5c40b0cb34b1294fcc69`.
This is exactly 54 fewer passed tests than the PR #280 comparator's 16,686 passed
and 14 skipped, matching only the authorized node removal. The skip inventory is
identical to the comparator and consists only of these platform integrations:

| Test | Reason |
|---|---|
| `tests.test_clipserve.test_a_live_reader_does_not_block_deletion` | delete-while-open is a Windows sharing rule |
| `tests.test_evesettings_profilecopy.test_prepare_copy_rejects_a_real_windows_server_junction_outside_the_root` | requires a real Windows junction |
| `tests.test_evesettings_profilecopy.test_prepare_copy_rejects_a_real_windows_profile_junction_outside_the_server` | requires a real Windows junction |
| `tests.test_evesettings_profilecopy.test_cleanup_refuses_a_stage_shaped_windows_junction_rather_than_following_it` | requires a real Windows junction |
| `tests.test_eveskills_dpapi.test_round_trips_on_windows` | requires real DPAPI |
| `tests.test_eveskills_dpapi.test_crypt32_binding_is_cached` | requires real WinDLL |
| `tests.test_preview_host.test_stop_from_another_thread_really_exits_the_pump` | needs a real message pump and window station |
| `tests.test_preview_win32.test_every_used_function_is_declared` | binds user32/gdi32/dwmapi |
| `tests.test_preview_win32.test_pointer_sized_returns_are_not_left_at_the_c_int_default` | binds user32/gdi32/dwmapi |
| `tests.test_preview_win32.test_bind_is_cached_so_declarations_are_applied_once` | binds user32/gdi32/dwmapi |
| `tests.test_tray.test_adapter_loads_against_the_pinned_pystray_windows_backend` | pystray Windows backend |
| `tests.test_ui_setup_profile.test_recognized_file_shaped_junction_refuses[core_char_31.dat]` | requires real Windows junction |
| `tests.test_ui_setup_profile.test_recognized_file_shaped_junction_refuses[prefs.ini]` | requires real Windows junction |
| `tests.test_wanderer_integration.test_real_windows_credential_document_roundtrip_replace_binding_and_remove` | real Windows user-bound DPAPI required |

Node v26.5.0 and the built release codec were available. There were no Node,
native-codec, or other availability skips.

### Independent gates

| Gate | Outcome |
|---|---|
| `node scripts/js_smoke.js` | Passed: every module for all three pages loaded |
| `node --test tests/fixtures/screenshot_dom.test.cjs` | 35 passed, 0 failed/skipped |
| `cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml` | 1 passed, 0 failed/ignored |
| `uv run --no-sync ruff check .` | All checks passed |
| `uv run --no-sync ruff format --check .` | 520 files already formatted |
| `git diff --check` | Passed |

### Changed-path and exclusion proof

The exact `30422062..HEAD` changed-path allowlist passed with these five paths:

- `docs/ci-screenshot-walk-consolidation-results.md`;
- `docs/superpowers/plans/2026-09-22-screenshot-walk-consolidation.md`;
- `docs/superpowers/specs/2026-09-22-screenshot-walk-consolidation-design.md`;
- `tests/test_current_screenshots.py`;
- `tests/test_shoot_screens.py`.

The protected-path command over `wingman`, `.github`, `scripts`, `packaging`,
`pyproject.toml`, `uv.lock`, and `tests/fixtures` printed nothing. Production,
JavaScript fixtures, workflows, packaging sources, dependencies, configuration,
screenshot inventories, generated expressions, and persistent-worker protocol
are unchanged. The only executable changes are the authorized pytest parameter
selections in the two test files.

## Hosted evidence

### Run authority and comparability

The hosted comparator remains PR #280 run
[`35767700980`](https://github.com/elboaf/FlyGD-Wingman/actions/runs/35767700980),
whose executable head is `18f85d2d4a53423544c157af70aa29a310de8924`.
Its final Windows and Ubuntu artifacts are retained at
`/tmp/wingman-pr280-final-windows` and `/tmp/wingman-pr280-final-ubuntu`.

PR #285 run
[`35812158175`](https://github.com/elboaf/FlyGD-Wingman/actions/runs/35812158175)
tested branch head `978bb02df6fe1b4b4f607b3c0ce39d2f6c539c40` through synthetic
merge `c9a8e0d` into base `438ac1c6fd6fe1e8ef51b1a0c32bb558128ca4fb`.
The base movement from the PR #280 source baseline, `30422062..438ac1c6`, is
only PR #284. Its changed paths do not include any of the four target tests,
their fixtures, `scripts/shoot_screens.py`, or `.github/workflows/ci.yml`.
The comparator and PR #285 artifacts are therefore comparable for this bounded
target identity and testcase-sum analysis. This hosted-evidence update is
documentation-only and follows the tested executable head.

Run `35812158175` supplied two complete successful attempts:

| Attempt | Checks | Ubuntu job | Ubuntu job / Test | Windows job | Windows job / Test |
|---|---:|---:|---:|---:|---:|
| 1 | `107025872947` — passed | `107025873111` — passed | 6m38s / 6m13s | `107025873164` — passed | 12m26s / 11m30s |
| 2 | `107028566697` — passed | `107028566862` — passed | 5m51s / 5m28s | `107028567019` — passed | 13m01s / 11m58s |

Attempt 1 artifacts are retained at
`/tmp/wingman-pr285-attempt1-{windows,ubuntu}`; attempt 2 artifacts are at
`/tmp/wingman-pr285-attempt2-{windows,ubuntu}`. All six artifact directories
contain both `pytest-result.xml` and `pytest-timing.json`.

### Result, identity, and skip audits

The XML and JSON in all six artifact directories were parsed together. For each
artifact, the JUnit testcase count and testcase-time sum reproduce the JSON
`case_count`, `total_seconds`, per-file counts, and per-file sums. Both PR #285
attempts have **16,646 cases**, zero failures, and zero errors on each platform.
Windows has **67 expected skips** and Ubuntu has **14 expected skips**; the skip
test identities match the comparator and each other on the same platform. The
two Windows reasons that embed a generated pytest temporary directory differ
only in that run-specific path.

The target identity audit also passed exactly:

- the comparator Windows and Ubuntu target sets both equal the published
  597-ID Appendix A inventory;
- both PR #285 attempts on both platforms equal the published 543-ID Appendix B
  inventory;
- Windows and Ubuntu target sets are identical within each attempt;
- relative to the comparator, exactly the 54 mapped IDs are absent and zero IDs
  are added;
- both attempts retain exact per-file counts `240 / 90 / 112 / 101`.

### Per-file hosted testcase sums

JUnit testcase sums are additive diagnostic observations. They are not job
wall-clock or required-critical-path measurements.

| Platform | Evidence | `test_shoot_screens.py` | `test_new_screenshots.py` | `test_current_screenshots.py` | `test_fittings_page.py` | Four-file target |
|---|---|---:|---:|---:|---:|---:|
| Windows | PR #280 comparator | 26.392s / 246 | 15.617s / 90 | 20.755s / 160 | 17.265s / 101 | 80.029s / 597 |
| Windows | PR #285 attempt 1 | 32.298s / 240 | 20.952s / 90 | 23.416s / 112 | 22.198s / 101 | 98.864s / 543 |
| Windows | PR #285 attempt 2 | 31.861s / 240 | 20.674s / 90 | 22.785s / 112 | 22.203s / 101 | 97.523s / 543 |
| Ubuntu | PR #280 comparator | 23.202s / 246 | 15.979s / 90 | 15.826s / 160 | 19.140s / 101 | 74.147s / 597 |
| Ubuntu | PR #285 attempt 1 | 23.435s / 240 | 16.085s / 90 | 15.879s / 112 | 19.402s / 101 | 74.801s / 543 |
| Ubuntu | PR #285 attempt 2 | 17.256s / 240 | 11.970s / 90 | 11.917s / 112 | 10.759s / 101 | 51.902s / 543 |

The two changed test files are the affected scope. The unchanged New Screenshots
and Fittings files are target-local runner controls:

| Platform | Evidence | All-case JUnit sum | Affected two-file sum | Unchanged target controls | Affected / control |
|---|---|---:|---:|---:|---:|
| Windows | PR #280 comparator | 834.507s | 47.147s | 32.882s | 1.434 |
| Windows | PR #285 attempt 1 | 654.602s | 55.714s | 43.150s | 1.291 |
| Windows | PR #285 attempt 2 | 679.696s | 54.646s | 42.877s | 1.274 |
| Ubuntu | PR #280 comparator | 344.815s | 39.028s | 35.119s | 1.111 |
| Ubuntu | PR #285 attempt 1 | 342.432s | 39.314s | 35.487s | 1.108 |
| Ubuntu | PR #285 attempt 2 | 310.710s | 29.173s | 22.729s | 1.284 |

For the 543 IDs common to comparator and PR #285, the comparator sums are
79.591s on Windows and 73.960s on Ubuntu. The 54 removed pure-Python
orchestration cases account for only **0.438s on Windows** and **0.187s on
Ubuntu** in the comparator. The corresponding common-ID sums are 98.864s and
74.801s in attempt 1, and 97.523s and 51.902s in attempt 2.

For wall-clock context only, the PR #280 final Windows job/Test observations were
16m51s / 14m28s and its final Ubuntu observations were 6m46s / 6m18s. PR #285's
two job/Test observations are recorded in the attempt table above. These values
vary independently of the tiny removed-case cost and do not establish an overall
runtime result.

### Interpretation

The raw Windows four-file target sum is slower in both PR #285 attempts:
98.864s and 97.523s versus the comparator's 80.029s. This is not evidence that
the consolidation itself regressed the target. Both unchanged control files
increase similarly in both attempts, while the affected/control ratio improves
from **1.434** in the comparator to **1.291** and **1.274**. The removed cases
represented only 0.438s of comparator Windows testcase time, so no material
absolute reduction was expected from this Stage 1 contract simplification.

Ubuntu reinforces the high-variance interpretation: attempt 1 is near-flat at
74.801s versus 74.147s, while attempt 2 is much faster at 51.902s. Its affected
and control files move together rather than isolating a stable Stage 1 timing
effect. The all-case sums, Test steps, and complete jobs likewise vary enough
that they are observations only.

Accordingly, this evidence makes **no Stage 1 speedup claim and no overall
runtime, job-duration, wall-clock, runner-efficiency, or critical-path
improvement claim**.

### Decision boundary

**GO — a separate Stage 2 current-owner lifecycle consolidation only.** Both
hosted attempts pass all required jobs; identity, skip, failure/error, mapping,
and scope contracts hold; and Windows target-control normalization supplies an
explanation for the raw target increase rather than an unexplained material
regression. Stage 2 must remain a separate change with its own contract and
mutation evidence.

**STOP — workflow selection, budget enforcement, sharding, every overall-runtime
claim, and Stages 3–4.** None is authorized by this evidence; each remains
stopped until separately designed and supported by its own evidence.

## Appendix A — Complete normalized baseline node list (597)

This is the source-baseline collection order normalized to one node ID per line.
Its SHA-256 is `4ff87df92ef58977cd8e5b99b85ca52dddd330f4fc86b037d5f6d209e99de6e7`.

```text
tests/test_shoot_screens.py::test_gate_on_shoots_every_screen
tests/test_shoot_screens.py::test_gate_off_shoots_only_the_reachable_screens
tests/test_shoot_screens.py::test_screen_list_matches_the_page
tests/test_shoot_screens.py::test_gated_column_matches_the_apps_own_gate
tests/test_shoot_screens.py::test_floor_sized_screens_use_the_explicit_inventory_flag
tests/test_shoot_screens.py::test_gap_capture_inventory_keeps_existing_stages
tests/test_shoot_screens.py::test_gap_capture_worker_reuses_process_and_preserves_business_outcomes
tests/test_shoot_screens.py::test_gap_capture_worker_vm_failures_preserve_stack_and_recover
tests/test_shoot_screens.py::test_gap_capture_worker_is_order_independent[settled-missing-settled]
tests/test_shoot_screens.py::test_gap_capture_worker_is_order_independent[covered-settled-hidden]
tests/test_shoot_screens.py::test_gap_capture_worker_cancels_pending_timer[pending-timer-normal-exit]
tests/test_shoot_screens.py::test_gap_capture_worker_cancels_pending_timer[pending-timer-assertion-exit]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[settled-settings-wanderer-controls-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[settled-profiles-copy-scope]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[settled-fittings-metadata-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[settled-fittings-copy-preflight-bottom-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[settled-fittings-copy-result-bottom-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[missing-settings-wanderer-controls-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[missing-profiles-copy-scope]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[missing-fittings-metadata-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[missing-fittings-copy-preflight-bottom-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[missing-fittings-copy-result-bottom-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[hidden-settings-wanderer-controls-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[hidden-profiles-copy-scope]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[hidden-fittings-metadata-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[hidden-fittings-copy-preflight-bottom-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[hidden-fittings-copy-result-bottom-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[wrong-text-settings-wanderer-controls-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[wrong-text-profiles-copy-scope]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[wrong-text-fittings-metadata-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[wrong-text-fittings-copy-preflight-bottom-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[wrong-text-fittings-copy-result-bottom-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[clipped-settings-wanderer-controls-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[clipped-profiles-copy-scope]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[clipped-fittings-metadata-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[clipped-fittings-copy-preflight-bottom-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[clipped-fittings-copy-result-bottom-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[covered-settings-wanderer-controls-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[covered-profiles-copy-scope]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[covered-fittings-metadata-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[covered-fittings-copy-preflight-bottom-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[covered-fittings-copy-result-bottom-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[zero-area-settings-wanderer-controls-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[zero-area-profiles-copy-scope]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[zero-area-fittings-metadata-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[zero-area-fittings-copy-preflight-bottom-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[zero-area-fittings-copy-result-bottom-narrow]
tests/test_shoot_screens.py::test_gap_geometry_allows_only_one_pixel_rounding_and_still_hit_tests[rounding-top]
tests/test_shoot_screens.py::test_gap_geometry_allows_only_one_pixel_rounding_and_still_hit_tests[rounding-bottom]
tests/test_shoot_screens.py::test_gap_geometry_allows_only_one_pixel_rounding_and_still_hit_tests[rounding-left]
tests/test_shoot_screens.py::test_gap_geometry_allows_only_one_pixel_rounding_and_still_hit_tests[rounding-right]
tests/test_shoot_screens.py::test_gap_geometry_allows_only_one_pixel_rounding_and_still_hit_tests[edge-top]
tests/test_shoot_screens.py::test_gap_geometry_allows_only_one_pixel_rounding_and_still_hit_tests[edge-bottom]
tests/test_shoot_screens.py::test_gap_geometry_allows_only_one_pixel_rounding_and_still_hit_tests[edge-left]
tests/test_shoot_screens.py::test_gap_geometry_allows_only_one_pixel_rounding_and_still_hit_tests[edge-right]
tests/test_shoot_screens.py::test_gap_geometry_allows_only_one_pixel_rounding_and_still_hit_tests[overflow-top]
tests/test_shoot_screens.py::test_gap_geometry_allows_only_one_pixel_rounding_and_still_hit_tests[overflow-bottom]
tests/test_shoot_screens.py::test_gap_geometry_allows_only_one_pixel_rounding_and_still_hit_tests[overflow-left]
tests/test_shoot_screens.py::test_gap_geometry_allows_only_one_pixel_rounding_and_still_hit_tests[overflow-right]
tests/test_shoot_screens.py::test_gap_geometry_allows_only_one_pixel_rounding_and_still_hit_tests[covered-rounding]
tests/test_shoot_screens.py::test_metadata_capture_waits_for_real_detail_without_creating_drafts[unresolved]
tests/test_shoot_screens.py::test_metadata_capture_waits_for_real_detail_without_creating_drafts[wrong-name]
tests/test_shoot_screens.py::test_metadata_capture_waits_for_real_detail_without_creating_drafts[wrong-description]
tests/test_shoot_screens.py::test_metadata_capture_waits_for_real_detail_without_creating_drafts[missing-rack]
tests/test_shoot_screens.py::test_metadata_capture_waits_for_real_detail_without_creating_drafts[redundant-alias]
tests/test_shoot_screens.py::test_metadata_capture_waits_for_real_detail_without_creating_drafts[clean-save-enabled]
tests/test_shoot_screens.py::test_metadata_capture_waits_for_real_detail_without_creating_drafts[immediate-inside-metadata]
tests/test_shoot_screens.py::test_profiles_scope_capture_uses_actual_capability_without_overrides[codec-missing]
tests/test_shoot_screens.py::test_profiles_scope_capture_uses_actual_capability_without_overrides[codec-missing-clipped]
tests/test_shoot_screens.py::test_profiles_scope_capture_uses_actual_capability_without_overrides[inconsistent-capability]
tests/test_shoot_screens.py::test_profiles_scope_capture_uses_actual_capability_without_overrides[unresolved]
tests/test_shoot_screens.py::test_lower_copy_capture_rejects_unsettled_or_wrong_outcomes[fittings-copy-preflight-bottom-narrow-wrong-pair]
tests/test_shoot_screens.py::test_lower_copy_capture_rejects_unsettled_or_wrong_outcomes[fittings-copy-preflight-bottom-narrow-unresolved]
tests/test_shoot_screens.py::test_lower_copy_capture_rejects_unsettled_or_wrong_outcomes[fittings-copy-preflight-bottom-narrow-missing-reassurance]
tests/test_shoot_screens.py::test_lower_copy_capture_rejects_unsettled_or_wrong_outcomes[fittings-copy-result-bottom-narrow-wrong-summary]
tests/test_shoot_screens.py::test_lower_copy_capture_rejects_unsettled_or_wrong_outcomes[fittings-copy-result-bottom-narrow-missing-recovery]
tests/test_shoot_screens.py::test_lower_copy_capture_rejects_unsettled_or_wrong_outcomes[fittings-copy-result-bottom-narrow-hidden-recovery]
tests/test_shoot_screens.py::test_lower_copy_capture_rejects_unsettled_or_wrong_outcomes[fittings-copy-result-bottom-narrow-clipped-summary]
tests/test_shoot_screens.py::test_lower_copy_capture_rejects_unsettled_or_wrong_outcomes[fittings-copy-result-bottom-narrow-reversed-recovery]
tests/test_shoot_screens.py::test_lower_copy_capture_rejects_unsettled_or_wrong_outcomes[fittings-copy-result-bottom-narrow-hidden-technical]
tests/test_shoot_screens.py::test_lower_copy_capture_rejects_unsettled_or_wrong_outcomes[fittings-copy-result-bottom-narrow-clipped-technical]
tests/test_shoot_screens.py::test_lower_copy_capture_requires_retained_context_and_footer[hidden-summary-fittings-copy-preflight-bottom-narrow]
tests/test_shoot_screens.py::test_lower_copy_capture_requires_retained_context_and_footer[hidden-summary-fittings-copy-result-bottom-narrow]
tests/test_shoot_screens.py::test_lower_copy_capture_requires_retained_context_and_footer[clipped-summary-fittings-copy-preflight-bottom-narrow]
tests/test_shoot_screens.py::test_lower_copy_capture_requires_retained_context_and_footer[clipped-summary-fittings-copy-result-bottom-narrow]
tests/test_shoot_screens.py::test_lower_copy_capture_requires_retained_context_and_footer[covered-summary-fittings-copy-preflight-bottom-narrow]
tests/test_shoot_screens.py::test_lower_copy_capture_requires_retained_context_and_footer[covered-summary-fittings-copy-result-bottom-narrow]
tests/test_shoot_screens.py::test_lower_copy_capture_requires_retained_context_and_footer[wrong-summary-fittings-copy-preflight-bottom-narrow]
tests/test_shoot_screens.py::test_lower_copy_capture_requires_retained_context_and_footer[wrong-summary-fittings-copy-result-bottom-narrow]
tests/test_shoot_screens.py::test_lower_copy_capture_requires_retained_context_and_footer[summary-in-body-fittings-copy-preflight-bottom-narrow]
tests/test_shoot_screens.py::test_lower_copy_capture_requires_retained_context_and_footer[summary-in-body-fittings-copy-result-bottom-narrow]
tests/test_shoot_screens.py::test_lower_copy_capture_requires_retained_context_and_footer[wrong-title-fittings-copy-preflight-bottom-narrow]
tests/test_shoot_screens.py::test_lower_copy_capture_requires_retained_context_and_footer[wrong-title-fittings-copy-result-bottom-narrow]
tests/test_shoot_screens.py::test_lower_copy_capture_requires_retained_context_and_footer[clipped-title-fittings-copy-preflight-bottom-narrow]
tests/test_shoot_screens.py::test_lower_copy_capture_requires_retained_context_and_footer[clipped-title-fittings-copy-result-bottom-narrow]
tests/test_shoot_screens.py::test_lower_copy_capture_requires_retained_context_and_footer[hidden-footer-fittings-copy-preflight-bottom-narrow]
tests/test_shoot_screens.py::test_lower_copy_capture_requires_retained_context_and_footer[hidden-footer-fittings-copy-result-bottom-narrow]
tests/test_shoot_screens.py::test_lower_copy_capture_requires_retained_context_and_footer[clipped-footer-fittings-copy-preflight-bottom-narrow]
tests/test_shoot_screens.py::test_lower_copy_capture_requires_retained_context_and_footer[clipped-footer-fittings-copy-result-bottom-narrow]
tests/test_shoot_screens.py::test_lower_result_capture_keeps_recovery_before_pairs_not_sticky
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-progress-settled]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-progress-hidden-summary]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-progress-wrong-summary]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-progress-wrong-title]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-result-settled]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-result-hidden-summary]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-result-wrong-summary]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-result-wrong-title]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-limit-settled]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-limit-hidden-summary]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-limit-wrong-summary]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-limit-wrong-title]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-progress-missing-progress]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-progress-hidden-progress]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-progress-wrong-progress-value]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-progress-wrong-progress-max]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-progress-wrong-progress-aria]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-progress-wrong-progress-label]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-result-missing-technical]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-result-open-technical]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-result-wrong-operation-id]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-result-wrong-technical-label]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-result-unfocusable-technical]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-result-live-operation-id]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-limit-hidden-limit-summary]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-limit-wrong-limit-summary]
tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture[settings-wanderer-controls-narrow]
tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture[profiles-copy-scope]
tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture[fittings-metadata-narrow]
tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture[fittings-copy-preflight-bottom-narrow]
tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture[fittings-copy-result-bottom-narrow]
tests/test_shoot_screens.py::test_preview_capture_variants_cover_the_scroller_and_picker
tests/test_shoot_screens.py::test_page_candidates_keeps_the_real_app_page
tests/test_shoot_screens.py::test_page_candidates_rejects_the_dev_harness
tests/test_shoot_screens.py::test_page_candidates_rejects_non_page_targets
tests/test_shoot_screens.py::test_page_candidates_ignores_the_debug_port
tests/test_shoot_screens.py::test_page_candidates_rejects_a_page_that_is_not_index_html
tests/test_shoot_screens.py::test_page_candidates_rejects_any_non_dev_query_string_too
tests/test_shoot_screens.py::test_resolve_interpreter_prefers_explicit_over_env
tests/test_shoot_screens.py::test_resolve_interpreter_falls_back_to_search
tests/test_shoot_screens.py::test_resolve_interpreter_rejects_a_python_without_the_app_deps
tests/test_shoot_screens.py::test_resolve_interpreter_skips_unusable_candidates_and_keeps_looking
tests/test_shoot_screens.py::test_resolve_interpreter_reports_every_place_it_looked
tests/test_shoot_screens.py::test_launch_command_sets_the_env_inside_cmd
tests/test_shoot_screens.py::test_launch_command_does_not_redirect_localappdata
tests/test_shoot_screens.py::test_manifest_records_what_the_gate_skipped
tests/test_shoot_screens.py::test_manifest_counts_a_failed_shot_as_not_shot
tests/test_shoot_screens.py::test_restore_incumbent_keeps_a_spaced_install_path_intact
tests/test_shoot_screens.py::test_restore_incumbent_keeps_source_build_arguments_intact
tests/test_shoot_screens.py::test_staged_dialog_matches_the_production_delete_payload
tests/test_shoot_screens.py::test_dialog_body_matches_the_shape_the_app_actually_raises
tests/test_shoot_screens.py::test_manifest_records_a_set_shot_without_the_engine
tests/test_shoot_screens.py::test_ensure_engine_is_a_noop_when_the_binary_is_already_there
tests/test_shoot_screens.py::test_ensure_engine_reports_false_without_raising_when_it_cannot_fetch
tests/test_shoot_screens.py::test_ensure_engine_reports_false_when_the_fetcher_is_absent
tests/test_shoot_screens.py::test_preview_group_stages_are_present
tests/test_shoot_screens.py::test_preview_group_stage_setup_scripts
tests/test_shoot_screens.py::test_gate_on_shoots_every_screen_including_new_group_stages
tests/test_shoot_screens.py::test_cdp_set_device_metrics_override_sends_correct_params
tests/test_shoot_screens.py::test_cdp_clear_device_metrics_override_sends_correct_method
tests/test_shoot_screens.py::test_cdp_evaluate_raises_target_error_on_exception_details
tests/test_shoot_screens.py::test_cdp_evaluate_returns_value_when_no_exception
tests/test_shoot_screens.py::test_walk_records_setup_failure_as_failed_shot
tests/test_shoot_screens.py::test_walk_applies_and_clears_device_metrics_for_narrow_screen
tests/test_shoot_screens.py::test_walk_clears_device_metrics_even_when_narrow_screenshot_fails
tests/test_shoot_screens.py::test_dev_preview_fixture_extractor_exists_and_is_callable
tests/test_shoot_screens.py::test_dev_preview_fixture_extractor_returns_a_dict_with_hotkeys
tests/test_shoot_screens.py::test_groups_stage_injects_fixture_via_onPreviewHotkeys
tests/test_shoot_screens.py::test_narrow_stage_injects_fixture_via_onPreviewHotkeys
tests/test_shoot_screens.py::test_groups_stage_scrolls_to_preview_group_manager
tests/test_shoot_screens.py::test_narrow_stage_frames_roster_heading_at_scrollport_start
tests/test_shoot_screens.py::test_detail_stage_scrolls_opened_character_detail_into_view
tests/test_shoot_screens.py::test_fixture_backed_preview_staging_does_not_invoke_write_methods
tests/test_shoot_screens.py::test_fixture_extractor_raises_clearly_on_missing_marker
tests/test_shoot_screens.py::test_walk_applies_device_metrics_before_narrow_setup_script
tests/test_shoot_screens.py::test_walk_narrow_setup_runs_inside_device_metrics_override_on_failure
tests/test_shoot_screens.py::test_narrow_stage_closes_details_and_returns_the_roster_heading_to_top
tests/test_shoot_screens.py::test_narrow_stage_targets_roster_heading_deterministically
tests/test_shoot_screens.py::test_fixture_backed_preview_setup_scripts_embed_exact_fixture_payload
tests/test_shoot_screens.py::test_groups_stage_uses_preview_group_manager_selector
tests/test_shoot_screens.py::test_narrow_stage_uses_the_exact_roster_heading_selector
tests/test_shoot_screens.py::test_narrow_stage_does_not_target_a_character_control
tests/test_shoot_screens.py::test_fixture_stages_fail_closed_when_required_controls_are_missing
tests/test_shoot_screens.py::test_copy_stage_fails_closed_unless_the_copy_chooser_opens
tests/test_shoot_screens.py::test_walk_failure_path_records_set_eval_attempt_clear_in_order
tests/test_shoot_screens.py::test_walk_failure_path_records_attempt_before_clear_not_only_clear
tests/test_shoot_screens.py::test_character_capture_inventory_covers_current_authority_states
tests/test_shoot_screens.py::test_character_capture_staging_is_read_only_and_scenario_backed
tests/test_shoot_screens.py::test_fittings_capture_inventory_covers_every_required_visual_state
tests/test_shoot_screens.py::test_every_fittings_variant_has_fail_closed_staging
tests/test_shoot_screens.py::test_fittings_result_data_is_owned_by_the_dev_harness
tests/test_shoot_screens.py::test_fittings_fixture_injection_is_semantic_bounded_and_exact
tests/test_shoot_screens.py::test_fittings_stage_generator_uses_an_explicit_row_action
tests/test_shoot_screens.py::test_walk_injects_fittings_fixture_before_stage_actions
tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails[fittings-detail]
tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails[fittings-copy-progress]
tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails[fittings-copy-result]
tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails[fittings-copy-limit]
tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails[settings-previews-groups]
tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails[settings-characters-partial-cleanup]
tests/test_shoot_screens.py::test_fittings_capture_staging_never_starts_a_remote_write
tests/test_shoot_screens.py::test_every_preview_capture_uses_the_authoritative_read_only_fixture
tests/test_shoot_screens.py::test_groups_stage_closes_inherited_detail_before_framing_management
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[settled-disabled]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[settled-enabled]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[wrong-route]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[wrong-section]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[inactive-route]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[inactive-section]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[missing-section]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[missing-pane]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[hidden-section]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[hidden-pane]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[hidden-card]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[wrong-owner]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[empty-health]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[zero-health]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[outside-viewport]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[missing-master]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[missing-health]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[hidden-master]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[hidden-health]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[invisible-master]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[invisible-health]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[display-none-master]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[display-none-health]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[clipped-master-top]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[clipped-master-bottom]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[clipped-master-left]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[clipped-master-right]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[clipped-health-top]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[clipped-health-bottom]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[clipped-health-left]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[clipped-health-right]
tests/test_shoot_screens.py::test_alerts_base_capture_walk_waits_then_frames_or_records_failure[False]
tests/test_shoot_screens.py::test_alerts_base_capture_walk_waits_then_frames_or_records_failure[True]
tests/test_shoot_screens.py::test_alerts_advanced_stage_is_present_and_gated
tests/test_shoot_screens.py::test_alerts_advanced_stage_opens_and_frames_the_disclosure
tests/test_shoot_screens.py::test_alerts_advanced_stage_does_not_touch_any_bridge_api
tests/test_shoot_screens.py::test_previews_sticky_conflict_stage_is_present_and_gated
tests/test_shoot_screens.py::test_previews_sticky_conflict_stage_targets_aigas_owner_prefixed_conflict
tests/test_shoot_screens.py::test_previews_sticky_conflict_stage_opens_the_lower_detail_before_positioning_aiga
tests/test_shoot_screens.py::test_previews_sticky_conflict_stage_measures_the_real_sticky_column_header
tests/test_shoot_screens.py::test_previews_sticky_conflict_stage_differs_from_the_table_stage
tests/test_shoot_screens.py::test_previews_sticky_conflict_stage_fails_closed_when_the_owner_row_is_missing
tests/test_shoot_screens.py::test_previews_sticky_conflict_stage_is_read_only
tests/test_new_screenshots.py::test_new_screenshot_worker_reuses_process_and_preserves_negative_contracts
tests/test_new_screenshots.py::test_new_capture_inventory
tests/test_new_screenshots.py::test_capture_fidelity_and_writer_free_exit[settings-previews-groups-fidelity]
tests/test_new_screenshots.py::test_capture_fidelity_and_writer_free_exit[settings-characters-waiting-fidelity]
tests/test_new_screenshots.py::test_capture_fidelity_and_writer_free_exit[settings-characters-partial-cleanup-fidelity]
tests/test_new_screenshots.py::test_capture_fidelity_and_writer_free_exit[fittings-copy-limit-fidelity]
tests/test_new_screenshots.py::test_capture_fidelity_and_writer_free_exit[fittings-copy-result-fidelity]
tests/test_new_screenshots.py::test_capture_fidelity_and_writer_free_exit[fittings-copy-progress-cancel]
tests/test_new_screenshots.py::test_capture_fidelity_and_writer_free_exit[fittings-copy-progress-close]
tests/test_new_screenshots.py::test_capture_fidelity_and_writer_free_exit[fittings-copy-progress-leave]
tests/test_new_screenshots.py::test_capture_fidelity_and_writer_free_exit[fittings-copy-progress-teardown]
tests/test_new_screenshots.py::test_capture_fidelity_and_writer_free_exit[fittings-copy-progress-start]
tests/test_new_screenshots.py::test_capture_fidelity_and_writer_free_exit[fittings-copy-progress-late-live]
tests/test_new_screenshots.py::test_limit_capture_uses_entry_identity[duplicate-selected-name]
tests/test_new_screenshots.py::test_limit_capture_uses_entry_identity[unselected-name-collision]
tests/test_new_screenshots.py::test_fittings_capture_preserves_pending_confirmation[progress]
tests/test_new_screenshots.py::test_fittings_capture_preserves_pending_confirmation[results]
tests/test_new_screenshots.py::test_groups_capture_rejects_clipped_or_occluded_controls[descendant-hit]
tests/test_new_screenshots.py::test_groups_capture_rejects_clipped_or_occluded_controls[missing-summary]
tests/test_new_screenshots.py::test_groups_capture_rejects_clipped_or_occluded_controls[hidden-summary]
tests/test_new_screenshots.py::test_groups_capture_rejects_clipped_or_occluded_controls[hidden-panel]
tests/test_new_screenshots.py::test_groups_capture_rejects_clipped_or_occluded_controls[inside-outer-crossing-inner]
tests/test_new_screenshots.py::test_groups_capture_rejects_clipped_or_occluded_controls[zero-area]
tests/test_new_screenshots.py::test_groups_capture_rejects_clipped_or_occluded_controls[pane-top]
tests/test_new_screenshots.py::test_groups_capture_rejects_clipped_or_occluded_controls[pane-bottom]
tests/test_new_screenshots.py::test_groups_capture_rejects_clipped_or_occluded_controls[pane-left]
tests/test_new_screenshots.py::test_groups_capture_rejects_clipped_or_occluded_controls[pane-right]
tests/test_new_screenshots.py::test_groups_capture_rejects_clipped_or_occluded_controls[viewport-top]
tests/test_new_screenshots.py::test_groups_capture_rejects_clipped_or_occluded_controls[viewport-bottom]
tests/test_new_screenshots.py::test_groups_capture_rejects_clipped_or_occluded_controls[viewport-left]
tests/test_new_screenshots.py::test_groups_capture_rejects_clipped_or_occluded_controls[viewport-right]
tests/test_new_screenshots.py::test_groups_capture_rejects_clipped_or_occluded_controls[occluded-center]
tests/test_new_screenshots.py::test_groups_capture_rejects_clipped_or_occluded_controls[occluded-corner]
tests/test_new_screenshots.py::test_groups_capture_rejects_clipped_or_occluded_controls[null-hit]
tests/test_new_screenshots.py::test_new_capture_staging_executes_without_bridge_or_clipboard[profiles-formations]
tests/test_new_screenshots.py::test_new_capture_staging_executes_without_bridge_or_clipboard[profiles-formations-import]
tests/test_new_screenshots.py::test_new_capture_staging_executes_without_bridge_or_clipboard[profiles-setup-import]
tests/test_new_screenshots.py::test_new_capture_staging_executes_without_bridge_or_clipboard[profiles-setup-share]
tests/test_new_screenshots.py::test_new_capture_staging_executes_without_bridge_or_clipboard[settings-previews-crop-narrow]
tests/test_new_screenshots.py::test_fittings_detail_capture_requires_settled_named_detail[settled]
tests/test_new_screenshots.py::test_fittings_detail_capture_requires_settled_named_detail[collapsed]
tests/test_new_screenshots.py::test_fittings_detail_capture_requires_settled_named_detail[wrong-target]
tests/test_new_screenshots.py::test_fittings_detail_capture_requires_settled_named_detail[missing-detail]
tests/test_new_screenshots.py::test_fittings_detail_capture_requires_settled_named_detail[missing-rack]
tests/test_new_screenshots.py::test_fittings_detail_capture_requires_settled_named_detail[missing-alias]
tests/test_new_screenshots.py::test_fittings_detail_capture_requires_settled_named_detail[missing-presence]
tests/test_new_screenshots.py::test_fittings_detail_capture_requires_settled_named_detail[unresolved]
tests/test_new_screenshots.py::test_fittings_detail_capture_requires_settled_named_detail[late-reset]
tests/test_new_screenshots.py::test_fittings_detail_capture_requires_settled_named_detail[late-reinject]
tests/test_new_screenshots.py::test_fittings_detail_capture_requires_settled_named_detail[late-state]
tests/test_new_screenshots.py::test_fittings_detail_capture_requires_settled_named_detail[cleanup]
tests/test_new_screenshots.py::test_fittings_detail_capture_requires_settled_named_detail[late-cleanup]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_live_controls[clear]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_live_controls[group-clear]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_live_controls[capture]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_live_controls[bind]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_live_controls[size]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_live_controls[copy]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_live_controls[exclude]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_live_controls[lock]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_live_controls[never-minimize]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_live_controls[group]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_live_controls[add]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_live_controls[rename]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_live_controls[delete]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_live_controls[crop-select]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_live_controls[crop-remove]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_live_controls[crop-enabled]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_live_controls[reentry]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_dialog_started_live[bind]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_dialog_started_live[size]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_dialog_started_live[copy]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_dialog_started_live[rename]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_dialog_started_live[delete]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_dialog_started_live[crop-remove]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_parser_started_live[bind]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_parser_started_live[size]
tests/test_new_screenshots.py::test_crop_screenshot_cleanup_settles_only_terminal_live_operation[matching]
tests/test_new_screenshots.py::test_crop_screenshot_cleanup_settles_only_terminal_live_operation[newer]
tests/test_new_screenshots.py::test_crop_screenshot_cleanup_settles_only_terminal_live_operation[older]
tests/test_new_screenshots.py::test_new_capture_cleanup_runs_after_any_failure[profiles-setup-import-prepare]
tests/test_new_screenshots.py::test_new_capture_cleanup_runs_after_any_failure[profiles-setup-import-stage]
tests/test_new_screenshots.py::test_new_capture_cleanup_runs_after_any_failure[profiles-setup-import-verify]
tests/test_new_screenshots.py::test_new_capture_cleanup_runs_after_any_failure[profiles-setup-import-capture]
tests/test_new_screenshots.py::test_new_capture_cleanup_runs_after_any_failure[settings-previews-crop-narrow-prepare]
tests/test_new_screenshots.py::test_new_capture_cleanup_runs_after_any_failure[settings-previews-crop-narrow-stage]
tests/test_new_screenshots.py::test_new_capture_cleanup_runs_after_any_failure[settings-previews-crop-narrow-verify]
tests/test_new_screenshots.py::test_new_capture_cleanup_runs_after_any_failure[settings-previews-crop-narrow-capture]
tests/test_new_screenshots.py::test_tool_fixture_extraction_fails_closed[no marker]
tests/test_new_screenshots.py::test_tool_fixture_extraction_fails_closed[var DEV_TOOL_SCREENSHOT_FIXTURE = {broken}]
tests/test_current_screenshots.py::test_current_screenshot_worker_isolates_owner_families
tests/test_current_screenshots.py::test_current_screenshot_worker_vm_failures_preserve_stack_and_recover
tests/test_current_screenshots.py::test_current_screenshot_worker_cancels_pending_timer[pending-timer-normal-exit]
tests/test_current_screenshots.py::test_current_screenshot_worker_cancels_pending_timer[pending-timer-assertion-exit]
tests/test_current_screenshots.py::test_preview_stages_select_visible_subpages_and_their_scroll_owner[settings-previews]
tests/test_current_screenshots.py::test_preview_stages_select_visible_subpages_and_their_scroll_owner[settings-previews-middle]
tests/test_current_screenshots.py::test_preview_stages_select_visible_subpages_and_their_scroll_owner[settings-previews-table]
tests/test_current_screenshots.py::test_preview_stages_select_visible_subpages_and_their_scroll_owner[settings-previews-sticky-conflict]
tests/test_current_screenshots.py::test_preview_stages_select_visible_subpages_and_their_scroll_owner[settings-previews-detail]
tests/test_current_screenshots.py::test_preview_stages_select_visible_subpages_and_their_scroll_owner[settings-previews-copy]
tests/test_current_screenshots.py::test_preview_stages_select_visible_subpages_and_their_scroll_owner[settings-previews-groups]
tests/test_current_screenshots.py::test_preview_stages_select_visible_subpages_and_their_scroll_owner[settings-previews-narrow]
tests/test_current_screenshots.py::test_preview_stages_select_visible_subpages_and_their_scroll_owner[settings-previews-crop-narrow]
tests/test_current_screenshots.py::test_current_inventory_and_floor_coverage
tests/test_current_screenshots.py::test_current_synthetic_owners[normal-settings-companions-populated]
tests/test_current_screenshots.py::test_current_synthetic_owners[normal-settings-companions-detail-narrow]
tests/test_current_screenshots.py::test_current_synthetic_owners[normal-settings-companions-add]
tests/test_current_screenshots.py::test_current_synthetic_owners[normal-settings-companions-source-narrow]
tests/test_current_screenshots.py::test_current_synthetic_owners[normal-settings-wanderer]
tests/test_current_screenshots.py::test_current_synthetic_owners[normal-settings-wanderer-narrow]
tests/test_current_screenshots.py::test_current_synthetic_owners[normal-settings-fleet-characters-narrow]
tests/test_current_screenshots.py::test_current_synthetic_owners[normal-settings-fleet-sharing]
tests/test_current_screenshots.py::test_current_synthetic_owners[normal-settings-fleet-sharing-details]
tests/test_current_screenshots.py::test_current_synthetic_owners[normal-settings-fleet-sharing-history-narrow]
tests/test_current_screenshots.py::test_current_synthetic_owners[late-read-settings-companions-populated]
tests/test_current_screenshots.py::test_current_synthetic_owners[late-read-settings-companions-detail-narrow]
tests/test_current_screenshots.py::test_current_synthetic_owners[late-read-settings-companions-add]
tests/test_current_screenshots.py::test_current_synthetic_owners[late-read-settings-companions-source-narrow]
tests/test_current_screenshots.py::test_current_synthetic_owners[late-read-settings-wanderer]
tests/test_current_screenshots.py::test_current_synthetic_owners[late-read-settings-wanderer-narrow]
tests/test_current_screenshots.py::test_current_synthetic_owners[late-read-settings-fleet-characters-narrow]
tests/test_current_screenshots.py::test_current_synthetic_owners[late-read-settings-fleet-sharing]
tests/test_current_screenshots.py::test_current_synthetic_owners[late-read-settings-fleet-sharing-details]
tests/test_current_screenshots.py::test_current_synthetic_owners[late-read-settings-fleet-sharing-history-narrow]
tests/test_current_screenshots.py::test_current_synthetic_owners[late-synthetic-settings-companions-populated]
tests/test_current_screenshots.py::test_current_synthetic_owners[late-synthetic-settings-companions-detail-narrow]
tests/test_current_screenshots.py::test_current_synthetic_owners[late-synthetic-settings-companions-add]
tests/test_current_screenshots.py::test_current_synthetic_owners[late-synthetic-settings-companions-source-narrow]
tests/test_current_screenshots.py::test_current_synthetic_owners[late-synthetic-settings-wanderer]
tests/test_current_screenshots.py::test_current_synthetic_owners[late-synthetic-settings-wanderer-narrow]
tests/test_current_screenshots.py::test_current_synthetic_owners[late-synthetic-settings-fleet-characters-narrow]
tests/test_current_screenshots.py::test_current_synthetic_owners[late-synthetic-settings-fleet-sharing]
tests/test_current_screenshots.py::test_current_synthetic_owners[late-synthetic-settings-fleet-sharing-details]
tests/test_current_screenshots.py::test_current_synthetic_owners[late-synthetic-settings-fleet-sharing-history-narrow]
tests/test_current_screenshots.py::test_current_synthetic_owners[invalid-settings-companions-populated]
tests/test_current_screenshots.py::test_current_synthetic_owners[invalid-settings-companions-detail-narrow]
tests/test_current_screenshots.py::test_current_synthetic_owners[invalid-settings-companions-add]
tests/test_current_screenshots.py::test_current_synthetic_owners[invalid-settings-companions-source-narrow]
tests/test_current_screenshots.py::test_current_synthetic_owners[invalid-settings-wanderer]
tests/test_current_screenshots.py::test_current_synthetic_owners[invalid-settings-wanderer-narrow]
tests/test_current_screenshots.py::test_current_synthetic_owners[invalid-settings-fleet-characters-narrow]
tests/test_current_screenshots.py::test_current_synthetic_owners[invalid-settings-fleet-sharing]
tests/test_current_screenshots.py::test_current_synthetic_owners[invalid-settings-fleet-sharing-details]
tests/test_current_screenshots.py::test_current_synthetic_owners[invalid-settings-fleet-sharing-history-narrow]
tests/test_current_screenshots.py::test_lower_cards_frame_live_content_without_actions[settings-uploading]
tests/test_current_screenshots.py::test_lower_cards_frame_live_content_without_actions[settings-uploading-recording]
tests/test_current_screenshots.py::test_lower_cards_frame_live_content_without_actions[settings-uploading-integrations]
tests/test_current_screenshots.py::test_lower_cards_frame_live_content_without_actions[settings-uploading-webhook]
tests/test_current_screenshots.py::test_lower_cards_frame_live_content_without_actions[settings-bookmarks-windows]
tests/test_current_screenshots.py::test_lower_cards_frame_live_content_without_actions[settings-bookmarks-sigbar]
tests/test_current_screenshots.py::test_lower_cards_frame_live_content_without_actions[settings-alerts-custom-narrow]
tests/test_current_screenshots.py::test_cleanup_before_any_live_hydration_erases_synthetic_content[settings-companions-populated]
tests/test_current_screenshots.py::test_cleanup_before_any_live_hydration_erases_synthetic_content[settings-wanderer]
tests/test_current_screenshots.py::test_cleanup_before_any_live_hydration_erases_synthetic_content[settings-fleet-sharing]
tests/test_current_screenshots.py::test_companion_capture_does_not_take_over_a_live_dialog
tests/test_current_screenshots.py::test_sharing_screenshot_fixture_uses_current_control_projection
tests/test_current_screenshots.py::test_sharing_screenshot_projection_guard_rejects_drift[missing-key]
tests/test_current_screenshots.py::test_sharing_screenshot_projection_guard_rejects_drift[extra-key]
tests/test_current_screenshots.py::test_sharing_screenshot_projection_guard_rejects_drift[missing-item]
tests/test_current_screenshots.py::test_sharing_screenshot_projection_guard_rejects_drift[extra-item]
tests/test_current_screenshots.py::test_sharing_screenshot_projection_guard_rejects_drift[reordered-items]
tests/test_current_screenshots.py::test_sharing_screenshot_projection_guard_rejects_drift[bool-as-int]
tests/test_current_screenshots.py::test_sharing_screenshot_projection_guard_rejects_drift[int-as-bool]
tests/test_current_screenshots.py::test_sharing_screenshot_projection_guard_rejects_drift[int-as-float]
tests/test_current_screenshots.py::test_sharing_screenshot_projection_guard_rejects_drift[changed-bool]
tests/test_current_screenshots.py::test_sharing_screenshot_projection_guard_rejects_drift[changed-int]
tests/test_current_screenshots.py::test_sharing_screenshot_projection_guard_rejects_drift[stale-string]
tests/test_current_screenshots.py::test_sharing_screenshot_projection_guard_rejects_drift[changed-null]
tests/test_current_screenshots.py::test_sharing_screenshot_lifecycle_preserves_live_authority[cold]
tests/test_current_screenshots.py::test_sharing_screenshot_lifecycle_preserves_live_authority[live-before]
tests/test_current_screenshots.py::test_sharing_screenshot_lifecycle_preserves_live_authority[live-during]
tests/test_current_screenshots.py::test_sharing_screenshot_lifecycle_preserves_live_authority[cold-then-live]
tests/test_current_screenshots.py::test_sharing_screenshot_lifecycle_preserves_live_authority[repeat]
tests/test_current_screenshots.py::test_sharing_screenshot_lifecycle_preserves_live_authority[authority]
tests/test_current_screenshots.py::test_sharing_screenshot_lifecycle_preserves_live_authority[focus]
tests/test_current_screenshots.py::test_sharing_screenshot_lifecycle_preserves_live_authority[worklists]
tests/test_current_screenshots.py::test_sharing_cleanup_preserves_failed_refresh_authority[cached]
tests/test_current_screenshots.py::test_sharing_cleanup_preserves_failed_refresh_authority[same]
tests/test_current_screenshots.py::test_sharing_cleanup_preserves_failed_refresh_authority[newer]
tests/test_current_screenshots.py::test_wanderer_cleanup_obeys_live_binding_health_fence[live]
tests/test_current_screenshots.py::test_wanderer_cleanup_obeys_live_binding_health_fence[buffered]
tests/test_current_screenshots.py::test_fleet_capture_refuses_pending_live_writes[toggle-button]
tests/test_current_screenshots.py::test_fleet_capture_refuses_pending_live_writes[toggle-check]
tests/test_current_screenshots.py::test_fleet_capture_refuses_pending_live_writes[reset]
tests/test_current_screenshots.py::test_fleet_capture_refuses_pending_live_writes[character]
tests/test_current_screenshots.py::test_fleet_capture_refuses_pending_live_writes[overlap]
tests/test_current_screenshots.py::test_sharing_capture_refuses_pending_browser_actions[pair]
tests/test_current_screenshots.py::test_sharing_capture_refuses_pending_browser_actions[grant]
tests/test_current_screenshots.py::test_sharing_capture_refuses_pending_browser_actions[overlap]
tests/test_current_screenshots.py::test_fleet_cleanup_restores_focused_master_without_changing_live_focus_policy
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[None-settings-companions-populated]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[None-settings-companions-detail-narrow]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[None-settings-companions-add]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[None-settings-companions-source-narrow]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[None-settings-wanderer]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[None-settings-wanderer-narrow]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[None-settings-fleet-characters-narrow]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[None-settings-fleet-sharing]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[None-settings-fleet-sharing-details]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[None-settings-fleet-sharing-history-narrow]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[prepare-settings-companions-populated]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[prepare-settings-companions-detail-narrow]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[prepare-settings-companions-add]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[prepare-settings-companions-source-narrow]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[prepare-settings-wanderer]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[prepare-settings-wanderer-narrow]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[prepare-settings-fleet-characters-narrow]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[prepare-settings-fleet-sharing]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[prepare-settings-fleet-sharing-details]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[prepare-settings-fleet-sharing-history-narrow]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[entry-settings-companions-populated]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[entry-settings-companions-detail-narrow]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[entry-settings-companions-add]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[entry-settings-companions-source-narrow]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[entry-settings-wanderer]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[entry-settings-wanderer-narrow]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[entry-settings-fleet-characters-narrow]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[entry-settings-fleet-sharing]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[entry-settings-fleet-sharing-details]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[entry-settings-fleet-sharing-history-narrow]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[stage-settings-companions-populated]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[stage-settings-companions-detail-narrow]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[stage-settings-companions-add]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[stage-settings-companions-source-narrow]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[stage-settings-wanderer]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[stage-settings-wanderer-narrow]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[stage-settings-fleet-characters-narrow]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[stage-settings-fleet-sharing]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[stage-settings-fleet-sharing-details]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[stage-settings-fleet-sharing-history-narrow]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[verify-settings-companions-populated]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[verify-settings-companions-detail-narrow]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[verify-settings-companions-add]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[verify-settings-companions-source-narrow]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[verify-settings-wanderer]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[verify-settings-wanderer-narrow]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[verify-settings-fleet-characters-narrow]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[verify-settings-fleet-sharing]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[verify-settings-fleet-sharing-details]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[verify-settings-fleet-sharing-history-narrow]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[capture-settings-companions-populated]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[capture-settings-companions-detail-narrow]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[capture-settings-companions-add]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[capture-settings-companions-source-narrow]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[capture-settings-wanderer]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[capture-settings-wanderer-narrow]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[capture-settings-fleet-characters-narrow]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[capture-settings-fleet-sharing]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[capture-settings-fleet-sharing-details]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[capture-settings-fleet-sharing-history-narrow]
tests/test_fittings_page.py::test_copy_context_stays_outside_the_only_body_scroller
tests/test_fittings_page.py::test_copy_dialog_bounds_its_existing_scroller_without_overlaying_the_footer
tests/test_fittings_page.py::test_copy_pair_identity_is_the_only_row_local_sticky_owner
tests/test_fittings_page.py::test_copy_dynamic_header_and_progress_respect_hidden[#fittings-copy-summary[hidden]]
tests/test_fittings_page.py::test_copy_dynamic_header_and_progress_respect_hidden[#fittings-copy-limit-summary[hidden]]
tests/test_fittings_page.py::test_copy_dynamic_header_and_progress_respect_hidden[#fittings-copy-progress[hidden]]
tests/test_fittings_page.py::test_copy_progress_is_compact_and_not_decoratively_animated
tests/test_fittings_page.py::test_copy_progress_retains_a_visible_forced_colour_track_and_value
tests/test_fittings_page.py::test_copy_technical_disclosure_keeps_support_id_selectable_and_wrapped
tests/test_fittings_page.py::test_copy_native_skip_focus_uses_the_painted_label_bounds
tests/test_fittings_page.py::test_copy_mirrored_live_status_removes_the_visible_status_spacing
tests/test_fittings_page.py::test_expanded_fitting_keeps_its_identity_above_the_detail
tests/test_fittings_page.py::test_fitting_visual_header_labels_existing_controls_without_table_roles
tests/test_fittings_page.py::test_fitting_header_and_rows_share_deliberate_tracks_and_insets
tests/test_fittings_page.py::test_fitting_selection_helpers_and_primary_share_one_action_area
tests/test_fittings_page.py::test_fitting_details_stack_at_reachable_floor_without_another_scroller
tests/test_fittings_page.py::test_fitting_native_expanders_use_the_shared_focus_token[.fit-row-toggle:focus-visible]
tests/test_fittings_page.py::test_fitting_native_expanders_use_the_shared_focus_token[.fit-metadata-disclosure > summary:focus-visible]
tests/test_fittings_page.py::test_detail_module_wrapping_does_not_restyle_shared_clipboard_review
tests/test_fittings_page.py::test_fitting_checkbox_focus_scrolls_its_visible_label
tests/test_fittings_page.py::test_fitting_forced_colour_outline_is_decided_at_root
tests/test_fittings_page.py::test_clipboard_import_is_inline_labelled_and_keeps_status_mounted
tests/test_fittings_page.py::test_the_nav_button_exists_and_points_at_the_route
tests/test_fittings_page.py::test_route_uses_shared_eve_workspace_class
tests/test_fittings_page.py::test_eve_workspace_css_has_required_properties
tests/test_fittings_page.py::test_eve_workspace_active_sets_display_grid
tests/test_fittings_page.py::test_primary_action_alignment_shared_rule
tests/test_fittings_page.py::test_there_are_exactly_four_destinations
tests/test_fittings_page.py::test_the_route_map_carries_fittings
tests/test_fittings_page.py::test_fittings_is_gated_with_the_other_eve_destinations
tests/test_fittings_page.py::test_fittings_joins_the_remembered_destination_list
tests/test_fittings_page.py::test_the_script_is_included
tests/test_fittings_page.py::test_fittings_registers_the_enter_leave_contract
tests/test_fittings_page.py::test_entry_asks_python_for_state_exactly_once
tests/test_fittings_page.py::test_returning_from_settings_after_an_authority_change_rereads_fittings_state
tests/test_fittings_page.py::test_fittings_state_bridge_call_matches_a_real_api_method
tests/test_fittings_page.py::test_the_pager_can_actually_hide
tests/test_fittings_page.py::test_screenshot_state_handler_is_allowlisted_bounded_and_read_only
tests/test_fittings_page.py::test_screenshot_mode_intercepts_reads_and_is_cleared_on_route_leave
tests/test_fittings_page.py::test_copy_selection_is_pruned_to_the_current_rendered_page
tests/test_fittings_page.py::test_filter_collection_and_page_changes_clear_selection_before_refetch
tests/test_fittings_page.py::test_route_leave_force_closes_copy_and_resets_progress_phase
tests/test_fittings_page.py::test_rejected_discrete_edits_immediately_requery_persisted_state
tests/test_fittings_page.py::test_rejected_fitting_delete_requeries_without_clearing_page_state
tests/test_fittings_page.py::test_refresh_refusal_error_is_rendered_from_semantic_progress
tests/test_fittings_page.py::test_copy_has_preflight_progress_and_results_overlays
tests/test_fittings_page.py::test_rejected_conflict_recheck_preserves_the_usable_preflight
tests/test_fittings_page.py::test_copy_conflicts_offer_alternate_name_or_explicit_skip
tests/test_fittings_page.py::test_copy_results_name_every_terminal_category_and_never_offer_retry
tests/test_fittings_page.py::test_copy_result_terminal_states_use_existing_semantic_tokens
tests/test_fittings_page.py::test_copy_identity_text_can_wrap_in_review_results_and_progress
tests/test_fittings_page.py::test_fittings_empty_state_starts_hidden_until_the_first_payload
tests/test_fittings_page.py::test_fittings_hands_character_management_off_to_settings
tests/test_fittings_page.py::test_fittings_empty_and_copy_target_copy_name_settings_without_auth_controls
tests/test_fittings_page.py::test_copy_selected_remains_the_only_accent_action
tests/test_fittings_page.py::test_fittings_primary_action_includes_workspace_primary_token
tests/test_fittings_page.py::test_render_pager_defaults_page_when_the_payload_has_none
tests/test_fittings_page.py::test_fittings_worker_reuses_process_and_preserves_business_outcomes
tests/test_fittings_page.py::test_fittings_worker_vm_failures_preserve_stack_and_recover
tests/test_fittings_page.py::test_fittings_worker_cancels_pending_timer[pending-timer-normal-exit]
tests/test_fittings_page.py::test_fittings_worker_cancels_pending_timer[pending-timer-assertion-exit]
tests/test_fittings_page.py::test_copy_accessibility_in_node[checkbox-name]
tests/test_fittings_page.py::test_copy_accessibility_in_node[dialog-description]
tests/test_fittings_page.py::test_copy_accessibility_in_node[tab-wrap]
tests/test_fittings_page.py::test_copy_accessibility_in_node[tab-outside]
tests/test_fittings_page.py::test_copy_accessibility_in_node[hidden-controls]
tests/test_fittings_page.py::test_copy_accessibility_in_node[close]
tests/test_fittings_page.py::test_copy_accessibility_in_node[escape]
tests/test_fittings_page.py::test_copy_accessibility_in_node[fallback-detached]
tests/test_fittings_page.py::test_copy_accessibility_in_node[fallback-hidden]
tests/test_fittings_page.py::test_copy_accessibility_in_node[fallback-invisible]
tests/test_fittings_page.py::test_copy_accessibility_in_node[fallback-disabled]
tests/test_fittings_page.py::test_copy_accessibility_in_node[shared-dialog]
tests/test_fittings_page.py::test_copy_accessibility_in_node[progress-focus]
tests/test_fittings_page.py::test_copy_accessibility_in_node[progress-tab]
tests/test_fittings_page.py::test_copy_accessibility_in_node[cancel-focus]
tests/test_fittings_page.py::test_copy_accessibility_in_node[cancel-tab]
tests/test_fittings_page.py::test_copy_accessibility_in_node[progress-shared-dialog]
tests/test_fittings_page.py::test_copy_accessibility_in_node[review-scroller]
tests/test_fittings_page.py::test_copy_accessibility_in_node[results-scroller]
tests/test_fittings_page.py::test_copy_accessibility_in_node[interleaving-complete-dismiss]
tests/test_fittings_page.py::test_copy_accessibility_in_node[interleaving-queued-complete-dismiss]
tests/test_fittings_page.py::test_copy_accessibility_in_node[interleaving-rollback-false-cancel]
tests/test_fittings_page.py::test_copy_accessibility_in_node[interleaving-rollback-null-cancel]
tests/test_fittings_page.py::test_copy_accessibility_in_node[interleaving-rollback-false-uncancelled]
tests/test_fittings_page.py::test_copy_accessibility_in_node[interleaving-rollback-null-uncancelled]
tests/test_fittings_page.py::test_copy_accessibility_in_node[interleaving-root-tab]
tests/test_fittings_page.py::test_copy_accessibility_in_node[interleaving-descendant-tab]
tests/test_fittings_page.py::test_copy_accessibility_in_node[progress]
tests/test_fittings_page.py::test_copy_accessibility_in_node[route-leave]
tests/test_fittings_page.py::test_fittings_state_machine_in_node[state-route-lifecycle]
tests/test_fittings_page.py::test_fittings_state_machine_in_node[state-request-sequence]
tests/test_fittings_page.py::test_fittings_state_machine_in_node[state-selection-scope]
tests/test_fittings_page.py::test_fittings_state_machine_in_node[state-detail-sequence]
tests/test_fittings_page.py::test_fittings_state_machine_in_node[state-rejected-mutation]
tests/test_fittings_page.py::test_fittings_state_machine_in_node[state-screenshot-progress]
tests/test_fittings_page.py::test_fittings_state_machine_in_node[state-stale-preflight]
tests/test_fittings_page.py::test_fittings_state_machine_in_node[state-stale-progress]
tests/test_fittings_page.py::test_fittings_state_machine_in_node[state-ticket-progress]
tests/test_fittings_page.py::test_fittings_state_machine_in_node[state-stale-start-result]
tests/test_fittings_page.py::test_fittings_state_machine_in_node[state-copy-lifecycle]
```

## Appendix B — Complete normalized final node list (543)

This is the final collection order normalized to one node ID per line. Its
SHA-256 is `0142f2bec02e99ca96859c7e58044dd413e7c3026f82e907b8bf267e8c53d04d`.

```text
tests/test_shoot_screens.py::test_gate_on_shoots_every_screen
tests/test_shoot_screens.py::test_gate_off_shoots_only_the_reachable_screens
tests/test_shoot_screens.py::test_screen_list_matches_the_page
tests/test_shoot_screens.py::test_gated_column_matches_the_apps_own_gate
tests/test_shoot_screens.py::test_floor_sized_screens_use_the_explicit_inventory_flag
tests/test_shoot_screens.py::test_gap_capture_inventory_keeps_existing_stages
tests/test_shoot_screens.py::test_gap_capture_worker_reuses_process_and_preserves_business_outcomes
tests/test_shoot_screens.py::test_gap_capture_worker_vm_failures_preserve_stack_and_recover
tests/test_shoot_screens.py::test_gap_capture_worker_is_order_independent[settled-missing-settled]
tests/test_shoot_screens.py::test_gap_capture_worker_is_order_independent[covered-settled-hidden]
tests/test_shoot_screens.py::test_gap_capture_worker_cancels_pending_timer[pending-timer-normal-exit]
tests/test_shoot_screens.py::test_gap_capture_worker_cancels_pending_timer[pending-timer-assertion-exit]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[settled-settings-wanderer-controls-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[settled-profiles-copy-scope]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[settled-fittings-metadata-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[settled-fittings-copy-preflight-bottom-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[settled-fittings-copy-result-bottom-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[missing-settings-wanderer-controls-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[missing-profiles-copy-scope]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[missing-fittings-metadata-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[missing-fittings-copy-preflight-bottom-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[missing-fittings-copy-result-bottom-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[hidden-settings-wanderer-controls-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[hidden-profiles-copy-scope]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[hidden-fittings-metadata-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[hidden-fittings-copy-preflight-bottom-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[hidden-fittings-copy-result-bottom-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[wrong-text-settings-wanderer-controls-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[wrong-text-profiles-copy-scope]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[wrong-text-fittings-metadata-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[wrong-text-fittings-copy-preflight-bottom-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[wrong-text-fittings-copy-result-bottom-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[clipped-settings-wanderer-controls-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[clipped-profiles-copy-scope]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[clipped-fittings-metadata-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[clipped-fittings-copy-preflight-bottom-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[clipped-fittings-copy-result-bottom-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[covered-settings-wanderer-controls-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[covered-profiles-copy-scope]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[covered-fittings-metadata-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[covered-fittings-copy-preflight-bottom-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[covered-fittings-copy-result-bottom-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[zero-area-settings-wanderer-controls-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[zero-area-profiles-copy-scope]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[zero-area-fittings-metadata-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[zero-area-fittings-copy-preflight-bottom-narrow]
tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[zero-area-fittings-copy-result-bottom-narrow]
tests/test_shoot_screens.py::test_gap_geometry_allows_only_one_pixel_rounding_and_still_hit_tests[rounding-top]
tests/test_shoot_screens.py::test_gap_geometry_allows_only_one_pixel_rounding_and_still_hit_tests[rounding-bottom]
tests/test_shoot_screens.py::test_gap_geometry_allows_only_one_pixel_rounding_and_still_hit_tests[rounding-left]
tests/test_shoot_screens.py::test_gap_geometry_allows_only_one_pixel_rounding_and_still_hit_tests[rounding-right]
tests/test_shoot_screens.py::test_gap_geometry_allows_only_one_pixel_rounding_and_still_hit_tests[edge-top]
tests/test_shoot_screens.py::test_gap_geometry_allows_only_one_pixel_rounding_and_still_hit_tests[edge-bottom]
tests/test_shoot_screens.py::test_gap_geometry_allows_only_one_pixel_rounding_and_still_hit_tests[edge-left]
tests/test_shoot_screens.py::test_gap_geometry_allows_only_one_pixel_rounding_and_still_hit_tests[edge-right]
tests/test_shoot_screens.py::test_gap_geometry_allows_only_one_pixel_rounding_and_still_hit_tests[overflow-top]
tests/test_shoot_screens.py::test_gap_geometry_allows_only_one_pixel_rounding_and_still_hit_tests[overflow-bottom]
tests/test_shoot_screens.py::test_gap_geometry_allows_only_one_pixel_rounding_and_still_hit_tests[overflow-left]
tests/test_shoot_screens.py::test_gap_geometry_allows_only_one_pixel_rounding_and_still_hit_tests[overflow-right]
tests/test_shoot_screens.py::test_gap_geometry_allows_only_one_pixel_rounding_and_still_hit_tests[covered-rounding]
tests/test_shoot_screens.py::test_metadata_capture_waits_for_real_detail_without_creating_drafts[unresolved]
tests/test_shoot_screens.py::test_metadata_capture_waits_for_real_detail_without_creating_drafts[wrong-name]
tests/test_shoot_screens.py::test_metadata_capture_waits_for_real_detail_without_creating_drafts[wrong-description]
tests/test_shoot_screens.py::test_metadata_capture_waits_for_real_detail_without_creating_drafts[missing-rack]
tests/test_shoot_screens.py::test_metadata_capture_waits_for_real_detail_without_creating_drafts[redundant-alias]
tests/test_shoot_screens.py::test_metadata_capture_waits_for_real_detail_without_creating_drafts[clean-save-enabled]
tests/test_shoot_screens.py::test_metadata_capture_waits_for_real_detail_without_creating_drafts[immediate-inside-metadata]
tests/test_shoot_screens.py::test_profiles_scope_capture_uses_actual_capability_without_overrides[codec-missing]
tests/test_shoot_screens.py::test_profiles_scope_capture_uses_actual_capability_without_overrides[codec-missing-clipped]
tests/test_shoot_screens.py::test_profiles_scope_capture_uses_actual_capability_without_overrides[inconsistent-capability]
tests/test_shoot_screens.py::test_profiles_scope_capture_uses_actual_capability_without_overrides[unresolved]
tests/test_shoot_screens.py::test_lower_copy_capture_rejects_unsettled_or_wrong_outcomes[fittings-copy-preflight-bottom-narrow-wrong-pair]
tests/test_shoot_screens.py::test_lower_copy_capture_rejects_unsettled_or_wrong_outcomes[fittings-copy-preflight-bottom-narrow-unresolved]
tests/test_shoot_screens.py::test_lower_copy_capture_rejects_unsettled_or_wrong_outcomes[fittings-copy-preflight-bottom-narrow-missing-reassurance]
tests/test_shoot_screens.py::test_lower_copy_capture_rejects_unsettled_or_wrong_outcomes[fittings-copy-result-bottom-narrow-wrong-summary]
tests/test_shoot_screens.py::test_lower_copy_capture_rejects_unsettled_or_wrong_outcomes[fittings-copy-result-bottom-narrow-missing-recovery]
tests/test_shoot_screens.py::test_lower_copy_capture_rejects_unsettled_or_wrong_outcomes[fittings-copy-result-bottom-narrow-hidden-recovery]
tests/test_shoot_screens.py::test_lower_copy_capture_rejects_unsettled_or_wrong_outcomes[fittings-copy-result-bottom-narrow-clipped-summary]
tests/test_shoot_screens.py::test_lower_copy_capture_rejects_unsettled_or_wrong_outcomes[fittings-copy-result-bottom-narrow-reversed-recovery]
tests/test_shoot_screens.py::test_lower_copy_capture_rejects_unsettled_or_wrong_outcomes[fittings-copy-result-bottom-narrow-hidden-technical]
tests/test_shoot_screens.py::test_lower_copy_capture_rejects_unsettled_or_wrong_outcomes[fittings-copy-result-bottom-narrow-clipped-technical]
tests/test_shoot_screens.py::test_lower_copy_capture_requires_retained_context_and_footer[hidden-summary-fittings-copy-preflight-bottom-narrow]
tests/test_shoot_screens.py::test_lower_copy_capture_requires_retained_context_and_footer[hidden-summary-fittings-copy-result-bottom-narrow]
tests/test_shoot_screens.py::test_lower_copy_capture_requires_retained_context_and_footer[clipped-summary-fittings-copy-preflight-bottom-narrow]
tests/test_shoot_screens.py::test_lower_copy_capture_requires_retained_context_and_footer[clipped-summary-fittings-copy-result-bottom-narrow]
tests/test_shoot_screens.py::test_lower_copy_capture_requires_retained_context_and_footer[covered-summary-fittings-copy-preflight-bottom-narrow]
tests/test_shoot_screens.py::test_lower_copy_capture_requires_retained_context_and_footer[covered-summary-fittings-copy-result-bottom-narrow]
tests/test_shoot_screens.py::test_lower_copy_capture_requires_retained_context_and_footer[wrong-summary-fittings-copy-preflight-bottom-narrow]
tests/test_shoot_screens.py::test_lower_copy_capture_requires_retained_context_and_footer[wrong-summary-fittings-copy-result-bottom-narrow]
tests/test_shoot_screens.py::test_lower_copy_capture_requires_retained_context_and_footer[summary-in-body-fittings-copy-preflight-bottom-narrow]
tests/test_shoot_screens.py::test_lower_copy_capture_requires_retained_context_and_footer[summary-in-body-fittings-copy-result-bottom-narrow]
tests/test_shoot_screens.py::test_lower_copy_capture_requires_retained_context_and_footer[wrong-title-fittings-copy-preflight-bottom-narrow]
tests/test_shoot_screens.py::test_lower_copy_capture_requires_retained_context_and_footer[wrong-title-fittings-copy-result-bottom-narrow]
tests/test_shoot_screens.py::test_lower_copy_capture_requires_retained_context_and_footer[clipped-title-fittings-copy-preflight-bottom-narrow]
tests/test_shoot_screens.py::test_lower_copy_capture_requires_retained_context_and_footer[clipped-title-fittings-copy-result-bottom-narrow]
tests/test_shoot_screens.py::test_lower_copy_capture_requires_retained_context_and_footer[hidden-footer-fittings-copy-preflight-bottom-narrow]
tests/test_shoot_screens.py::test_lower_copy_capture_requires_retained_context_and_footer[hidden-footer-fittings-copy-result-bottom-narrow]
tests/test_shoot_screens.py::test_lower_copy_capture_requires_retained_context_and_footer[clipped-footer-fittings-copy-preflight-bottom-narrow]
tests/test_shoot_screens.py::test_lower_copy_capture_requires_retained_context_and_footer[clipped-footer-fittings-copy-result-bottom-narrow]
tests/test_shoot_screens.py::test_lower_result_capture_keeps_recovery_before_pairs_not_sticky
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-progress-settled]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-progress-hidden-summary]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-progress-wrong-summary]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-progress-wrong-title]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-result-settled]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-result-hidden-summary]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-result-wrong-summary]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-result-wrong-title]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-limit-settled]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-limit-hidden-summary]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-limit-wrong-summary]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-limit-wrong-title]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-progress-missing-progress]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-progress-hidden-progress]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-progress-wrong-progress-value]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-progress-wrong-progress-max]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-progress-wrong-progress-aria]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-progress-wrong-progress-label]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-result-missing-technical]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-result-open-technical]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-result-wrong-operation-id]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-result-wrong-technical-label]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-result-unfocusable-technical]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-result-live-operation-id]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-limit-hidden-limit-summary]
tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details[fittings-copy-limit-wrong-limit-summary]
tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture[settings-wanderer-controls-narrow]
tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture[profiles-copy-scope]
tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture[fittings-copy-preflight-bottom-narrow]
tests/test_shoot_screens.py::test_preview_capture_variants_cover_the_scroller_and_picker
tests/test_shoot_screens.py::test_page_candidates_keeps_the_real_app_page
tests/test_shoot_screens.py::test_page_candidates_rejects_the_dev_harness
tests/test_shoot_screens.py::test_page_candidates_rejects_non_page_targets
tests/test_shoot_screens.py::test_page_candidates_ignores_the_debug_port
tests/test_shoot_screens.py::test_page_candidates_rejects_a_page_that_is_not_index_html
tests/test_shoot_screens.py::test_page_candidates_rejects_any_non_dev_query_string_too
tests/test_shoot_screens.py::test_resolve_interpreter_prefers_explicit_over_env
tests/test_shoot_screens.py::test_resolve_interpreter_falls_back_to_search
tests/test_shoot_screens.py::test_resolve_interpreter_rejects_a_python_without_the_app_deps
tests/test_shoot_screens.py::test_resolve_interpreter_skips_unusable_candidates_and_keeps_looking
tests/test_shoot_screens.py::test_resolve_interpreter_reports_every_place_it_looked
tests/test_shoot_screens.py::test_launch_command_sets_the_env_inside_cmd
tests/test_shoot_screens.py::test_launch_command_does_not_redirect_localappdata
tests/test_shoot_screens.py::test_manifest_records_what_the_gate_skipped
tests/test_shoot_screens.py::test_manifest_counts_a_failed_shot_as_not_shot
tests/test_shoot_screens.py::test_restore_incumbent_keeps_a_spaced_install_path_intact
tests/test_shoot_screens.py::test_restore_incumbent_keeps_source_build_arguments_intact
tests/test_shoot_screens.py::test_staged_dialog_matches_the_production_delete_payload
tests/test_shoot_screens.py::test_dialog_body_matches_the_shape_the_app_actually_raises
tests/test_shoot_screens.py::test_manifest_records_a_set_shot_without_the_engine
tests/test_shoot_screens.py::test_ensure_engine_is_a_noop_when_the_binary_is_already_there
tests/test_shoot_screens.py::test_ensure_engine_reports_false_without_raising_when_it_cannot_fetch
tests/test_shoot_screens.py::test_ensure_engine_reports_false_when_the_fetcher_is_absent
tests/test_shoot_screens.py::test_preview_group_stages_are_present
tests/test_shoot_screens.py::test_preview_group_stage_setup_scripts
tests/test_shoot_screens.py::test_gate_on_shoots_every_screen_including_new_group_stages
tests/test_shoot_screens.py::test_cdp_set_device_metrics_override_sends_correct_params
tests/test_shoot_screens.py::test_cdp_clear_device_metrics_override_sends_correct_method
tests/test_shoot_screens.py::test_cdp_evaluate_raises_target_error_on_exception_details
tests/test_shoot_screens.py::test_cdp_evaluate_returns_value_when_no_exception
tests/test_shoot_screens.py::test_walk_records_setup_failure_as_failed_shot
tests/test_shoot_screens.py::test_walk_applies_and_clears_device_metrics_for_narrow_screen
tests/test_shoot_screens.py::test_walk_clears_device_metrics_even_when_narrow_screenshot_fails
tests/test_shoot_screens.py::test_dev_preview_fixture_extractor_exists_and_is_callable
tests/test_shoot_screens.py::test_dev_preview_fixture_extractor_returns_a_dict_with_hotkeys
tests/test_shoot_screens.py::test_groups_stage_injects_fixture_via_onPreviewHotkeys
tests/test_shoot_screens.py::test_narrow_stage_injects_fixture_via_onPreviewHotkeys
tests/test_shoot_screens.py::test_groups_stage_scrolls_to_preview_group_manager
tests/test_shoot_screens.py::test_narrow_stage_frames_roster_heading_at_scrollport_start
tests/test_shoot_screens.py::test_detail_stage_scrolls_opened_character_detail_into_view
tests/test_shoot_screens.py::test_fixture_backed_preview_staging_does_not_invoke_write_methods
tests/test_shoot_screens.py::test_fixture_extractor_raises_clearly_on_missing_marker
tests/test_shoot_screens.py::test_walk_applies_device_metrics_before_narrow_setup_script
tests/test_shoot_screens.py::test_walk_narrow_setup_runs_inside_device_metrics_override_on_failure
tests/test_shoot_screens.py::test_narrow_stage_closes_details_and_returns_the_roster_heading_to_top
tests/test_shoot_screens.py::test_narrow_stage_targets_roster_heading_deterministically
tests/test_shoot_screens.py::test_fixture_backed_preview_setup_scripts_embed_exact_fixture_payload
tests/test_shoot_screens.py::test_groups_stage_uses_preview_group_manager_selector
tests/test_shoot_screens.py::test_narrow_stage_uses_the_exact_roster_heading_selector
tests/test_shoot_screens.py::test_narrow_stage_does_not_target_a_character_control
tests/test_shoot_screens.py::test_fixture_stages_fail_closed_when_required_controls_are_missing
tests/test_shoot_screens.py::test_copy_stage_fails_closed_unless_the_copy_chooser_opens
tests/test_shoot_screens.py::test_walk_failure_path_records_set_eval_attempt_clear_in_order
tests/test_shoot_screens.py::test_walk_failure_path_records_attempt_before_clear_not_only_clear
tests/test_shoot_screens.py::test_character_capture_inventory_covers_current_authority_states
tests/test_shoot_screens.py::test_character_capture_staging_is_read_only_and_scenario_backed
tests/test_shoot_screens.py::test_fittings_capture_inventory_covers_every_required_visual_state
tests/test_shoot_screens.py::test_every_fittings_variant_has_fail_closed_staging
tests/test_shoot_screens.py::test_fittings_result_data_is_owned_by_the_dev_harness
tests/test_shoot_screens.py::test_fittings_fixture_injection_is_semantic_bounded_and_exact
tests/test_shoot_screens.py::test_fittings_stage_generator_uses_an_explicit_row_action
tests/test_shoot_screens.py::test_walk_injects_fittings_fixture_before_stage_actions
tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails[fittings-copy-progress]
tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails[settings-previews-groups]
tests/test_shoot_screens.py::test_fittings_capture_staging_never_starts_a_remote_write
tests/test_shoot_screens.py::test_every_preview_capture_uses_the_authoritative_read_only_fixture
tests/test_shoot_screens.py::test_groups_stage_closes_inherited_detail_before_framing_management
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[settled-disabled]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[settled-enabled]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[wrong-route]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[wrong-section]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[inactive-route]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[inactive-section]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[missing-section]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[missing-pane]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[hidden-section]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[hidden-pane]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[hidden-card]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[wrong-owner]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[empty-health]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[zero-health]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[outside-viewport]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[missing-master]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[missing-health]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[hidden-master]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[hidden-health]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[invisible-master]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[invisible-health]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[display-none-master]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[display-none-health]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[clipped-master-top]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[clipped-master-bottom]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[clipped-master-left]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[clipped-master-right]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[clipped-health-top]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[clipped-health-bottom]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[clipped-health-left]
tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions[clipped-health-right]
tests/test_shoot_screens.py::test_alerts_base_capture_walk_waits_then_frames_or_records_failure[False]
tests/test_shoot_screens.py::test_alerts_base_capture_walk_waits_then_frames_or_records_failure[True]
tests/test_shoot_screens.py::test_alerts_advanced_stage_is_present_and_gated
tests/test_shoot_screens.py::test_alerts_advanced_stage_opens_and_frames_the_disclosure
tests/test_shoot_screens.py::test_alerts_advanced_stage_does_not_touch_any_bridge_api
tests/test_shoot_screens.py::test_previews_sticky_conflict_stage_is_present_and_gated
tests/test_shoot_screens.py::test_previews_sticky_conflict_stage_targets_aigas_owner_prefixed_conflict
tests/test_shoot_screens.py::test_previews_sticky_conflict_stage_opens_the_lower_detail_before_positioning_aiga
tests/test_shoot_screens.py::test_previews_sticky_conflict_stage_measures_the_real_sticky_column_header
tests/test_shoot_screens.py::test_previews_sticky_conflict_stage_differs_from_the_table_stage
tests/test_shoot_screens.py::test_previews_sticky_conflict_stage_fails_closed_when_the_owner_row_is_missing
tests/test_shoot_screens.py::test_previews_sticky_conflict_stage_is_read_only
tests/test_new_screenshots.py::test_new_screenshot_worker_reuses_process_and_preserves_negative_contracts
tests/test_new_screenshots.py::test_new_capture_inventory
tests/test_new_screenshots.py::test_capture_fidelity_and_writer_free_exit[settings-previews-groups-fidelity]
tests/test_new_screenshots.py::test_capture_fidelity_and_writer_free_exit[settings-characters-waiting-fidelity]
tests/test_new_screenshots.py::test_capture_fidelity_and_writer_free_exit[settings-characters-partial-cleanup-fidelity]
tests/test_new_screenshots.py::test_capture_fidelity_and_writer_free_exit[fittings-copy-limit-fidelity]
tests/test_new_screenshots.py::test_capture_fidelity_and_writer_free_exit[fittings-copy-result-fidelity]
tests/test_new_screenshots.py::test_capture_fidelity_and_writer_free_exit[fittings-copy-progress-cancel]
tests/test_new_screenshots.py::test_capture_fidelity_and_writer_free_exit[fittings-copy-progress-close]
tests/test_new_screenshots.py::test_capture_fidelity_and_writer_free_exit[fittings-copy-progress-leave]
tests/test_new_screenshots.py::test_capture_fidelity_and_writer_free_exit[fittings-copy-progress-teardown]
tests/test_new_screenshots.py::test_capture_fidelity_and_writer_free_exit[fittings-copy-progress-start]
tests/test_new_screenshots.py::test_capture_fidelity_and_writer_free_exit[fittings-copy-progress-late-live]
tests/test_new_screenshots.py::test_limit_capture_uses_entry_identity[duplicate-selected-name]
tests/test_new_screenshots.py::test_limit_capture_uses_entry_identity[unselected-name-collision]
tests/test_new_screenshots.py::test_fittings_capture_preserves_pending_confirmation[progress]
tests/test_new_screenshots.py::test_fittings_capture_preserves_pending_confirmation[results]
tests/test_new_screenshots.py::test_groups_capture_rejects_clipped_or_occluded_controls[descendant-hit]
tests/test_new_screenshots.py::test_groups_capture_rejects_clipped_or_occluded_controls[missing-summary]
tests/test_new_screenshots.py::test_groups_capture_rejects_clipped_or_occluded_controls[hidden-summary]
tests/test_new_screenshots.py::test_groups_capture_rejects_clipped_or_occluded_controls[hidden-panel]
tests/test_new_screenshots.py::test_groups_capture_rejects_clipped_or_occluded_controls[inside-outer-crossing-inner]
tests/test_new_screenshots.py::test_groups_capture_rejects_clipped_or_occluded_controls[zero-area]
tests/test_new_screenshots.py::test_groups_capture_rejects_clipped_or_occluded_controls[pane-top]
tests/test_new_screenshots.py::test_groups_capture_rejects_clipped_or_occluded_controls[pane-bottom]
tests/test_new_screenshots.py::test_groups_capture_rejects_clipped_or_occluded_controls[pane-left]
tests/test_new_screenshots.py::test_groups_capture_rejects_clipped_or_occluded_controls[pane-right]
tests/test_new_screenshots.py::test_groups_capture_rejects_clipped_or_occluded_controls[viewport-top]
tests/test_new_screenshots.py::test_groups_capture_rejects_clipped_or_occluded_controls[viewport-bottom]
tests/test_new_screenshots.py::test_groups_capture_rejects_clipped_or_occluded_controls[viewport-left]
tests/test_new_screenshots.py::test_groups_capture_rejects_clipped_or_occluded_controls[viewport-right]
tests/test_new_screenshots.py::test_groups_capture_rejects_clipped_or_occluded_controls[occluded-center]
tests/test_new_screenshots.py::test_groups_capture_rejects_clipped_or_occluded_controls[occluded-corner]
tests/test_new_screenshots.py::test_groups_capture_rejects_clipped_or_occluded_controls[null-hit]
tests/test_new_screenshots.py::test_new_capture_staging_executes_without_bridge_or_clipboard[profiles-formations]
tests/test_new_screenshots.py::test_new_capture_staging_executes_without_bridge_or_clipboard[profiles-formations-import]
tests/test_new_screenshots.py::test_new_capture_staging_executes_without_bridge_or_clipboard[profiles-setup-import]
tests/test_new_screenshots.py::test_new_capture_staging_executes_without_bridge_or_clipboard[profiles-setup-share]
tests/test_new_screenshots.py::test_new_capture_staging_executes_without_bridge_or_clipboard[settings-previews-crop-narrow]
tests/test_new_screenshots.py::test_fittings_detail_capture_requires_settled_named_detail[settled]
tests/test_new_screenshots.py::test_fittings_detail_capture_requires_settled_named_detail[collapsed]
tests/test_new_screenshots.py::test_fittings_detail_capture_requires_settled_named_detail[wrong-target]
tests/test_new_screenshots.py::test_fittings_detail_capture_requires_settled_named_detail[missing-detail]
tests/test_new_screenshots.py::test_fittings_detail_capture_requires_settled_named_detail[missing-rack]
tests/test_new_screenshots.py::test_fittings_detail_capture_requires_settled_named_detail[missing-alias]
tests/test_new_screenshots.py::test_fittings_detail_capture_requires_settled_named_detail[missing-presence]
tests/test_new_screenshots.py::test_fittings_detail_capture_requires_settled_named_detail[unresolved]
tests/test_new_screenshots.py::test_fittings_detail_capture_requires_settled_named_detail[late-reset]
tests/test_new_screenshots.py::test_fittings_detail_capture_requires_settled_named_detail[late-reinject]
tests/test_new_screenshots.py::test_fittings_detail_capture_requires_settled_named_detail[late-state]
tests/test_new_screenshots.py::test_fittings_detail_capture_requires_settled_named_detail[cleanup]
tests/test_new_screenshots.py::test_fittings_detail_capture_requires_settled_named_detail[late-cleanup]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_live_controls[clear]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_live_controls[group-clear]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_live_controls[capture]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_live_controls[bind]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_live_controls[size]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_live_controls[copy]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_live_controls[exclude]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_live_controls[lock]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_live_controls[never-minimize]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_live_controls[group]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_live_controls[add]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_live_controls[rename]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_live_controls[delete]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_live_controls[crop-select]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_live_controls[crop-remove]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_live_controls[crop-enabled]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_live_controls[reentry]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_dialog_started_live[bind]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_dialog_started_live[size]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_dialog_started_live[copy]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_dialog_started_live[rename]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_dialog_started_live[delete]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_dialog_started_live[crop-remove]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_parser_started_live[bind]
tests/test_new_screenshots.py::test_crop_screenshot_blocks_parser_started_live[size]
tests/test_new_screenshots.py::test_crop_screenshot_cleanup_settles_only_terminal_live_operation[matching]
tests/test_new_screenshots.py::test_crop_screenshot_cleanup_settles_only_terminal_live_operation[newer]
tests/test_new_screenshots.py::test_crop_screenshot_cleanup_settles_only_terminal_live_operation[older]
tests/test_new_screenshots.py::test_new_capture_cleanup_runs_after_any_failure[profiles-setup-import-prepare]
tests/test_new_screenshots.py::test_new_capture_cleanup_runs_after_any_failure[profiles-setup-import-stage]
tests/test_new_screenshots.py::test_new_capture_cleanup_runs_after_any_failure[profiles-setup-import-verify]
tests/test_new_screenshots.py::test_new_capture_cleanup_runs_after_any_failure[profiles-setup-import-capture]
tests/test_new_screenshots.py::test_new_capture_cleanup_runs_after_any_failure[settings-previews-crop-narrow-prepare]
tests/test_new_screenshots.py::test_new_capture_cleanup_runs_after_any_failure[settings-previews-crop-narrow-stage]
tests/test_new_screenshots.py::test_new_capture_cleanup_runs_after_any_failure[settings-previews-crop-narrow-verify]
tests/test_new_screenshots.py::test_new_capture_cleanup_runs_after_any_failure[settings-previews-crop-narrow-capture]
tests/test_new_screenshots.py::test_tool_fixture_extraction_fails_closed[no marker]
tests/test_new_screenshots.py::test_tool_fixture_extraction_fails_closed[var DEV_TOOL_SCREENSHOT_FIXTURE = {broken}]
tests/test_current_screenshots.py::test_current_screenshot_worker_isolates_owner_families
tests/test_current_screenshots.py::test_current_screenshot_worker_vm_failures_preserve_stack_and_recover
tests/test_current_screenshots.py::test_current_screenshot_worker_cancels_pending_timer[pending-timer-normal-exit]
tests/test_current_screenshots.py::test_current_screenshot_worker_cancels_pending_timer[pending-timer-assertion-exit]
tests/test_current_screenshots.py::test_preview_stages_select_visible_subpages_and_their_scroll_owner[settings-previews]
tests/test_current_screenshots.py::test_preview_stages_select_visible_subpages_and_their_scroll_owner[settings-previews-middle]
tests/test_current_screenshots.py::test_preview_stages_select_visible_subpages_and_their_scroll_owner[settings-previews-table]
tests/test_current_screenshots.py::test_preview_stages_select_visible_subpages_and_their_scroll_owner[settings-previews-sticky-conflict]
tests/test_current_screenshots.py::test_preview_stages_select_visible_subpages_and_their_scroll_owner[settings-previews-detail]
tests/test_current_screenshots.py::test_preview_stages_select_visible_subpages_and_their_scroll_owner[settings-previews-copy]
tests/test_current_screenshots.py::test_preview_stages_select_visible_subpages_and_their_scroll_owner[settings-previews-groups]
tests/test_current_screenshots.py::test_preview_stages_select_visible_subpages_and_their_scroll_owner[settings-previews-narrow]
tests/test_current_screenshots.py::test_preview_stages_select_visible_subpages_and_their_scroll_owner[settings-previews-crop-narrow]
tests/test_current_screenshots.py::test_current_inventory_and_floor_coverage
tests/test_current_screenshots.py::test_current_synthetic_owners[normal-settings-companions-populated]
tests/test_current_screenshots.py::test_current_synthetic_owners[normal-settings-companions-detail-narrow]
tests/test_current_screenshots.py::test_current_synthetic_owners[normal-settings-companions-add]
tests/test_current_screenshots.py::test_current_synthetic_owners[normal-settings-companions-source-narrow]
tests/test_current_screenshots.py::test_current_synthetic_owners[normal-settings-wanderer]
tests/test_current_screenshots.py::test_current_synthetic_owners[normal-settings-wanderer-narrow]
tests/test_current_screenshots.py::test_current_synthetic_owners[normal-settings-fleet-characters-narrow]
tests/test_current_screenshots.py::test_current_synthetic_owners[normal-settings-fleet-sharing]
tests/test_current_screenshots.py::test_current_synthetic_owners[normal-settings-fleet-sharing-details]
tests/test_current_screenshots.py::test_current_synthetic_owners[normal-settings-fleet-sharing-history-narrow]
tests/test_current_screenshots.py::test_current_synthetic_owners[late-read-settings-companions-populated]
tests/test_current_screenshots.py::test_current_synthetic_owners[late-read-settings-companions-detail-narrow]
tests/test_current_screenshots.py::test_current_synthetic_owners[late-read-settings-companions-add]
tests/test_current_screenshots.py::test_current_synthetic_owners[late-read-settings-companions-source-narrow]
tests/test_current_screenshots.py::test_current_synthetic_owners[late-read-settings-wanderer]
tests/test_current_screenshots.py::test_current_synthetic_owners[late-read-settings-wanderer-narrow]
tests/test_current_screenshots.py::test_current_synthetic_owners[late-read-settings-fleet-characters-narrow]
tests/test_current_screenshots.py::test_current_synthetic_owners[late-read-settings-fleet-sharing]
tests/test_current_screenshots.py::test_current_synthetic_owners[late-read-settings-fleet-sharing-details]
tests/test_current_screenshots.py::test_current_synthetic_owners[late-read-settings-fleet-sharing-history-narrow]
tests/test_current_screenshots.py::test_current_synthetic_owners[late-synthetic-settings-companions-populated]
tests/test_current_screenshots.py::test_current_synthetic_owners[late-synthetic-settings-companions-detail-narrow]
tests/test_current_screenshots.py::test_current_synthetic_owners[late-synthetic-settings-companions-add]
tests/test_current_screenshots.py::test_current_synthetic_owners[late-synthetic-settings-companions-source-narrow]
tests/test_current_screenshots.py::test_current_synthetic_owners[late-synthetic-settings-wanderer]
tests/test_current_screenshots.py::test_current_synthetic_owners[late-synthetic-settings-wanderer-narrow]
tests/test_current_screenshots.py::test_current_synthetic_owners[late-synthetic-settings-fleet-characters-narrow]
tests/test_current_screenshots.py::test_current_synthetic_owners[late-synthetic-settings-fleet-sharing]
tests/test_current_screenshots.py::test_current_synthetic_owners[late-synthetic-settings-fleet-sharing-details]
tests/test_current_screenshots.py::test_current_synthetic_owners[late-synthetic-settings-fleet-sharing-history-narrow]
tests/test_current_screenshots.py::test_current_synthetic_owners[invalid-settings-companions-populated]
tests/test_current_screenshots.py::test_current_synthetic_owners[invalid-settings-companions-detail-narrow]
tests/test_current_screenshots.py::test_current_synthetic_owners[invalid-settings-companions-add]
tests/test_current_screenshots.py::test_current_synthetic_owners[invalid-settings-companions-source-narrow]
tests/test_current_screenshots.py::test_current_synthetic_owners[invalid-settings-wanderer]
tests/test_current_screenshots.py::test_current_synthetic_owners[invalid-settings-wanderer-narrow]
tests/test_current_screenshots.py::test_current_synthetic_owners[invalid-settings-fleet-characters-narrow]
tests/test_current_screenshots.py::test_current_synthetic_owners[invalid-settings-fleet-sharing]
tests/test_current_screenshots.py::test_current_synthetic_owners[invalid-settings-fleet-sharing-details]
tests/test_current_screenshots.py::test_current_synthetic_owners[invalid-settings-fleet-sharing-history-narrow]
tests/test_current_screenshots.py::test_lower_cards_frame_live_content_without_actions[settings-uploading]
tests/test_current_screenshots.py::test_lower_cards_frame_live_content_without_actions[settings-uploading-recording]
tests/test_current_screenshots.py::test_lower_cards_frame_live_content_without_actions[settings-uploading-integrations]
tests/test_current_screenshots.py::test_lower_cards_frame_live_content_without_actions[settings-uploading-webhook]
tests/test_current_screenshots.py::test_lower_cards_frame_live_content_without_actions[settings-bookmarks-windows]
tests/test_current_screenshots.py::test_lower_cards_frame_live_content_without_actions[settings-bookmarks-sigbar]
tests/test_current_screenshots.py::test_lower_cards_frame_live_content_without_actions[settings-alerts-custom-narrow]
tests/test_current_screenshots.py::test_cleanup_before_any_live_hydration_erases_synthetic_content[settings-companions-populated]
tests/test_current_screenshots.py::test_cleanup_before_any_live_hydration_erases_synthetic_content[settings-wanderer]
tests/test_current_screenshots.py::test_cleanup_before_any_live_hydration_erases_synthetic_content[settings-fleet-sharing]
tests/test_current_screenshots.py::test_companion_capture_does_not_take_over_a_live_dialog
tests/test_current_screenshots.py::test_sharing_screenshot_fixture_uses_current_control_projection
tests/test_current_screenshots.py::test_sharing_screenshot_projection_guard_rejects_drift[missing-key]
tests/test_current_screenshots.py::test_sharing_screenshot_projection_guard_rejects_drift[extra-key]
tests/test_current_screenshots.py::test_sharing_screenshot_projection_guard_rejects_drift[missing-item]
tests/test_current_screenshots.py::test_sharing_screenshot_projection_guard_rejects_drift[extra-item]
tests/test_current_screenshots.py::test_sharing_screenshot_projection_guard_rejects_drift[reordered-items]
tests/test_current_screenshots.py::test_sharing_screenshot_projection_guard_rejects_drift[bool-as-int]
tests/test_current_screenshots.py::test_sharing_screenshot_projection_guard_rejects_drift[int-as-bool]
tests/test_current_screenshots.py::test_sharing_screenshot_projection_guard_rejects_drift[int-as-float]
tests/test_current_screenshots.py::test_sharing_screenshot_projection_guard_rejects_drift[changed-bool]
tests/test_current_screenshots.py::test_sharing_screenshot_projection_guard_rejects_drift[changed-int]
tests/test_current_screenshots.py::test_sharing_screenshot_projection_guard_rejects_drift[stale-string]
tests/test_current_screenshots.py::test_sharing_screenshot_projection_guard_rejects_drift[changed-null]
tests/test_current_screenshots.py::test_sharing_screenshot_lifecycle_preserves_live_authority[cold]
tests/test_current_screenshots.py::test_sharing_screenshot_lifecycle_preserves_live_authority[live-before]
tests/test_current_screenshots.py::test_sharing_screenshot_lifecycle_preserves_live_authority[live-during]
tests/test_current_screenshots.py::test_sharing_screenshot_lifecycle_preserves_live_authority[cold-then-live]
tests/test_current_screenshots.py::test_sharing_screenshot_lifecycle_preserves_live_authority[repeat]
tests/test_current_screenshots.py::test_sharing_screenshot_lifecycle_preserves_live_authority[authority]
tests/test_current_screenshots.py::test_sharing_screenshot_lifecycle_preserves_live_authority[focus]
tests/test_current_screenshots.py::test_sharing_screenshot_lifecycle_preserves_live_authority[worklists]
tests/test_current_screenshots.py::test_sharing_cleanup_preserves_failed_refresh_authority[cached]
tests/test_current_screenshots.py::test_sharing_cleanup_preserves_failed_refresh_authority[same]
tests/test_current_screenshots.py::test_sharing_cleanup_preserves_failed_refresh_authority[newer]
tests/test_current_screenshots.py::test_wanderer_cleanup_obeys_live_binding_health_fence[live]
tests/test_current_screenshots.py::test_wanderer_cleanup_obeys_live_binding_health_fence[buffered]
tests/test_current_screenshots.py::test_fleet_capture_refuses_pending_live_writes[toggle-button]
tests/test_current_screenshots.py::test_fleet_capture_refuses_pending_live_writes[toggle-check]
tests/test_current_screenshots.py::test_fleet_capture_refuses_pending_live_writes[reset]
tests/test_current_screenshots.py::test_fleet_capture_refuses_pending_live_writes[character]
tests/test_current_screenshots.py::test_fleet_capture_refuses_pending_live_writes[overlap]
tests/test_current_screenshots.py::test_sharing_capture_refuses_pending_browser_actions[pair]
tests/test_current_screenshots.py::test_sharing_capture_refuses_pending_browser_actions[grant]
tests/test_current_screenshots.py::test_sharing_capture_refuses_pending_browser_actions[overlap]
tests/test_current_screenshots.py::test_fleet_cleanup_restores_focused_master_without_changing_live_focus_policy
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[None-settings-companions-populated]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[None-settings-fleet-sharing-history-narrow]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[prepare-settings-companions-populated]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[prepare-settings-fleet-sharing-history-narrow]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[entry-settings-companions-populated]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[entry-settings-fleet-sharing-history-narrow]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[stage-settings-companions-populated]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[stage-settings-fleet-sharing-history-narrow]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[verify-settings-companions-populated]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[verify-settings-fleet-sharing-history-narrow]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[capture-settings-companions-populated]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[capture-settings-fleet-sharing-history-narrow]
tests/test_fittings_page.py::test_copy_context_stays_outside_the_only_body_scroller
tests/test_fittings_page.py::test_copy_dialog_bounds_its_existing_scroller_without_overlaying_the_footer
tests/test_fittings_page.py::test_copy_pair_identity_is_the_only_row_local_sticky_owner
tests/test_fittings_page.py::test_copy_dynamic_header_and_progress_respect_hidden[#fittings-copy-summary[hidden]]
tests/test_fittings_page.py::test_copy_dynamic_header_and_progress_respect_hidden[#fittings-copy-limit-summary[hidden]]
tests/test_fittings_page.py::test_copy_dynamic_header_and_progress_respect_hidden[#fittings-copy-progress[hidden]]
tests/test_fittings_page.py::test_copy_progress_is_compact_and_not_decoratively_animated
tests/test_fittings_page.py::test_copy_progress_retains_a_visible_forced_colour_track_and_value
tests/test_fittings_page.py::test_copy_technical_disclosure_keeps_support_id_selectable_and_wrapped
tests/test_fittings_page.py::test_copy_native_skip_focus_uses_the_painted_label_bounds
tests/test_fittings_page.py::test_copy_mirrored_live_status_removes_the_visible_status_spacing
tests/test_fittings_page.py::test_expanded_fitting_keeps_its_identity_above_the_detail
tests/test_fittings_page.py::test_fitting_visual_header_labels_existing_controls_without_table_roles
tests/test_fittings_page.py::test_fitting_header_and_rows_share_deliberate_tracks_and_insets
tests/test_fittings_page.py::test_fitting_selection_helpers_and_primary_share_one_action_area
tests/test_fittings_page.py::test_fitting_details_stack_at_reachable_floor_without_another_scroller
tests/test_fittings_page.py::test_fitting_native_expanders_use_the_shared_focus_token[.fit-row-toggle:focus-visible]
tests/test_fittings_page.py::test_fitting_native_expanders_use_the_shared_focus_token[.fit-metadata-disclosure > summary:focus-visible]
tests/test_fittings_page.py::test_detail_module_wrapping_does_not_restyle_shared_clipboard_review
tests/test_fittings_page.py::test_fitting_checkbox_focus_scrolls_its_visible_label
tests/test_fittings_page.py::test_fitting_forced_colour_outline_is_decided_at_root
tests/test_fittings_page.py::test_clipboard_import_is_inline_labelled_and_keeps_status_mounted
tests/test_fittings_page.py::test_the_nav_button_exists_and_points_at_the_route
tests/test_fittings_page.py::test_route_uses_shared_eve_workspace_class
tests/test_fittings_page.py::test_eve_workspace_css_has_required_properties
tests/test_fittings_page.py::test_eve_workspace_active_sets_display_grid
tests/test_fittings_page.py::test_primary_action_alignment_shared_rule
tests/test_fittings_page.py::test_there_are_exactly_four_destinations
tests/test_fittings_page.py::test_the_route_map_carries_fittings
tests/test_fittings_page.py::test_fittings_is_gated_with_the_other_eve_destinations
tests/test_fittings_page.py::test_fittings_joins_the_remembered_destination_list
tests/test_fittings_page.py::test_the_script_is_included
tests/test_fittings_page.py::test_fittings_registers_the_enter_leave_contract
tests/test_fittings_page.py::test_entry_asks_python_for_state_exactly_once
tests/test_fittings_page.py::test_returning_from_settings_after_an_authority_change_rereads_fittings_state
tests/test_fittings_page.py::test_fittings_state_bridge_call_matches_a_real_api_method
tests/test_fittings_page.py::test_the_pager_can_actually_hide
tests/test_fittings_page.py::test_screenshot_state_handler_is_allowlisted_bounded_and_read_only
tests/test_fittings_page.py::test_screenshot_mode_intercepts_reads_and_is_cleared_on_route_leave
tests/test_fittings_page.py::test_copy_selection_is_pruned_to_the_current_rendered_page
tests/test_fittings_page.py::test_filter_collection_and_page_changes_clear_selection_before_refetch
tests/test_fittings_page.py::test_route_leave_force_closes_copy_and_resets_progress_phase
tests/test_fittings_page.py::test_rejected_discrete_edits_immediately_requery_persisted_state
tests/test_fittings_page.py::test_rejected_fitting_delete_requeries_without_clearing_page_state
tests/test_fittings_page.py::test_refresh_refusal_error_is_rendered_from_semantic_progress
tests/test_fittings_page.py::test_copy_has_preflight_progress_and_results_overlays
tests/test_fittings_page.py::test_rejected_conflict_recheck_preserves_the_usable_preflight
tests/test_fittings_page.py::test_copy_conflicts_offer_alternate_name_or_explicit_skip
tests/test_fittings_page.py::test_copy_results_name_every_terminal_category_and_never_offer_retry
tests/test_fittings_page.py::test_copy_result_terminal_states_use_existing_semantic_tokens
tests/test_fittings_page.py::test_copy_identity_text_can_wrap_in_review_results_and_progress
tests/test_fittings_page.py::test_fittings_empty_state_starts_hidden_until_the_first_payload
tests/test_fittings_page.py::test_fittings_hands_character_management_off_to_settings
tests/test_fittings_page.py::test_fittings_empty_and_copy_target_copy_name_settings_without_auth_controls
tests/test_fittings_page.py::test_copy_selected_remains_the_only_accent_action
tests/test_fittings_page.py::test_fittings_primary_action_includes_workspace_primary_token
tests/test_fittings_page.py::test_render_pager_defaults_page_when_the_payload_has_none
tests/test_fittings_page.py::test_fittings_worker_reuses_process_and_preserves_business_outcomes
tests/test_fittings_page.py::test_fittings_worker_vm_failures_preserve_stack_and_recover
tests/test_fittings_page.py::test_fittings_worker_cancels_pending_timer[pending-timer-normal-exit]
tests/test_fittings_page.py::test_fittings_worker_cancels_pending_timer[pending-timer-assertion-exit]
tests/test_fittings_page.py::test_copy_accessibility_in_node[checkbox-name]
tests/test_fittings_page.py::test_copy_accessibility_in_node[dialog-description]
tests/test_fittings_page.py::test_copy_accessibility_in_node[tab-wrap]
tests/test_fittings_page.py::test_copy_accessibility_in_node[tab-outside]
tests/test_fittings_page.py::test_copy_accessibility_in_node[hidden-controls]
tests/test_fittings_page.py::test_copy_accessibility_in_node[close]
tests/test_fittings_page.py::test_copy_accessibility_in_node[escape]
tests/test_fittings_page.py::test_copy_accessibility_in_node[fallback-detached]
tests/test_fittings_page.py::test_copy_accessibility_in_node[fallback-hidden]
tests/test_fittings_page.py::test_copy_accessibility_in_node[fallback-invisible]
tests/test_fittings_page.py::test_copy_accessibility_in_node[fallback-disabled]
tests/test_fittings_page.py::test_copy_accessibility_in_node[shared-dialog]
tests/test_fittings_page.py::test_copy_accessibility_in_node[progress-focus]
tests/test_fittings_page.py::test_copy_accessibility_in_node[progress-tab]
tests/test_fittings_page.py::test_copy_accessibility_in_node[cancel-focus]
tests/test_fittings_page.py::test_copy_accessibility_in_node[cancel-tab]
tests/test_fittings_page.py::test_copy_accessibility_in_node[progress-shared-dialog]
tests/test_fittings_page.py::test_copy_accessibility_in_node[review-scroller]
tests/test_fittings_page.py::test_copy_accessibility_in_node[results-scroller]
tests/test_fittings_page.py::test_copy_accessibility_in_node[interleaving-complete-dismiss]
tests/test_fittings_page.py::test_copy_accessibility_in_node[interleaving-queued-complete-dismiss]
tests/test_fittings_page.py::test_copy_accessibility_in_node[interleaving-rollback-false-cancel]
tests/test_fittings_page.py::test_copy_accessibility_in_node[interleaving-rollback-null-cancel]
tests/test_fittings_page.py::test_copy_accessibility_in_node[interleaving-rollback-false-uncancelled]
tests/test_fittings_page.py::test_copy_accessibility_in_node[interleaving-rollback-null-uncancelled]
tests/test_fittings_page.py::test_copy_accessibility_in_node[interleaving-root-tab]
tests/test_fittings_page.py::test_copy_accessibility_in_node[interleaving-descendant-tab]
tests/test_fittings_page.py::test_copy_accessibility_in_node[progress]
tests/test_fittings_page.py::test_copy_accessibility_in_node[route-leave]
tests/test_fittings_page.py::test_fittings_state_machine_in_node[state-route-lifecycle]
tests/test_fittings_page.py::test_fittings_state_machine_in_node[state-request-sequence]
tests/test_fittings_page.py::test_fittings_state_machine_in_node[state-selection-scope]
tests/test_fittings_page.py::test_fittings_state_machine_in_node[state-detail-sequence]
tests/test_fittings_page.py::test_fittings_state_machine_in_node[state-rejected-mutation]
tests/test_fittings_page.py::test_fittings_state_machine_in_node[state-screenshot-progress]
tests/test_fittings_page.py::test_fittings_state_machine_in_node[state-stale-preflight]
tests/test_fittings_page.py::test_fittings_state_machine_in_node[state-stale-progress]
tests/test_fittings_page.py::test_fittings_state_machine_in_node[state-ticket-progress]
tests/test_fittings_page.py::test_fittings_state_machine_in_node[state-stale-start-result]
tests/test_fittings_page.py::test_fittings_state_machine_in_node[state-copy-lifecycle]
```
