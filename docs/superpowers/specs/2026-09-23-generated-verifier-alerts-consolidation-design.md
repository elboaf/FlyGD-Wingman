# Generated-verifier and Alerts consolidation — Stage 3 design

## Status

Approved design. Implementation requires a separate reviewed plan and must pass
the pre-implementation mutation qualification gate below.

## Purpose

Consolidate two screenshot-test products that cross shared failure mechanisms
with every owner even though the observable contract is supplied by the owner
and mechanism dimensions together:

1. the 35-case generated gap-verifier product — five owner keys crossed with
   `settled`, `missing`, `hidden`, `wrong-text`, `clipped`, `covered`, and
   `zero-area`;
2. the 31-case Alerts top-anchor product — 15 base states, eight
   visibility/absence states, and eight clipped-edge states.

The revised candidate is deliberately broader than a greedy minimum. Its
19 generated cases retain successful, absent-anchor, and exact-text evidence for
every owner, then consolidate only the shared hidden and geometry products. Its
24 Alerts cases retain all base states, both anchors, every visibility mode, and
every geometry edge.

This is the third staged PR in screenshot matrix-consolidation Plan B. It does
not authorize lower Fittings consolidation, workflow changes, cadence changes,
budgets, sharding, dependencies, or any overall-runtime claim.

## Authority and baseline

- Source baseline: merged PR #286, commit
  `8d5b9305` (`Consolidate current-owner lifecycle tests (#286)`).
- Design authority: `docs/ci-test-budget-redesign.md`.
- Stage 3 authorization and hosted comparator record:
  `docs/ci-current-owner-lifecycle-consolidation-results.md`.
- Stage 1 boundary:
  `docs/superpowers/specs/2026-09-22-screenshot-walk-consolidation-design.md`.
- Current local full-suite baseline: 16,611 passed and 14 intentional
  platform-only skips.
- Current four-file inventory:
  `240 / 90 / 91 / 101 = 522` identities.
- Current four-file normalized SHA-256:
  `07c1e080c24157001c3aa936ac7c26ec6307e9f246973cfb65f92164c31a51e6`.
- Normalization preserves collection order, joins each complete node ID with
  `\n`, and includes a final newline before hashing.

`PRODUCT.md` and `DESIGN.md` do not govern this tranche because it changes no
product behavior or rendered screen. The existing screenshot contracts and CI
redesign documents are the relevant authorities.

## Intended outcome

If and only if the mutation qualification gate validates the approved
candidate:

| Product | Before | Candidate after | Removed |
|---|---:|---:|---:|
| Generated gap verifier | 35 | 19 | 16 |
| Alerts top anchors | 31 | 24 | 7 |
| **Combined** | **66** | **43** | **23** |
| `tests/test_shoot_screens.py` | 240 | 217 | 23 |
| Four screenshot files | 522 | 499 | 23 |

The candidate four-file normalized SHA-256 is
`87147fc38afa59a4645b1212e5afbb71348fdf75d560f1de4958978d182b0610`.
The candidate retained 43-ID product hash is
`9c88e60a59e6b95ed5088c4007057f86dc9395f02b93b549804d12e05ed648d6`.
These are projections from the approved ordered candidate, not count targets:
if required mutation evidence expands the retained set, the implementation
must publish the actual IDs and hashes and explain the evidence-driven
expansion.

Structural Node process starts are expected to change from 35 to 28. The seven
removed Alerts identities each launch the one-shot `screenshot_alerts.cjs`
process. The 16 removed generated identities are requests to the existing
persistent screenshot worker, so they reduce testcase work but do not reduce
process starts.

No Stage 3 speedup, whole-suite speedup, job-duration improvement,
runner-efficiency improvement, or critical-path reduction is claimed. Timing is
observational evidence only.

## Contract boundary

### Generated verifier

`_gap_verify_script()` supplies five independent owner bodies but delegates
shared visibility, text, geometry, and hit-test behavior to
`_framed_content_script()`:

- `settings-wanderer-controls-narrow` — live Wanderer ownership, exact controls
  and explanatory text, password/token safety, and bounded lower framing;
- `profiles-copy-scope` — live codec capability without a fabricated fixture,
  exact healthy/missing-codec guidance, and bounded note framing;
- `fittings-metadata-narrow` — settled named detail, clean metadata editor,
  management ownership, exact labels, and bounded disclosure framing;
- `fittings-copy-preflight-bottom-narrow` — exact conflict review, disabled
  review action, retained title/summary/footer context, and bounded framing;
- `fittings-copy-result-bottom-narrow` — exact terminal row, recovery ordering,
  technical disclosure, retained title/summary/footer context, and bounded
  framing.

The seven scenarios do not make every shared hidden or geometry crossing a
separate product contract. Missing nodes and wrong text are different: each
owner body checks a different exact anchor, so all five missing and all five
wrong-text cases remain. Settled cases are positive controls, not sensitivity
evidence. Hidden and geometry mechanisms retain one representative crossing
each, same-owner missing/wrong-text evidence, and the independent 13-case
shared geometry tolerance matrix.

The following existing tests remain unchanged and continue to own key-specific
semantics:

- `test_gap_capture_walk_settles_then_verifies_and_reports_fixture`;
- `test_profiles_scope_capture_uses_actual_capability_without_overrides`;
- `test_metadata_capture_waits_for_real_detail_without_creating_drafts`;
- `test_lower_copy_capture_rejects_unsettled_or_wrong_outcomes`;
- `test_lower_copy_capture_requires_retained_context_and_footer`;
- `test_lower_result_capture_keeps_recovery_before_pairs_not_sticky`;
- `test_copy_capture_rejects_stale_context_progress_and_technical_details`;
- worker isolation, VM failure, timer cleanup, and order-independence tests;
- `test_gap_geometry_allows_only_one_pixel_rounding_and_still_hit_tests`, whose
  13 identities cover rounding, exact one-pixel acceptance, overflow rejection
  on all four edges, and covered content despite fractional rounding.

### Alerts top anchors

The base Alerts setup is live framing after the existing walk settle wait. It
must:

- prove the active Settings route and Alerts section own the visible pane;
- reset the outer Settings scroller, not the section;
- require the painted master `.check` label and non-empty readiness text;
- reject absent, hidden, zero-area, clipped, outside-viewport, or covered
  anchors;
- perform no bridge call, route/section entry, click, dispatch, preference
  change, disclosure change, ownership change, or anchor scroll.

The 15 base states are distinct route, section, ownership, content,
zero-area, viewport, and success observables. They remain intact. The
visibility and clipped products are consolidated pairwise across the master and
health anchors without deleting either missing short circuit, any visibility
mechanism, or any edge comparison.

## Candidate retained generated matrix — 19 cases

Retain all five successful verifiers in `GAP_CAPTURES` order:

1. `settled-settings-wanderer-controls-narrow`;
2. `settled-profiles-copy-scope`;
3. `settled-fittings-metadata-narrow`;
4. `settled-fittings-copy-preflight-bottom-narrow`;
5. `settled-fittings-copy-result-bottom-narrow`.

Retain absence and exact-text sensitivity for every owner:

| Owner | Missing anchor | Wrong-text anchor |
|---|---|---|
| Wanderer controls | `missing-settings-wanderer-controls-narrow` | `wrong-text-settings-wanderer-controls-narrow` |
| Profiles copy scope | `missing-profiles-copy-scope` | `wrong-text-profiles-copy-scope` |
| Fittings metadata | `missing-fittings-metadata-narrow` | `wrong-text-fittings-metadata-narrow` |
| Fittings preflight bottom | `missing-fittings-copy-preflight-bottom-narrow` | `wrong-text-fittings-copy-preflight-bottom-narrow` |
| Fittings result bottom | `missing-fittings-copy-result-bottom-narrow` | `wrong-text-fittings-copy-result-bottom-narrow` |

Retain one representative for each consolidated shared mechanism:

- `hidden-profiles-copy-scope`;
- `clipped-fittings-copy-preflight-bottom-narrow`;
- `covered-fittings-copy-result-bottom-narrow`;
- `zero-area-settings-wanderer-controls-narrow`.

Settled cases prove success only. The ten owner-specific missing/wrong-text
cases prove fail-closed target-anchor guards. The four representatives prove
shared hidden and geometry branches.

### Complete generated removed-to-retained mapping

Every removed identity maps to same-owner semantic evidence and independent
shared-helper evidence. Neither dimension alone is sufficient. The owner labels
below resolve to the complete retained IDs in the table immediately above; they
are exact cases, not family-level claims.

| Removed identity | Same-owner/same-anchor semantic evidence | Shared production/helper evidence |
|---|---|---|
| `hidden-settings-wanderer-controls-narrow` | Wanderer `missing` and `wrong-text` | `hidden-profiles-copy-scope`; remove `parent.hidden` rejection |
| `hidden-fittings-metadata-narrow` | Metadata `missing` and `wrong-text` | `hidden-profiles-copy-scope`; remove `parent.hidden` rejection |
| `hidden-fittings-copy-preflight-bottom-narrow` | Preflight `missing` and `wrong-text` | `hidden-profiles-copy-scope`; remove `parent.hidden` rejection |
| `hidden-fittings-copy-result-bottom-narrow` | Result `missing` and `wrong-text` | `hidden-profiles-copy-scope`; remove `parent.hidden` rejection |
| `clipped-settings-wanderer-controls-narrow` | Wanderer `missing` and `wrong-text` | `clipped-fittings-copy-preflight-bottom-narrow` plus four-edge/tolerance matrix |
| `clipped-profiles-copy-scope` | Profiles `missing` and `wrong-text` | `clipped-fittings-copy-preflight-bottom-narrow` plus four-edge/tolerance matrix |
| `clipped-fittings-metadata-narrow` | Metadata `missing` and `wrong-text` | `clipped-fittings-copy-preflight-bottom-narrow` plus four-edge/tolerance matrix |
| `clipped-fittings-copy-result-bottom-narrow` | Result `missing` and `wrong-text` | `clipped-fittings-copy-preflight-bottom-narrow` plus four-edge/tolerance matrix |
| `covered-settings-wanderer-controls-narrow` | Wanderer `missing` and `wrong-text` | `covered-fittings-copy-result-bottom-narrow` plus five-point hit-test mutants |
| `covered-profiles-copy-scope` | Profiles `missing` and `wrong-text` | `covered-fittings-copy-result-bottom-narrow` plus five-point hit-test mutants |
| `covered-fittings-metadata-narrow` | Metadata `missing` and `wrong-text` | `covered-fittings-copy-result-bottom-narrow` plus five-point hit-test mutants |
| `covered-fittings-copy-preflight-bottom-narrow` | Preflight `missing` and `wrong-text` | `covered-fittings-copy-result-bottom-narrow` plus five-point hit-test mutants |
| `zero-area-profiles-copy-scope` | Profiles `missing` and `wrong-text` | `zero-area-settings-wanderer-controls-narrow`; remove width/height rejection independently |
| `zero-area-fittings-metadata-narrow` | Metadata `missing` and `wrong-text` | `zero-area-settings-wanderer-controls-narrow`; remove width/height rejection independently |
| `zero-area-fittings-copy-preflight-bottom-narrow` | Preflight `missing` and `wrong-text` | `zero-area-settings-wanderer-controls-narrow`; remove width/height rejection independently |
| `zero-area-fittings-copy-result-bottom-narrow` | Result `missing` and `wrong-text` | `zero-area-settings-wanderer-controls-narrow`; remove width/height rejection independently |

## Candidate retained Alerts matrix — 24 cases

### All 15 base states remain

1. `settled-disabled`;
2. `settled-enabled`;
3. `wrong-route`;
4. `wrong-section`;
5. `inactive-route`;
6. `inactive-section`;
7. `missing-section`;
8. `missing-pane`;
9. `hidden-section`;
10. `hidden-pane`;
11. `hidden-card`;
12. `wrong-owner`;
13. `empty-health`;
14. `zero-health`;
15. `outside-viewport`.

These states continue to own action-free staging, ownership, scroll reset,
preference preservation, disclosure preservation, health content, positive
area, and viewport behavior.

### Missing short circuits remain distinct

- `missing-master`;
- `missing-health`.

The production setup has separate master and health guards. Neither may be
mapped solely to the other.

### Absence/visibility product reduces from eight to five

The two missing cases remain above. The six-case visibility-only subproduct
reduces to three. Retain:

- `hidden-master` — `hidden` attribute mechanism and master owner;
- `invisible-health` — computed `visibility: hidden` mechanism and health
  owner;
- `display-none-master` — no-client-rect/display-none mechanism and master
  owner.

Together these retain all three visibility mechanisms and represent both
anchors.

### Clipped product reduces from eight to four

Retain one exact edge branch each while pairing owners:

- `clipped-master-top`;
- `clipped-master-right`;
- `clipped-health-bottom`;
- `clipped-health-left`.

Together these retain all four comparisons and both anchors.

### Complete Alerts removed-to-retained mapping

| Removed identity | Owner witness | Mechanism/edge witness |
|---|---|---|
| `hidden-health` | `invisible-health` and `missing-health` | `hidden-master` |
| `invisible-master` | `hidden-master` and `display-none-master` | `invisible-health` |
| `display-none-health` | `invisible-health` and `missing-health` | `display-none-master` |
| `clipped-master-bottom` | `clipped-master-top` and `clipped-master-right` | `clipped-health-bottom` |
| `clipped-master-left` | `clipped-master-top` and `clipped-master-right` | `clipped-health-left` |
| `clipped-health-top` | `clipped-health-bottom` and `clipped-health-left` | `clipped-master-top` |
| `clipped-health-right` | `clipped-health-bottom` and `clipped-health-left` | `clipped-master-right` |

## Mutation qualification gate

The 43-case candidate is conditional. Mutation evidence may expand the retained
set; it may never weaken a production, helper, harness, assertion, or fixture
contract merely to reach 43 cases or 499 four-file identities.

All mutations are temporary and uncommitted. Restore and diff-audit the mutated
path after every probe and before every commit. No witness-only test,
production, helper, or fixture change may survive.

Every mutation must fail at the intended assertion. A later cleanup failure,
protocol failure, unrelated semantic assertion, timeout, process crash, or
changed error message without the intended boundary failure is not evidence.

### Generated branch-level mutation ledger

Settled cases are positive controls and do not qualify sensitivity. For every
owner, mutate the narrow production predicate for the exact anchor exercised by
the retained `missing` and `wrong-text` cases:

| Owner body | Exact anchor/predicate | Required retained witnesses |
|---|---|---|
| Wanderer controls | `wanderer-remove` existence and `text(remove, 'Remove connection')` | same-owner `missing` and `wrong-text` |
| Profiles copy scope | `es-copy-scope-note` existence/visibility and exact healthy guidance | same-owner `missing` and `wrong-text` |
| Fittings metadata | metadata Save existence and `text(save, 'Save')` | same-owner `missing` and `wrong-text` |
| Fittings preflight bottom | resolution-note existence and exact conflict guidance | same-owner `missing` and `wrong-text` |
| Fittings result bottom | terminal result existence and exact status-text predicate | same-owner `missing` and `wrong-text` |

Each production mutant removes or weakens one named predicate only. Its retained
same-owner, same-anchor case must fail at the intended assertion. An unchanged
dedicated test may substitute only when it corrupts that exact anchor and kills
the explicit guard mutant; name that test and assertion in the results. A broad
owner mutation, a settled case, another owner's negative, or a fixture-only
failure is not sensitivity evidence.

For every removed generated identity, the implementation results must include a
ledger row naming:

1. the explicit owner predicate mutant and retained same-owner/same-anchor
   `missing` or `wrong-text` witness, or the exact unchanged dedicated test that
   corrupts that anchor;
2. the production/helper branch mutant for hidden, clipped, covered, or
   zero-area behavior and its retained shared-mechanism witness;
3. the intended assertion and source-restoration proof.

All missing and wrong-text cases remain unless an unchanged same-anchor test
kills the explicit narrow predicate mutant. Such evidence may justify a later
design revision; it does not permit an implementation-time deletion from this
approved candidate.

Fixture-dispatch mutants may additionally prove that harness inputs are wired,
but they never qualify production sensitivity. No removed identity may be
justified circularly by disabling only the fixture behavior that creates it.

### Consolidated generated production branches

Qualify each consolidated mechanism with narrow production/helper mutants:

- hidden — remove only `parent.hidden` rejection from `visible()`;
  `hidden-profiles-copy-scope` must fail at that helper branch;
- clipped — weaken top, bottom, left, and right comparisons independently and
  change the one-pixel tolerance independently; the retained clipped preflight
  case and the 13-case geometry matrix must catch the exact branch;
- covered — weaken the five-point `.every(...)` requirement, null-hit refusal,
  direct-node equality, and descendant `contains` handling independently; the
  retained covered result case and point-specific geometry probes must catch
  the exact branch;
- zero area — remove `r.width <= 0` and `r.height <= 0` independently;
  `zero-area-settings-wanderer-controls-narrow`, with a narrowly supplied
  zero-height input where needed, must catch each production branch.

Fixture changes may only supply temporary branch-specific inputs. They do not
replace any production/helper mutant or survive the probe.

### Shared framed-content helper

The candidate plus the unchanged 13-case shared geometry matrix must establish
sensitivity for every helper dimension:

- positive width and height;
- top, bottom, left, and right containment comparisons;
- exact one-CSS-pixel tolerance versus `1.01` overflow;
- all five hit-test points rather than partial exposure;
- covered-point rejection;
- descendant hits accepted through `node.contains(hit)` while unrelated hits
  are rejected.

Use temporary production/helper mutations for every dimension. Where a
particular point, descendant, or zero-height input is otherwise not isolated, a
narrow fixture-dispatch mutant may supply that input only alongside the exact
production/helper mutant; it cannot qualify the branch by itself. Each
production mutant must be caught by the intended retained generated case or the
existing 13-case matrix. If any dimension cannot be attributed to an intended
assertion, stop and expand the test design before deleting identities.

### Alerts owner guards

Weaken the master and health production guards independently. The corresponding
retained owner evidence must fail at the guard-specific assertion. In
particular, both `missing-master` and `missing-health` remain because the two
short circuits are independent.

### Alerts visibility mechanisms

Mutate production `_framed_content_script()` independently for each visibility
branch:

- remove `parent.hidden` rejection — `hidden-master` must fail at that helper
  branch;
- remove computed `visibility === 'hidden'` rejection — `invisible-health` must
  fail at that helper branch;
- remove the `getClientRects().length` rejection — `display-none-master` must
  fail at that helper branch.

Fixture-dispatch mutants may additionally prove that `screenshot_alerts.cjs`
creates each input, but they cannot qualify production sensitivity. A fixture
failure, generic later failure, or another visibility branch is insufficient.

### Alerts edge comparisons

Weaken each helper comparison independently:

- top — caught by `clipped-master-top`;
- right — caught by `clipped-master-right`;
- bottom — caught by `clipped-health-bottom`;
- left — caught by `clipped-health-left`.

Each retained case must fail on the exact branch it owns. Owner pairing is not a
substitute for branch attribution.

### Alerts invariants that do not shrink

All 15 base states and the existing walk tests continue to prove:

- action-free staging;
- route, section, and pane ownership;
- outer Settings scroll reset and section-scroll preservation;
- preference and Advanced disclosure preservation;
- no anchor `scrollIntoView`;
- setup-before-capture ordering and fail-closed walk behavior.

Mutation evidence must not move these contracts into the reduced products or
weaken their assertions.

## Parameter derivation and identity order

Committed test changes are parameter derivation only.

For the generated matrix, parameterize `(scenario, key)` together from:

1. `settled` for all five `GAP_CAPTURES` keys in existing mapping order;
2. `missing` for all five keys in the same order;
3. `wrong-text` for all five keys in the same order;
4. the four shared-mechanism representatives in the order `hidden`, `clipped`,
   `covered`, `zero-area`.

Preserve pytest ID spelling as `scenario-key`. Do not create aggregate loop
identities or hand-copy all five settled pairs.

For Alerts, derive the scenario sequence from three named groups:

1. the unchanged 15-state base sequence;
2. `missing-master`, `missing-health`, then the three retained visibility cases;
3. the four retained clipped cases in top, right, bottom, left ownership order.

Preserve the existing test function and scenario IDs. The implementation may
name local constants to make products and boundaries reviewable, but it must not
change scenario semantics or introduce replacement synthetic IDs.

## Implementation scope

Committed executable changes are limited to parameter derivation in:

- `tests/test_shoot_screens.py`.

The implementation PR may also add or update only its Stage 3 design, execution
plan, and results documentation.

Explicitly forbidden without a new design review:

- `scripts/shoot_screens.py`;
- `tests/fixtures/screenshot_pages.cjs`;
- `tests/fixtures/screenshot_alerts.cjs`;
- any production file under `wingman/`;
- other test modules;
- workflows, configuration, dependencies, lockfiles, packaging, markers,
  budgets, or shard manifests.

If mutation evidence requires persistent fixture or test-support changes, stop
for redesign rather than broadening scope silently.

## Inventory and local verification requirements

Before deletion, freeze and publish the complete normalized 522-ID baseline and
its hash. After implementation, publish the complete normalized after inventory,
its hash, the retained 43-ID product inventory and hash, and an exact set diff.
For the approved candidate, acceptance is:

- `217 / 90 / 91 / 101 = 499` unique four-file IDs;
- exactly 23 removed IDs;
- zero added IDs;
- all 23 removals present in the mapping tables above;
- candidate four-file hash
  `87147fc38afa59a4645b1212e5afbb71348fdf75d560f1de4958978d182b0610`;
- candidate retained-product hash
  `9c88e60a59e6b95ed5088c4007057f86dc9395f02b93b549804d12e05ed648d6`.

If mutation evidence expands the candidate, recalculate and publish the actual
counts, complete inventories, hashes, exact removals, and zero-addition proof.
Do not preserve the projected count or hash by dropping a different case.

Run the four target files in five orders:

1. normal file order;
2. reverse file order while preserving collection order within each file;
3. explicit forward node order;
4. explicit reverse node order;
5. deterministic shuffled node order using integer seed `0x8d5b9305`.

Record each exact node-order hash and result. Explicit-node commands must pass
each node as a distinct argument.

Local verification must also include:

- focused generated, shared-geometry, Alerts, walk, worker-protocol, and
  isolation tests;
- the complete four-file run with JUnit and timing evidence;
- full pytest with Node available and the built release settings codec installed;
- complete skip inspection, rejecting any Node or codec availability skip;
- `node scripts/js_smoke.js`;
- `node --test tests/fixtures/screenshot_dom.test.cjs`;
- `cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml`;
- Ruff check and Ruff format check;
- `git diff --check`;
- exact changed-path allowlist and protected-path audit;
- proof that every temporary mutant was restored and no witness-only change
  remains.

The full-suite projection for the unexpanded candidate is 16,588 passed with the
same 14 intentional local platform skips, or 16,602 JUnit cases including those
skips. These are identity projections to audit, not permission to ignore an
unexpected collection change.

## Hosted comparator and acceptance evidence

Use PR #286 executable run
[`35882408360`](https://github.com/elboaf/FlyGD-Wingman/actions/runs/35882408360)
as the exact hosted comparator. Its provenance is:

- branch head `0c785ce18193b5900f8d810a8a4dc7e0f10c9f1e`;
- synthetic merge `c1ab289e4fdd31e7cc5be2c8322a2557c48e1a26`;
- base `459c5d6b57f5f35c97d3076bee25a6f65ba515be`;
- checks job `107253913132`;
- Ubuntu job `107253913433`;
- Windows job `107253913529`;
- downloaded Windows and Ubuntu artifacts containing `pytest-result.xml` and
  `pytest-timing.json`, recorded in the Stage 2 results document as
  `/tmp/wingman-pr286-{windows,ubuntu}`.

For the Stage 3 PR, record the exact branch head, synthetic merge, base, run,
job IDs, checkout provenance, and downloaded artifact paths. Parse Windows and
Ubuntu JUnit and timing artifacts directly and require:

- all required jobs pass;
- Windows and Ubuntu full testcase identity sets are equal;
- both target sets equal the published after inventory;
- exact target counts match the qualified candidate, expected
  `217 / 90 / 91 / 101 = 499` if unexpanded;
- relative to PR #286, exactly the published removals are absent and no identity
  is added;
- Windows and Ubuntu normalized skip tuples match the comparator exactly;
- no failure, error, or availability skip appears;
- per-file, combined-product, four-file target, and all-case testcase sums are
  reported;
- removed-ID and common-retained-ID sums are decomposed where artifacts permit;
- job duration and pytest Test-step duration are reported as observations.

Comparator workflow and unchanged target-path blobs must be audited so timing
comparisons are bounded to the authorized test selection. Hosted evidence may
support “no unexplained material target regression.” It may not support a Stage
3 or overall speedup claim from one run.

## Alternatives rejected

### Alerts-only consolidation

Rejected as too timid. It removes seven one-shot launches but leaves all 16
removable generated hidden/geometry crossings intact. Same-owner missing and
wrong-text cases preserve owner semantics while the shared helper and geometry
matrix qualify those 16 removals.

### Greedy mutant set-cover

Rejected as brittle. A mathematically smaller set can overfit the exact temporary
mutants, obscure owner/mechanism review, and lose resilience to harmless helper
refactors. The approved matrix intentionally retains all owner successes, every
owner's missing and exact-text failures, every shared mechanism, all 15 Alerts
base states, both missing short circuits, every visibility mode, both anchors,
and every edge.

### Raw deletion or count target

Rejected. `66 -> 43`, `240 -> 217`, and `522 -> 499` are consequences of the
qualified contract matrix, not goals that justify deleting a different case or
weakening an assertion. Mutation evidence may only expand the retained set.

## Risks and blind spots

### A shared helper mutant can be killed for the wrong reason

A later owner assertion may fail after the intended visibility or geometry guard
has already been bypassed. Require the exact intended assertion and inspect the
failure location/message, not merely a red test.

### Fixture dispatch can masquerade as production sensitivity

Some scenarios are harness-created inputs. Disabling the dispatch proves the
scenario is wired, not that the production helper rejects it. Production/helper
mutants are mandatory; fixture-input mutants are supplemental and must be
labelled separately.

### Two-dimensional mapping can hide owner-specific coupling

An owner body may accidentally rely on a generic helper in a way another owner
does not. Retain every same-owner missing and wrong-text case, mutate each exact
anchor predicate independently, and stop if that case or an unchanged
same-anchor dedicated test does not kill the defect. Settled success is not a
substitute.

### Five-point hit testing is easy to under-prove

A blanket covered scenario can remain red even if one point is removed. Use
narrow temporary point-specific fixture inputs and helper mutations to prove the
all-points and descendant contracts rather than inferring them from one covered
case.

### Alerts visibility mechanisms differ in the DOM double

`hidden`, computed visibility, and display-none/no-client-rect behavior use
different fixture paths. Retain each input and mutate each corresponding
production-helper branch independently; do not collapse them because all
eventually make `visible()` false.

The DOM double may make `hidden` also remove client rects, masking the separate
`parent.hidden` branch. The production mutant must still be killed without
counting a fixture-only change as sensitivity. If the retained case cannot
isolate that branch, stop for redesign; do not claim the fixture wiring as a
production witness or persist a fixture workaround.

### Hosted process and timing effects may be noisy

Generated removals do not reduce persistent-worker starts, while Alerts removals
do. Report starts and testcase sums structurally, but treat hosted durations as
runner observations. One run cannot establish a speedup.

### Conditional evidence can pressure scope expansion

A surviving mutant may tempt a persistent fixture helper or tooling change.
That is a design change, not a routine witness adjustment. Stop and redesign
instead of modifying authorized fixtures or `scripts/shoot_screens.py`.

## Stopping rules

Stop implementation and return to design review if any of these occurs:

1. a generated exact-anchor predicate cannot be killed by its retained
   same-owner missing/wrong-text case or an unchanged same-anchor dedicated
   contract;
2. a generic mechanism or shared-helper dimension lacks an intended-assertion
   witness;
3. either Alerts guard, any visibility mechanism, or any edge comparison lacks
   an exact retained witness;
4. qualification requires a persistent fixture, tooling, production, workflow,
   configuration, dependency, or additional test-module change;
5. the exact identity diff includes an addition or an unmapped removal;
6. any of the 15 Alerts base states, both missing short circuits, the 13-case
   geometry matrix, or existing walk/ownership/action-free tests would need to
   shrink;
7. Node, codec, native, or platform skip behavior changes;
8. hosted Windows and Ubuntu identities or normalized skips diverge;
9. evidence suggests lower Fittings, workflow, budget, or sharding work is
   needed to complete this tranche.

An evidence-driven retained-case expansion within `tests/test_shoot_screens.py`
is permitted and must be documented. Any broader support change is not.

## Required implementation self-review

Before publication, the implementation results must record a final self-review
covering:

- placeholder scan — no `TODO`, `TBD`, `PENDING`, ellipsis placeholder, or
  witness-only note remains in changed paths;
- arithmetic consistency — matrix, file, four-file, full-suite, removal, and
  process-start counts reconcile;
- identity consistency — published inventories, hashes, mappings, JUnit sets,
  and platform comparisons agree;
- mutation consistency — every mutant names its intended witness and restoration
  proof;
- scope consistency — committed executable changes are parameter derivation in
  `tests/test_shoot_screens.py` only, plus approved design/plan/results docs;
- protected-path audit — no script, fixture, production, workflow,
  configuration, dependency, packaging, marker, budget, or shard change;
- claim discipline — timing is observational and no Stage 3 or overall speedup
  is claimed;
- staged boundary — Stage 4 lower Fittings work and all workflow, budget, and
  sharding work remain STOP.

## Follow-up boundary

Successful Stage 3 hosted evidence may authorize review of a separate later
tranche; it does not authorize one automatically.

Stage 4 lower Fittings context consolidation remains STOP pending independent
branch-specific mutation evidence and a separate approved design. Workflow
selection, cadence, budgets, sharding, dependencies, and overall-runtime claims
also remain STOP.
