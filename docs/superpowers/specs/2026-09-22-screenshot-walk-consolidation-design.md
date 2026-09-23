# Screenshot walk matrix consolidation — Stage 1 design

## Purpose

Consolidate duplicate Python-side `shoot.walk()` orchestration crossings while preserving every independently implemented screenshot, verifier, fixture, owner, worker-isolation, platform, and failure contract.

This is the first staged PR in screenshot matrix-consolidation Plan B. It reduces the selected matrices from 71 cases to 17. It is primarily contract simplification: the current 71 cases take about 3.7 seconds locally, so this stage makes no material CI-runtime prediction.

## Authority and baseline

- Source baseline: merged PR #280, commit `30422062dd23870a7356608c57f6bb625acaecab`.
- Design authority: `docs/ci-test-budget-redesign.md`.
- Hosted comparator and Plan B authorization: `docs/ci-persistent-screenshot-harness-results.md`.
- Current four-file inventory: `246 / 90 / 160 / 101 = 597` test identities.
- Workflow selection, budget enforcement, sharding, and overall-runtime claims remain out of scope.

## Contract boundary

The affected tests replace `shoot.SCREENS` with one screen and pass generated setup, prepare, verify, and cleanup expressions through a CDP double. These tests cover orchestration order and cleanup; they do not execute the expression bodies.

Key-specific expression semantics remain covered by the persistent Node screenshot scenarios and direct generator tests. Family-specific Companion, Wanderer, Fleet, and Fittings behavior remains covered by their semantic matrices. Therefore equivalence is based on the observable `walk()` branch crossed, not the screen label.

The PR changes no:

- screenshot inventory, screen key, route, section, or fixture payload;
- generated setup, preparation, verification, or cleanup expression;
- JavaScript fixture or production source;
- persistent-worker protocol or isolation contract;
- workflow, dependency, marker, budget, shard, packaging, or production behavior.

## Consolidations

### Current-owner walk: 60 to 12

`test_current_walk_prepares_before_entry_and_always_cleans` currently crosses ten synthetic-owner keys with six outcomes: success and injected failure at prepare, entry, stage, verify, or capture.

Retain all six outcomes for two representatives:

- `settings-companions-populated` — ordinary viewport and early-owner path;
- `settings-fleet-sharing-history-narrow` — floor viewport and Fleet's paired cleanup expression.

Removed Companion and Wanderer cases map, by the same failure phase, to `settings-companions-populated`. Removed Fleet cases map, by the same failure phase, to `settings-fleet-sharing-history-narrow`.

The retained pair covers the two `walk()` viewport branches and samples two cleanup-expression families. Node scenarios continue to cover all ten visual targets and each owner's executable behavior.

### Gap walk: 5 to 3

`test_gap_capture_walk_settles_then_verifies_and_reports_fixture` has three observable fixture/orchestration classes. Retain one representative per class:

- `settings-wanderer-controls-narrow` — tool fixture and floor viewport;
- `profiles-copy-scope` — live capability with no synthetic fixture or cleanup;
- `fittings-copy-preflight-bottom-narrow` — Fittings fixture, reset, staging, verification, floor viewport, and cleanup.

Map these removed cases to `fittings-copy-preflight-bottom-narrow`:

- `fittings-metadata-narrow`;
- `fittings-copy-result-bottom-narrow`.

Their distinct semantic postconditions remain in the generated gap-verifier matrix.

### Failed postcondition walk: 6 to 2

`test_walk_refuses_capture_when_postcondition_fails` covers two orchestration classes: generic verify-before-capture and the same contract with Fittings cleanup.

Retain:

- `fittings-copy-progress` — Fittings cleanup path;
- `settings-previews-groups` — non-Fittings path.

Map:

- `fittings-detail`, `fittings-copy-result`, and `fittings-copy-limit` to `fittings-copy-progress`;
- `settings-characters-partial-cleanup` to `settings-previews-groups`.

Each removed key's verifier failure modes remain covered by its Node fidelity tests.

## Identity and count contract

Keep ordinary parametrized identities; do not replace them with aggregate loops or new synthetic IDs.

Expected counts:

| File | Before | After |
|---|---:|---:|
| `tests/test_shoot_screens.py` | 246 | 240 |
| `tests/test_new_screenshots.py` | 90 | 90 |
| `tests/test_current_screenshots.py` | 160 | 112 |
| `tests/test_fittings_page.py` | 101 | 101 |
| **Total** | **597** | **543** |

The implementation results must publish the exact 54 removed IDs and retained representative for each, plus before/after node lists and normalized hashes.

## Mutation evidence

Before deleting cases, apply temporary, uncommitted mutations to `scripts/shoot_screens.py`. Revert each mutation before the next probe and before any commit.

The retained set must detect:

1. current-owner preparation moved after section entry;
2. cleanup executed only after successful capture;
3. verification moved after screenshot capture;
4. floor viewport override or restoration removed or misordered;
5. tool, no-fixture, and Fittings fixture attribution confused.

Each witness must fail at the intended assertion. A later or unrelated failure does not establish sensitivity. Mutation code and witness-only test changes must not remain in the branch.

## Implementation shape

Committed behavior changes are limited to parameter selection in:

- `tests/test_current_screenshots.py`;
- `tests/test_shoot_screens.py`.

Add a results document for mappings, mutation outcomes, inventories, verification, and hosted evidence. Do not modify `scripts/shoot_screens.py`, `.cjs` fixtures, production code, or workflow/configuration files.

## Verification

Local verification must include:

- exact target collection `240 / 90 / 112 / 101 = 543` with unique IDs;
- affected tests in normal, reverse, and deterministic shuffled order;
- unchanged worker protocol/isolation and lifecycle suites;
- full pytest with Node and the built release settings codec, with platform skips inspected;
- executable JS smoke and Node DOM tests;
- independent settings-codec Cargo test;
- Ruff check and format check;
- exact path allowlist, `git diff --check`, and no residual mutation.

Hosted verification must include successful checks, Ubuntu, and Windows jobs; downloaded JUnit/timing artifacts; matching Windows and Ubuntu target identities; expected platform skip inventory; affected two-file and four-file testcase sums compared with PR #280's hosted executable run.

Hosted duration may be reported only as measured evidence. A failed, anomalous, or incomparable run is inconclusive, and this stage makes no overall wall-clock or critical-path improvement claim.

## Follow-up boundary

This PR does not authorize later stages automatically. After hosted evidence and review, separate PRs may address:

1. current-owner key-by-lifecycle crossings;
2. shared generated-verifier and Alerts geometry products;
3. lower Fittings context crossings, only with branch-specific mutation evidence.
