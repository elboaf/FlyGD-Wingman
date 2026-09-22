# Fleet test-budget consolidation tranche results

## Source identities

The tranche identities are pinned so each verification claim names the code it exercised. The initial evidence was captured before the results commit; the final test-bearing HEAD was added after the bounded polish wave.

| Identity | Command | Literal output |
|---|---|---|
| Merge base | `git merge-base origin/main HEAD` | `78adb17a8346f4810f48863dd10a87c386091948` |
| Pre-polish implementation HEAD | `git rev-parse HEAD` before the results commit | `65ff70c9a037697e206e662db451b82871eee9be` |
| Final test-bearing HEAD | `git rev-parse HEAD` before this documentation-only follow-up | `35aad4886d9cc15f32860e7ebd01723082f47dcf` |
| Tranche implementation base | Plan ledger and `git log` | `5a1b800b` (`docs: align Fleet plan parameter names`) |
| Windows reference | GitHub Actions | [`35534240008`](https://github.com/elboaf/FlyGD-Wingman/actions/runs/35534240008) at `78adb17a8346f4810f48863dd10a87c386091948` |

The ten implementation commits from `5a1b800b..65ff70c9` are:

```text
65ff70c9a037697e206e662db451b82871eee9be test: remove temporary Fleet mutation witnesses
0919f37ff7b8f64c62f83a5e08ad1dcfd7714fcb test: assert retained Fleet source metadata
846e7793289299780d6ba1deaa26306bdeff197b test: target Fleet source retirement capacity
90e0ff1582d7e0a30b6610a041f0e305e44bec82 test: consolidate Fleet source admission contracts
f56e931a3c06b19302fcaece498fc1980107005d test: preserve Fleet CAS replacement coverage
207bf0a0a153341638d18cb3cbb249f67c6caaa3 test: consolidate Fleet completion authority contracts
19f926fc2335450316dd4957158627b120eb9d43 test: consolidate Fleet cadence contracts
69b6e8f4c5617e72bdc33205f4718e3c939bae7a test: share Fleet signed publication transport
6708baceae37bfe2a1518dee4e5ba3b1db7dd25f test: split Fleet cadence persistence seams
b05c3aa5aa44a6cfe103cff6582eac67d8b6b50a test: classify Fleet transport resource probe
```

The targeted files had no changes between the Windows reference SHA and `5a1b800b`. The complete branch contains earlier, unrelated work, so complete-suite Windows-reference and fresh Linux totals are recorded as separate observations rather than a tranche speedup.

## Contract changes

The tranche changed test architecture and inventory only. `git diff --name-only 5a1b800b..65ff70c9 -- wingman .github` produced no output: no production or workflow files changed.

| Area | Before nodes | After nodes | Contract result |
|---|---:|---:|---|
| `tests/test_fleetsharing_cadence.py` | 139 | 75 | Scheduler products use in-memory state that is capacity-checked on save; only explicit FileStore signed PUT, external GET, and JSON/capacity representatives exercise persisted decode/validation, save-before-I/O, and atomic-file boundaries. Ordinary horizons and Cartesian products were consolidated while recurrence and stale-to-live representatives remain explicit. |
| `tests/test_fleetsharing_source_admission.py` | 201 | 120 | Durable file-backed authority, completion, error, barrier, rights, deadline, save, and lock-order contracts remain through explicit representative tuples. |
| `tests/test_fleetsharing_worker_timing_mutations.py` | 25 | 0 | All 25 temporary mutation witnesses passed once against the final direct regressions, then the permanent mutation-of-test module was deleted. |
| `tests/test_fleetsharing_transport_resources.py` | 3 | 3 | Two ordinary transport contracts remain required; the 47 MB maximum-response reader/codec contract is marked `resource`, has a 75-second parent wall budget, and publishes JUnit resource evidence. |
| `tests/test_fleetsharing_worker_revision.py` | 37 | 32 | The 260-cycle repeated lifecycle became three real durable recurrences plus three symbolic `MAX_SOURCE_INTENTS - 1`, `MAX_SOURCE_INTENTS`, and `MAX_SOURCE_INTENTS + 1` pruning boundaries. Eight permanent revision mutation witnesses were removed after each mutant triggered a direct regression failure under the broad witness harness. |
| **Five-file total** | **405** | **230** | **175 targeted nodes removed or consolidated; retained contracts are listed below.** |

The suite also gained three `tests/test_ci_timing.py` guards for strict marker registration, resource-marker ownership, and JUnit resource-property preservation. The reference run reported 16,421 cases; the fresh local suite reported 16,249 outcomes (`16,235 passed + 14 skipped`). Because the branch includes unrelated pre-tranche changes and the platforms differ, that complete-suite delta is not attributed solely to this tranche.

### Retained representatives

| Contract | Retained representative/evidence |
|---|---|
| Signed publisher PUT and save-before-I/O | `test_publisher_trace_crosses_real_signed_client` with an injected durable cadence store. |
| External receiver GET | `test_external_put_trace_preserves_original_origins_and_nullable_values` with an injected durable cadence store. |
| JSON, capacity validation, and atomic file boundary | `test_timed_relay_captures_valid_combat_rows_at_json_boundary` remains file-backed. |
| Cadence recurrence | Renewed-source scenarios retain the 60-second recurrence horizon; repeated metadata bursts remain direct. |
| Receiver stale-to-live transition | Two phase-aligned 40-second representatives retain the transition while ordinary mixed scenarios use 20 seconds. |
| Completion authority and durable 401 | Explicit publication/off, during-save/after-save, replacement/lifecycle/current-authority tuples remain file-backed. |
| Barrier and disclosure rights | Explicit unwrap/save/signing/prehook/after-start representatives; all three combat rights collections; uncertain-member refusal. |
| Source retirement recurrence | Three complete durable source retirement lifecycles. |
| Source metadata capacity | Direct below/at/above `MAX_SOURCE_INTENTS` setup verifies observation, generation, retry, failure, served, unrelated metadata, and read-deadline retention. |
| Ordinary transport | Maximum PUT escaping and memory-probe fallback remain in `-m "not resource"`. |
| Maximum response resource | Exact 47,022,137 bytes, 8,192 rows, 155,648 observations, real reader and Python fleetsharing protocol codec. The native release settings codec remains a separate full-suite prerequisite. |

The tranche file boundary is:

```text
M pyproject.toml
M scripts/summarize_pytest_junit.py
M tests/test_ci_timing.py
M tests/test_fleetsharing_cadence.py
M tests/test_fleetsharing_source_admission.py
M tests/test_fleetsharing_transport_resources.py
M tests/test_fleetsharing_worker.py
M tests/test_fleetsharing_worker_revision.py
D tests/test_fleetsharing_worker_timing_mutations.py
```

`tests/test_fleetsharing_worker.py` changed only the shared test helper to call the store interface's `load()`, preserving fresh disk reloads for `FileStore` while allowing the cadence in-memory store. No generated XML or JSON is tracked; fresh evidence was written under `/tmp`.

## Mutation evidence

Every production mutation was temporary and restored before commit. Non-killing probes that targeted immediately duplicated checks are recorded rather than strengthened into compound mutations.

| Task/probe | Test command or selection | Actual result | Ruling |
|---|---|---|---|
| Resource wall budget set temporarily to zero | `uv run --no-sync python -m pytest tests/test_fleetsharing_transport_resources.py -m resource -q -s` | `1 failed, 2 deselected`; failure included `maximum response resource budget exceeded` and complete JSON evidence. | Valid RED; budget restored to `75.0`. |
| Cadence retained timing witnesses after consolidation | Task 3 final permanent-witness selection | `11 passed in 3.87s` | Retained direct cadence tests still rejected the weakened implementations. |
| Completion: remove an error-path generic check | Retained durable-401/current-error and Off/error-install families | `10 passed`, then `15 passed`; success-path candidates also produced `26 passed` and `25 passed`. | Redundant/non-applicable because later completion checks own the same boundary. |
| Completion: bypass `_with_publication_source_locked` admission | `uv run --no-sync python -m pytest tests/test_fleetsharing_source_admission.py::test_original_source_guards_actual_completion_install -q` | `7 failed in 5.20s`; revoked publication rows failed because `_Obsolete` was absent. | Valid replacement RED; exact mutation also prevented current/inactive setup installs, which is recorded in Task 4 evidence. |
| Completion: remove `validate_publication()` check | Retained final-authority family | `9 passed in 3.14s` | Redundant/non-applicable because `_validate_publication_permission_locked()` repeats the same check. |
| Completion: bypass original-source reset guard | `test_original_source_guards_post_save_401_reset` | `4 failed, 1 passed in 4.18s`; all revoked rows detected the obsolete reset and the current control passed. | Valid RED. |
| Barrier: bypass source-admission leaf | `test_actual_publication_barriers_fence_before_start_and_late_completion[signing-source]` | Failed because one unexpected PUT was sent. | Valid RED. |
| Barrier: remove generic post-start check | `test_actual_publication_barriers_fence_before_start_and_late_completion[after_start-source]` | Passed. | Redundant with the independent completion source-authority check; no compound mutation was forced. |
| Disclosure rights omissions | `test_final_held_disclosure_and_applicable_withdrawal_rights[approved_capabilities-combat]`, `[session_approved_capabilities-combat]`, and `[acknowledged_capabilities-combat]` | Each retained row failed because `_Obsolete` was not raised. | Three valid RED probes. |
| Uncertain-member fallthrough | `test_any_uncertain_member_prevents_whole_inactivity_withdrawal[legacy-False-True]` | Failed because a destructive empty PUT was sent. | Valid RED. |
| Source retirement observation pruning removed | `uv run --no-sync python -m pytest tests/test_fleetsharing_worker_revision.py::test_terminal_only_source_retirement_bounds_observation_and_retry_metadata -q` | `3 failed in 3.61s`. | Valid RED at all symbolic rows. |
| Source retirement scheduler retention removed | Same three-row command | `3 failed in 3.58s`. | Valid RED at all symbolic rows. |
| Source retirement generation retention removed | Same three-row command | `3 failed in 3.82s`. | Valid RED at all symbolic rows. |
| Final timing mutation corpus before deletion | `uv run --no-sync python -m pytest tests/test_fleetsharing_worker_timing_mutations.py -q` | `25 passed in 5.01s`. | All deliberate timing mutants were rejected before deletion. |
| Final revision mutation corpus before deletion | `uv run --no-sync python -m pytest tests/test_fleetsharing_worker_revision.py::test_revision_guards_kill_in_memory_mutants -q` | `8 passed in 3.35s`. | Each mutant caused its direct regression to raise `AssertionError` or `pytest.fail.Exception`. Because the outer harness accepted either exception, this run proves a direct regression failure per mutant but not, by itself, the intended assertion. The three specific source-metadata pruning RED probes above remain the stronger assertion-level evidence for that boundary. |
| Direct product regressions after mutation-corpus deletion | `uv run --no-sync python -m pytest tests/test_fleetsharing_worker_timing.py tests/test_fleetsharing_worker_revision.py tests/test_fleetsharing_cadence.py -q --durations=30` | Fresh post-commit result: `162 passed in 13.75s`. | Direct product regressions remain after witness removal. |

## Local timing evidence

All timings in this section are Linux observations from this worktree unless explicitly labelled as the hosted Windows reference. They are not Windows projections.

### Reference Windows and fresh local targeted files

| Target file | Reference Windows run `35534240008` cases | Reference Windows testcase sum | Fresh local full-suite cases | Fresh local testcase sum |
|---|---:|---:|---:|---:|
| `test_fleetsharing_cadence.py` | 139 | 318.8s | 75 | 3.240s |
| `test_fleetsharing_source_admission.py` | 201 | 67.8s | 120 | 11.856s |
| `test_fleetsharing_worker_timing_mutations.py` | 25 | 46.8s | 0 | 0.000s |
| `test_fleetsharing_transport_resources.py` | 3 | 44.6s | 3 | 5.795s |
| `test_fleetsharing_worker_revision.py` | 37 | 40.7s | 32 | 2.626s |
| **Total** | **405** | **518.7s from displayed rounded rows; reference report total 518.8s** | **230** | **23.517s** |

The cross-platform columns establish inventory and two separate measured observations only. No Linux-to-Windows speedup percentage is claimed.

### Task-local before/after evidence

| Slice | Before | After |
|---|---|---|
| Cadence persistence seam, unchanged inventory | 139 cases, 424.768s JUnit sum | 139 cases, 29.129s JUnit sum |
| Cadence final consolidation | 139 cases before consolidation | 75 cases, 3.341s JUnit sum in Task 3; 3.240s in the fresh full suite |
| Source admission Task 4 intermediate | 201 reference nodes | 156 cases, 20.142s JUnit sum |
| Source admission Task 5 final | 156 intermediate nodes | 120 cases, 20.130s JUnit sum; 11.856s in the fresh full suite |
| Source retirement stress | Original 260-cycle test: 14.80s call, 17.30s pytest, 19.92s wall | Four replacement nodes: 0.34s summed calls, 1.60s pytest, 2.62s wall in Task 6 |
| Maximum-response resource | Task 1: 6.094s JUnit sum | Fresh focused resource: 5.822s JUnit sum |
| Permanent timing mutation witnesses | 25 passed in 5.01s | Deleted after final execution; direct regressions passed after deletion |

### Fresh focused selection

Command:

```bash
uv run --no-sync python -m pytest \
  tests/test_fleetsharing_cadence.py \
  tests/test_fleetsharing_source_admission.py \
  tests/test_fleetsharing_worker_revision.py \
  tests/test_fleetsharing_transport_resources.py \
  tests/test_ci_timing.py \
  -m "not resource" -q -rs --durations=50 \
  --junitxml=/tmp/fleet-required.xml
```

Result: `237 passed, 1 deselected in 29.70s`.

The summary command

```bash
uv run --no-sync python scripts/summarize_pytest_junit.py \
  /tmp/fleet-required.xml /tmp/fleet-required.json
```

reported `21.401s` summed testcase time:

| File | Cases | Seconds |
|---|---:|---:|
| `tests/test_fleetsharing_cadence.py` | 75 | 3.309 |
| `tests/test_fleetsharing_source_admission.py` | 120 | 12.000 |
| `tests/test_fleetsharing_worker_revision.py` | 32 | 2.870 |
| `tests/test_fleetsharing_transport_resources.py` | 2 | 0.040 |
| `tests/test_ci_timing.py` | 8 | 3.182 |

Fresh resource command:

```bash
uv run --no-sync python -m pytest \
  tests/test_fleetsharing_transport_resources.py \
  -m resource -q -s --durations=0 \
  --junitxml=/tmp/fleet-resource.xml
```

Result: `1 passed, 2 deselected in 7.96s`. The summary command was:

```bash
uv run --no-sync python scripts/summarize_pytest_junit.py \
  /tmp/fleet-resource.xml /tmp/fleet-resource.json
```

It reported `5.822s` and exactly one resource-evidence row:

| Property | Value |
|---|---|
| `resource.subprocess_wall_seconds` | `5.8128084220002165` |
| `resource.memory_metric` | `process_peak_rss_kib` |
| `resource.memory_peak` | `301028` |
| `resource.raw_bytes` | `47022137` |
| `resource.rows` | `8192` |
| `resource.observations` | `155648` |

### Fresh complete local verification

Prerequisites and complete verification were run with the exact Task 8 commands. The codec install/availability command was:

```bash
uv run --no-sync python -c "import os, pathlib, shutil; from wingman.evesettings import codec; name = 'wingman-settings-codec' + ('.exe' if os.name == 'nt' else ''); source = pathlib.Path('packaging/settings-codec/target/release') / name; target = pathlib.Path('packaging/bin') / name; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target); assert codec.codec_available(), 'Native integration tests require the built codec'"
```

| Command | Result |
|---|---|
| `uv sync --locked --extra dev` | Exit 0: resolved 56 packages; checked 39 packages. |
| `node --version` | Exit 0: `v26.5.0`. |
| `cargo build --locked --release --manifest-path packaging/settings-codec/Cargo.toml --target-dir packaging/settings-codec/target` | Exit 0: release codec built in 4.91s. |
| Codec copy/availability assertion command from Task 8 | Exit 0 with no output; `codec.codec_available()` asserted. |
| `uv run --no-sync python -m pytest tests/ -q -rs --durations=50 --junitxml=/tmp/fleet-tranche-full.xml` | Exit 0: `16235 passed, 14 skipped in 517.37s (0:08:37)`. |
| `uv run --no-sync python scripts/summarize_pytest_junit.py /tmp/fleet-tranche-full.xml /tmp/fleet-tranche-full.json` | Exit 0: `477.015s` summed testcase time and one resource-evidence row. |
| `node scripts/js_smoke.js` | Exit 0: `PASS every page module loaded`. |
| `cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml` | Exit 0: `1 passed; 0 failed`. |
| `uv run --extra dev ruff check .` | Exit 0: `All checks passed!`. |
| `uv run --extra dev ruff format --check .` | Exit 0: `515 files already formatted`. |
| `git diff --check` | Exit 0 with no output before the results document was written. |

The fresh full-suite resource row was:

| Property | Value |
|---|---|
| `resource.subprocess_wall_seconds` | `5.763258072999633` |
| `resource.memory_metric` | `process_peak_rss_kib` |
| `resource.memory_peak` | `342132` |
| `resource.raw_bytes` | `47022137` |
| `resource.rows` | `8192` |
| `resource.observations` | `155648` |

### Skip inventory

All 14 skips are intentional Linux platform/capability skips. There were no Node, codec, or unexpected native-availability skips.

| Count | Test/reason |
|---:|---|
| 1 | `tests/test_clipserve.py`: delete-while-open is a Windows sharing rule |
| 3 | `tests/test_evesettings_profilecopy.py`: requires a real Windows junction |
| 1 | `tests/test_eveskills_dpapi.py`: requires real DPAPI |
| 1 | `tests/test_eveskills_dpapi.py`: requires real WinDLL |
| 1 | `tests/test_preview_host.py`: needs a real message pump and window station |
| 3 | `tests/test_preview_win32.py`: binds `user32`/`gdi32`/`dwmapi` |
| 1 | `tests/test_tray.py`: pystray Windows backend |
| 2 | `tests/test_ui_setup_profile.py`: requires real Windows junction |
| 1 | `tests/test_wanderer_integration.py`: real Windows user-bound DPAPI required |

### Scope and leftover checks

The prescribed scope commands produced:

- `git status --short`: no output before the results document was created.
- `git diff --stat HEAD~7..HEAD`: four files, 289 insertions, 610 deletions. Because review fixes produced ten implementation commits, this seven-commit window does not cover the complete tranche.
- `git diff --check HEAD~7..HEAD`: exit 0, no output.
- Supplemental complete range `git diff --stat 5a1b800b..65ff70c9`: nine files, 445 insertions, 630 deletions.
- `git diff --check 5a1b800b..65ff70c9`: exit 0, no output.
- `git diff --name-only 5a1b800b..65ff70c9 -- wingman .github`: no output.
- The prescribed debug, zero-budget, and placeholder search across `pyproject.toml`, `scripts`, `tests`, and this document was repeated after this document was written and returned no matches (`rg` exit 1).

No workflow changes, production changes, temporary zero budget, debug instrumentation, placeholders, or tracked generated evidence were found.

### Post-polish final verification

A bounded polish wave corrected the exact resource-owner guard, removed single-value source-admission parameterizations, simplified now-unreachable test branches, and corrected documentation claims. On final test-bearing HEAD `35aad4886d9cc15f32860e7ebd01723082f47dcf`, fresh verification produced:

| Command | Result |
|---|---|
| `uv run --no-sync python -m pytest tests/ -q -rs --durations=30 --junitxml=/tmp/fleet-tranche-final-polished.xml` | `16235 passed, 14 skipped in 539.32s (0:08:59)` |
| Focused final Fleet/CI selection | `238 passed in 33.66s` |
| `uv run --no-sync python -m pytest tests/test_documentation.py -q` | `7 passed in 1.11s` |
| Focused Ruff check | `All checks passed!` |
| Focused Ruff format check | `7 files already formatted` |
| `git diff --check` | Exit 0, no output |

The 14 skips match the earlier inspected Linux platform/capability inventory; no Node or settings-codec availability skip was introduced. This final run supersedes the pre-polish full-suite result for branch-completion status while retaining the earlier timing as historical tranche evidence.

## Hosted Windows evidence

PR [#277](https://github.com/elboaf/FlyGD-Wingman/pull/277) produced the required hosted evidence at branch SHA `2ed88f372edba7f94cd815d484595960236b984b`:

- CI run: [`35684157184`](https://github.com/elboaf/FlyGD-Wingman/actions/runs/35684157184)
- Windows job: [`106607316881`](https://github.com/elboaf/FlyGD-Wingman/actions/runs/35684157184/job/106607316881)
- Ubuntu job: [`106607316829`](https://github.com/elboaf/FlyGD-Wingman/actions/runs/35684157184/job/106607316829)

The controlled comparison is the immediately preceding successful `main` run for UX merge `cfa1aca256c2aadf7082bbb5061275c749e345c6`, whose added tests are also present in the PR run:

- baseline run: [`35643273320`](https://github.com/elboaf/FlyGD-Wingman/actions/runs/35643273320)
- baseline Windows job: [`106477509176`](https://github.com/elboaf/FlyGD-Wingman/actions/runs/35643273320/job/106477509176)

| Hosted metric | Current `main` | PR #277 | Change |
|---|---:|---:|---:|
| Required critical path | 19m46s | 13m49s | -5m57s (-30.1%) |
| Windows job | 19m46s | 13m48s | -5m58s (-30.2%) |
| Windows pytest step | 18m42s | 12m41s | -6m01s (-32.2%) |
| Ubuntu job | 8m20s | 6m29s | -1m51s (-22.2%) |
| Ubuntu pytest step | 7m45s | 6m07s | -1m38s (-21.1%) |
| Windows JUnit testcase sum | 1084.184s | 724.378s | -359.806s (-33.2%) |
| Windows cases | 16,844 | 16,672 | -172 |
| Five-target Windows sum | 443.268s | 72.547s | -370.721s (-83.6%) |

The target-file result by owner was:

| Target | Current `main` | PR #277 |
|---|---:|---:|
| Cadence | 261.008s / 139 cases | 5.240s / 75 cases |
| Source admission | 57.743s / 201 cases | 18.164s / 120 cases |
| Timing mutations | 43.598s / 25 cases | deleted |
| Maximum transport resource | 45.269s / 3 cases | 44.550s / 3 cases |
| Worker revision | 35.650s / 37 cases | 4.593s / 32 cases |

All three required checks passed. The resource test deliberately remains in current PR CI until the later cadence/workflow phase; its stable 44.550-second Windows cost is now measured rather than inferred.

## Stop/go conclusion

**GO for the bounded Fleet tranche:** the hosted target-set sum fell 83.6%, the Windows pytest step fell 32.2%, and the required critical path fell 30.1%. Contract representatives, resource evidence, Node, native settings codec, Cargo, JS smoke, Ruff, and both hosted platforms passed.

**GO for a separate remaining-hotspot consolidation plan:** PR CI still takes 13m49s and the Windows job still takes 13m48s, missing both the five-minute required-path ceiling and ten-minute complete-Windows ceiling. The next plan should start from PR #277's Windows artifact and the ranked non-resource hotspots below.

**STOP for workflow selection, budget enforcement, and Windows sharding:** consolidate the remaining serial hotspots first, remeasure, and authorize workflow tiers or whole-file shards only at the approved stop/go gates.

The leading non-resource Windows owners are `test_ui_setup_controller.py` (44.067s), `test_shoot_screens.py` (38.610s), `test_fleetsharing_capacity.py` (30.868s), `test_new_screenshots.py` (26.005s), `test_current_screenshots.py` (25.852s), `test_fittings_page.py` (23.838s), `test_preview_savedlayouts_page.py` (20.796s), and `test_ui_setup_profile.py` (20.590s). The top ten files including the resource probe own 293.4 summed seconds; the top twenty own 430.2 seconds.

### Self-review

- Compared every required section and command against `task-8-brief.md`.
- Reconciled the Windows reference table with `docs/ci-test-budget-redesign.md` and the fresh local JUnit JSON.
- Kept Windows and Linux timing observations explicitly separate.
- Used the full `5a1b800b..65ff70c9` tranche range in addition to the prescribed `HEAD~7` check because the implementation contains ten commits.
- Confirmed the targeted files were unchanged between the reference SHA and tranche base.
- Confirmed every valid mutation probe has RED evidence and every redundant probe is explicitly ruled rather than presented as a kill.
- Confirmed the complete skip inventory contains no Node or codec skip.
- Confirmed no product, workflow, generated XML/JSON, debug, zero-budget, placeholder, or broader-hotspot change is included.
- Confirmed this results document is the only intended Task 8 commit content.

### Concerns

- Hosted Windows evidence confirms the tranche improvement but still misses the five-minute required-path and ten-minute complete-Windows ceilings; workflow selection, budget enforcement, and sharding remain unauthorized pending broader consolidation.
- The pre-polish Linux full suite took 517.37 seconds and the final polished suite took 539.32 seconds wall time; runner variation was not investigated, and several non-target files remain above the design's 20-second diagnostic threshold. Those are inputs to a separate measured hotspot plan, not scope for this tranche.
- Three single-check mutation probes were non-killing because independent later checks enforce the same authority boundary. The plan ledger explicitly ruled them redundant/non-applicable; compound mutations were intentionally not forced.
- The branch contains unrelated work before tranche base `5a1b800b`; complete-suite deltas against the reference run are therefore not attributed solely to this tranche.
