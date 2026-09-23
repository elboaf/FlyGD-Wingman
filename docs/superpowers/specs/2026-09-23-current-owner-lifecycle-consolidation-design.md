# Current-owner lifecycle matrix consolidation — Stage 2 design

## Purpose

Consolidate duplicate key-by-lifecycle crossings in `test_current_synthetic_owners` while preserving every distinct visual target and independently proving the four production screenshot-owner boundaries.

This is the second staged PR in screenshot matrix-consolidation Plan B. Stage 1 authorized this separate current-owner lifecycle tranche; it did not authorize workflow, budget, sharding, overall-runtime, or later matrix changes.

## Authority and baseline

- Source baseline: merged PR #285, commit `459c5d6b57f5f35c97d3076bee25a6f65ba515be`.
- Design authority: `docs/ci-test-budget-redesign.md`.
- Stage 2 authorization: `docs/ci-screenshot-walk-consolidation-results.md`.
- Current synthetic-owner matrix: ten keys crossed with four scenarios, producing 40 identities.
- Current four-file screenshot inventory: `240 / 90 / 112 / 101 = 543` identities.

## Contract boundary

The current matrix combines two dimensions:

1. ten key-specific visual targets, setup expressions, and verifiers;
2. four shared lifecycle scenarios: `normal`, `late-read`, `late-synthetic`, and `invalid`.

Every `normal` identity remains because the ten keys stage and verify different content. The three special scenarios are retained once per presentation family because their harness machinery is family-owned rather than key-owned.

There are three presentation families but four independent production owners:

- `WM.companionsScreenshot`;
- `WM.wandererScreenshot`;
- `WM.fleetScreenshot`;
- `WM.fleetSharingScreenshot`.

Fleet remains one retained test identity per special scenario because every Fleet request installs, validates, observes, and cleans both Fleet owners. Mutation evidence must nevertheless break Fleet display and Fleet sharing independently.

The PR changes no:

- production JavaScript owner or public interface;
- Node fixture, generated setup, preparation, verification, or cleanup expression;
- screen inventory, route, section, geometry, fixture payload, or screenshot key;
- persistent-worker protocol or isolation contract;
- workflow, dependency, packaging, marker, budget, shard, or runtime behavior.

All other current-owner cold cleanup, live-dialog, lifecycle, refresh-authority, binding-fence, pending-action, focus, and cross-family isolation tests remain unchanged.

## Retained identities

Retain `normal` for all ten keys in `SYNTHETIC`.

For each special scenario—`late-read`, `late-synthetic`, and `invalid`—retain:

| Family | Representative | Reason |
|---|---|---|
| Companions | `settings-companions-source-narrow` | Strongest Companion path and the only key that creates a real delayed synthetic continuation through the fixture source chooser. |
| Wanderer | `settings-wanderer` | Full ordinary-viewport card; narrow framing remains covered by its retained `normal` identity. |
| Fleet | `settings-fleet-sharing` | Directly frames sharing while every Fleet request exercises both display and sharing owners. |

## Exact removed-to-retained mapping

For each of `late-read`, `late-synthetic`, and `invalid`, map:

| Removed key | Retained key |
|---|---|
| `settings-companions-populated` | `settings-companions-source-narrow` |
| `settings-companions-detail-narrow` | `settings-companions-source-narrow` |
| `settings-companions-add` | `settings-companions-source-narrow` |
| `settings-wanderer-narrow` | `settings-wanderer` |
| `settings-fleet-characters-narrow` | `settings-fleet-sharing` |
| `settings-fleet-sharing-details` | `settings-fleet-sharing` |
| `settings-fleet-sharing-history-narrow` | `settings-fleet-sharing` |

This removes seven identities per special scenario, exactly 21 total, and adds none.

## Late-synthetic limitation

Only `settings-companions-source-narrow` currently creates real pending synthetic work: its fixture source chooser follows a `Promise.resolve(...)` path that can complete after cleanup.

Wanderer, Fleet display, and Fleet sharing have no equivalent fixture-owned delayed continuation. Their retained `late-synthetic` identities preserve the current stage-cleanup-idempotence behavior, but they do not prove delayed asynchronous revocation. Retaining more Wanderer or Fleet keys would repeat the same no-pending-continuation path.

Adding genuine pending synthetic work for those owners would require a separate fixture-design change and is outside this parameter-selection-only tranche.

## Case derivation

Do not hand-maintain ten `normal` pairs. Derive the case sequence from:

- all keys in `SYNTHETIC` for `normal`;
- a three-entry family representative sequence for each special scenario.

Preserve existing pytest ID spelling and order:

1. all ten `normal` IDs in `SYNTHETIC` order;
2. three `late-read` IDs in Companion, Wanderer, Fleet order;
3. three `late-synthetic` IDs in the same order;
4. three `invalid` IDs in the same order.

Parameterize `(scenario, key)` together so generated IDs remain `scenario-key`. Do not introduce aggregate loop tests or custom replacement identities.

## Mutation evidence

Before deleting identities, apply temporary, uncommitted production mutations. Revert each mutation before the next probe and before every commit. Each retained test must fail at the intended assertion rather than at unrelated later cleanup.

### Every independent owner

For Companions, Wanderer, Fleet display, and Fleet sharing separately:

1. **Validator ownership:** disable the owner's malformed-payload guard. The retained family `invalid` identity must fail because its `assert.throws` no longer observes rejection. Fleet display and Fleet sharing require separate mutations against the same Fleet identity.
2. **Fixture isolation:** bypass the owner's effective fixture/read/live fence so held reads or live delivery paints during capture. The retained representative must fail while rechecking synthetic fixture content.
3. **Newest-live restoration:** preserve fixture display but suppress buffering the newest live delivery. Cleanup must restore stale authority and fail the retained lifecycle assertion.

### Companion-only delayed continuation

Disable the source chooser's fixture epoch/request revocation enough for its delayed synthetic result to continue after cleanup. The retained `late-synthetic/settings-companions-source-narrow` identity must fail because the chooser reopens or a bridge call escapes.

Do not claim analogous Wanderer or Fleet delayed-continuation mutation evidence.

Mutation code and witness-only changes must not remain in the branch.

## Identity and count contract

| Inventory | Before | After |
|---|---:|---:|
| Synthetic-owner matrix | 40 | 19 |
| `tests/test_current_screenshots.py` | 112 | 91 |
| Four screenshot target files | 543 | 522 |
| Full local passed-test projection | 16,632 | 16,611 |
| Full JUnit cases with the same 14 skips | 16,646 | 16,625 |

The implementation results must publish:

- complete normalized 543-ID before and 522-ID after lists;
- normalized hashes;
- the exact 21 removed IDs and retained representative for each;
- zero added IDs;
- temporary mutation outcomes and source-restoration proof.

## Implementation shape

Committed executable changes are limited to case derivation and parameter selection in `tests/test_current_screenshots.py`.

Add one results document for mapping, mutation, inventory, local verification, and hosted evidence. The spec and plan are the only other planned paths. Do not modify production JavaScript, `.cjs` fixtures, screenshot tooling, other tests, workflows, or configuration.

## Verification

Local verification must include:

- exact target collection `240 / 90 / 91 / 101 = 522` with unique IDs;
- exact synthetic-owner collection of 19 IDs in the required order;
- exact 21 removals and zero additions;
- normal, reverse-file, forward-node, reverse-node, and deterministic shuffled execution;
- unchanged worker protocol/isolation and lifecycle suites;
- full pytest with Node and built release settings codec, with all skips inspected;
- executable JS smoke and Node DOM tests;
- independent settings-codec Cargo test;
- Ruff check and format check;
- exact changed-path allowlist, `git diff --check`, and no residual mutation.

Hosted verification must include successful checks, Ubuntu, and Windows jobs; downloaded JUnit/timing artifacts; exact Windows/Ubuntu identity equality with the published 522-ID list; expected platform skips; affected-file and four-file testcase sums compared with PR #285; and an explicit Stage 3 stop/go decision.

Hosted timing is measured evidence only. A failed, anomalous, or incomparable run is inconclusive. This stage makes no overall wall-clock, runner-efficiency, or critical-path improvement claim.

## Follow-up boundary

This PR does not authorize later stages automatically. Only reviewed hosted evidence may authorize the separate shared generated-verifier and Alerts geometry tranche. Lower Fittings context consolidation remains later and independently conditional on branch-specific mutation evidence.
