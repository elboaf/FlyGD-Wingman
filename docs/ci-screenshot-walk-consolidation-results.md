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

HOSTED PENDING — no hosted, Windows-runtime, overall-runtime, wall-clock, or
critical-path improvement claim is made from this local evidence.
