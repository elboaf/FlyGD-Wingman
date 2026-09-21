# CI test budget redesign

## Status

Approved design; implementation requires a separate reviewed plan.

This design supersedes the rollout decisions in
[`ci-test-strategy-design.md`](ci-test-strategy-design.md) where current evidence
or the agreed policy differs. The earlier document and
[`ci-test-strategy-phase-1-results.md`](ci-test-strategy-phase-1-results.md)
remain the historical record of persistent-worker and xdist experiments. This
redesign starts from the suite after Fleet v2, not from the smaller Phase 1
suite.

## Decision

Required pull-request CI has an absolute five-minute critical-path ceiling and a
four-minute operating target. Complete product verification on main, nightly,
and release paths has a ten-minute ceiling.

The primary intervention is contract consolidation: delete equivalent cases and
simplify expensive test architecture before moving tests or adding runners.
Cadence tiers and file-level Windows shards support the budgets; they are not a
substitute for reducing a bloated suite.

## Current evidence

GitHub Actions run
[`35534240008`](https://github.com/elboaf/FlyGD-Wingman/actions/runs/35534240008)
at `78adb17a8346f4810f48863dd10a87c386091948` is the current reference run.
Its Windows job took 20m05s and its pytest step took 18m56s. The uploaded JUnit
summary contains 16,421 cases and 1,100.617 summed testcase seconds.

The regression first appears at Fleet v2 merge
`63d27041a65359c659c844d6304c2c645a584c3e` (PR #256):

- Windows pytest increased from 9m38s to 15m56s.
- Ubuntu pytest increased from 4m44s to 7m10s.
- Setup and codec-build times remained effectively unchanged.
- The merge added 2,816 cases, from 13,560 to 16,376.

Case count alone does not explain cost. Cheap protocol vectors contribute
hundreds of cases in seconds, while a few scenario families dominate runtime.
At the current reference run:

| Scope | Windows case sum | Cases |
|---|---:|---:|
| Five slow Fleet files | 518.8s | 405 |
| Top five files overall | 518.8s | 405 |
| Top ten files | 656.7s | 959 |
| Top twenty files | 825.4s | 1,698 |
| All 324 files | 1,100.6s | 16,421 |

The five initial Fleet targets are:

| File | Windows case sum | Cases | Main cost |
|---|---:|---:|---|
| `test_fleetsharing_cadence.py` | 318.8s | 139 | Long virtual scenarios combined with real signing, codec, and fsynced state writes across Cartesian grids |
| `test_fleetsharing_source_admission.py` | 67.8s | 201 | Repeated signed file-backed worker construction across large products |
| `test_fleetsharing_worker_timing_mutations.py` | 46.8s | 25 | Production mutants that rerun existing long regressions |
| `test_fleetsharing_transport_resources.py` | 44.6s | 3 | A 47 MB, 8,192-row response decoded under Windows `tracemalloc` |
| `test_fleetsharing_worker_revision.py` | 40.7s | 37 | A 260-cycle durable stress case and a mutant that reruns it |

Even deleting all five files would leave about 582 summed seconds. The redesign
therefore requires both an initial Fleet tranche and a measured pass over the
remaining expensive files.

## Goals

1. Establish required PR critical-path p95 at or below 300 seconds, with a
   240-second operating target.
2. Establish complete Windows product verification at or below 600 seconds.
3. Reduce the complete suite, not merely hide its cost behind tiers or runners.
4. Preserve distinct user workflow, trust-boundary, concurrency, persistence,
   platform, and historical regression contracts.
5. Keep actual Windows-native, Node, and release-codec integration mandatory.
6. Make future runtime growth visible and enforceable before another large merge.

## Non-goals

- A test-count quota or line/branch coverage target.
- Removing Windows verification from a Windows-only product.
- Treating Linux mocks as substitutes for Win32, DPAPI, filesystem, or codec
  behavior.
- Adopting pytest-xdist. Phase 1 did not establish sufficient reliability.
- Weakening production limits to make boundary tests cheaper.
- Replacing manual WebView2, installed-build, DPI, clipboard, or accessibility
  checks with pytest doubles.
- Keeping mutation-of-test checks on release paths merely so the release suite
  can be called exhaustive.

## Verification contracts

A retained case must protect at least one observable contract:

1. **User workflow** — a visible operation succeeds, refuses safely, or recovers
   predictably.
2. **Trust boundary** — malformed or hostile filesystem, network, OAuth, update,
   setup-import, or bridge input is rejected without unsafe effects.
3. **Ownership and concurrency** — stale, cancelled, detached, or duplicate work
   cannot overwrite newer authority or outlive shutdown incorrectly.
4. **Persistence** — acknowledged state, crash intent, migration, rollback, or
   atomic publication behaves as promised.
5. **Platform integration** — the actual Windows, codec, Node, filesystem, or
   packaging seam works.
6. **Source-shape invariant** — exact spelling or placement is load-bearing and
   cannot be proved through ordinary executable behavior.
7. **Historical regression** — the case uniquely owns a prior incident not
   already represented by an equivalent contract.

A case protecting none of these is deleted. Multiple cases protecting the same
contract through equivalent observables are consolidated.

## Observable equivalence

Cases are equivalent when they share all of these dimensions:

- public entry point;
- normalized result or error;
- persisted and externally visible effects;
- authority or state transition;
- trust-boundary class;
- platform and encoding semantics;
- historical incident ownership.

Different scalar values, fixture names, internal branches, or parameter labels
do not establish distinct contracts. Production branch count may guide review,
but it is not the definition of equivalence.

## Consolidation rules

### Parameter matrices

- Retain minimum, maximum, threshold or equality, one-beyond, and one
  representative interior value where they produce meaningful boundaries.
- Use pairwise combinations by default. Retain a three-way or full Cartesian
  interaction only when it changes an observable contract or owns a prior
  regression.
- A required matrix larger than twelve cases needs an explicit contract table
  explaining why each interaction matters.
- Do not preserve every spelling or every field × malformed-scalar crossing when
  normalization and effects are equivalent.

### Timing, persistence, and concurrency

- Virtual scheduler permutations do not all need real signing, codec work, and
  fsynced journals. Keep representative end-to-end crossings and use a
  deterministic lightweight store for pure scheduling combinations.
- Real thread and barrier tests remain where ordering is the contract. Their
  fail-safe waits must normally complete immediately.
- Stress repetition must target an actual threshold. Replace repeated identical
  lifecycles with a few complete lifecycles plus direct setup immediately below,
  at, and above the threshold.
- Keep focused atomic-write and crash-persistence tests; do not require every
  logical permutation to prove the same filesystem primitive.

### External boundaries

Representative boundary classes remain required:

- missing required data;
- wrong container or scalar type;
- minimum, maximum, equality, and one value beyond a bound;
- malformed syntax;
- oversized input;
- unknown or duplicate fields where ambiguity matters;
- unsafe paths, redirects, parser features, or identities;
- interrupted transport and partial persistence.

Large maximum-size performance probes are resource tests, not ordinary
functional cases.

### Impossible states

Do not fabricate internal states that constructors, validated settings,
migrations, old persisted data, external input, or concurrency cannot create.
A deletion based on impossibility must account for all six sources; an assertion
that current constructors do not create the state is insufficient.

### Mutation evidence

Permanent tests that rewrite or compile altered production source and then rerun
other tests are not product verification.

During consolidation, temporary mutation probes demonstrate that retained
representatives still detect the protected defect at the intended boundary. The
mutations are never committed. A small separate nightly mutation job may remain
only if it demonstrates ongoing value; mutation checks do not run on PR or
release product-verification paths.

Later refusal can mask a missing earlier guard. Eventual failure and unchanged
files do not prove an admission, worker, or publication boundary still owns its
check. A mutation probe must fail for the intended reason or the original cases
remain.

## Initial Fleet consolidation

### Cadence

Reduce `tests/test_fleetsharing_cadence.py` from 139 cases toward 50–70 while
preserving distinct timing contracts.

- Replace the 4 × 2 × 3 healthy publisher/receiver grid with boundary and pairwise
  representatives covering every phase, watch mode, and latency, including the
  worst combination.
- Replace the 4 × 3 simultaneous-metadata grid with representatives covering
  every latency and phase boundaries.
- Reduce the second 4 × 2 × 3 receiver-only grid while retaining explicit stale
  to live transitions and independent external-trace behavior.
- Reduce each period × phase × skew proof grid pairwise while retaining both
  periods, phase boundaries, and both skew signs.
- Reduce renewed-source latency products to minimum, representative, and maximum
  values with both source behaviors represented.
- Keep only one required delayed-response family when the second adds no distinct
  signed-client or authority contract.
- Shorten ordinary virtual scenarios to the minimum horizon proving startup,
  collision, stale/live transition, and tail behavior. Keep a long recurrence
  scenario only where later bursts add a distinct observation.
- Keep representative real signed-client and durable-journal crossings; do not
  fsync every scheduler combination.

### Source admission

Reduce `tests/test_fleetsharing_source_admission.py` from 201 cases toward 90–120.

- Separate barrier-position coverage from authority-change coverage instead of
  crossing every barrier with every change.
- Cover each HTTP error and each invalidation mode without crossing every error,
  work kind, and authority mutation.
- Retain exact deadline equality, `nextafter`, 401 persistence/reset boundaries,
  post-save source revocation, leaf lock ordering, committed source retirement,
  and retry across thread/session reauthentication.
- Retain positive current-authority controls, but do not duplicate them in every
  family whose named contract is obsolete-completion refusal.

### Worker revision

- Replace the 260 identical source retirements with a few complete durable
  lifecycles plus directly seeded source-observation, generation, and scheduler
  metadata around the exact capacity boundary.
- Verify pruning preserves the unrelated retry deadline and removes stale
  metadata.
- Remove permanent in-memory mutant witnesses from product verification.

### Timing mutations

Remove `tests/test_fleetsharing_worker_timing_mutations.py` from ordinary and
release product pytest. Preserve the underlying direct regressions. If a bounded
nightly mutation job remains, combine cases that can consume one shared expensive
trace and enforce its own runtime budget.

### Transport resources

- Keep normal maximum PUT escaping and memory-probe fallback behavior required.
- Move the 47 MB maximum legal response reader/codec test to the Windows resource
  gate.
- Retain a small ordinary-response real-client codec crossing in required CI if
  no existing case owns that seam.

## Broader consolidation

After the Fleet tranche, audit every file above ten Windows seconds in descending
order. The current top group includes screenshot/page harnesses, Preview
lifecycle suites, setup controllers and YAML, Fleet reservation/capacity, and
Fittings UI tests.

For each family:

1. Record entry point, result/error, effects, authority, boundary class,
   platform/encoding, incident owner, case count, and measured duration.
2. Remove test-owned overhead that does not contribute to the contract.
3. Propose retained representatives and exact removed-to-retained mappings.
4. Run temporary mutation probes for high-risk validator, authority,
   persistence, and path-safety reductions.
5. Delete equivalent cases rather than automatically moving them to extended.
6. Re-measure before choosing the next family.

Stop only when both PR and complete-suite budgets have stable headroom. Do not
optimize hundreds of sub-second files while a small number of files owns most of
the runtime.

## Suite architecture

### Required pull-request checks

Keep the stable required status names:

- `checks`
- `test (ubuntu-latest)`
- `test (windows-latest)`

`checks` retains lexical/build invariants, executable JavaScript smoke, Ruff, and
lightweight test-manifest validation.

Ubuntu runs broad required product coverage. Windows runs all required native
seams and representative subsystem contracts. New unclassified tests run in
required CI by default.

### Cadence classes

Markers describe cadence, not importance:

- `extended` — distinct exhaustive or rare compatibility contracts;
- `resource` — maximum-size, allocation, or performance probes;
- `mutation` — optional test-strength checks that alter implementations.

Windows-native ownership is orthogonal. A native test cannot be omitted from
required Windows CI merely because it is expensive; its design must be improved
or a representative native contract retained.

The execution matrix is:

| Context | Selection |
|---|---|
| PR Ubuntu | Required portable and product tests |
| PR Windows | Required tests, including all native seams |
| Main push | Required, extended, and resource product tests |
| Nightly | Complete product suite plus optional separately budgeted mutation checks |
| Release/build | Complete product suite including extended/resource, excluding mutation-of-test checks |

Node and the built release settings codec remain mandatory wherever their tests
run. Availability skips are failures.

### Windows file-level shards

Consolidation precedes sharding. If the consolidated Windows required selection
still cannot retain five-minute headroom serially, split it into two measured
file-level shards; add a third only if two are insufficient.

- Assign every test file to exactly one shard using measured Windows duration.
- Never split cases from one file across concurrent workers.
- Fail a guard if a test file is missing or assigned twice.
- Upload JUnit and timing evidence per shard.
- Use a final aggregator named `test (windows-latest)` so branch protection keeps
  one stable required status and any shard failure blocks it.
- Rebalance only from measured drift, not file count.

This avoids the shared-state and timing behavior observed in the rejected xdist
experiment while reducing wall time after the suite itself is smaller.

## Runtime budgets

Initial budgets are:

- required PR critical path: 300-second ceiling, 240-second target;
- complete Windows product verification: 600-second ceiling;
- ordinary case: two seconds unless its contract explains the exception;
- test file: twenty seconds unless it is an intentional integration/resource
  owner with a separately reviewed budget;
- `checks`: thirty seconds.

A checked-in budget manifest records file ownership and stable measured limits.
It is not a hand-maintained case-count copy. Timing reports identify the files
that exceed budget.

Budgets report without failing while ten comparable green hosted runs establish
stable headroom. Gates are enabled only after that sample. Workflow
`timeout-minutes` remains deadlock protection rather than the performance metric.

Critical path means earliest required-job start to latest completion, excluding
initial Actions queue time. File and testcase sums diagnose cost but do not
replace wall time.

## Delivery sequence

### 1. Freeze baseline and contract inventory

- Preserve current Windows and Ubuntu JUnit/timing artifacts and exact source
  SHA.
- Collect exact node IDs, outcomes, skips, family parameter counts, and file
  durations.
- Produce concise contract ledgers for targeted families.

### 2. Consolidate the five Fleet files

For each independently reviewable family:

1. Run and time the original family.
2. Add or select retained representatives.
3. Demonstrate intended sensitivity with temporary mutation probes where needed.
4. Remove equivalent cases or separate resource/mutation work.
5. Run focused, Fleet-wide, and complete Linux verification.
6. Obtain hosted Windows timing evidence before expanding scope.

### 3. Consolidate remaining hotspots

Continue in descending Windows duration until complete Windows verification
projects below ten minutes and required work is balanced enough to shard.

### 4. Add cadence markers and complete workflows

Register markers strictly, publish the exact selection truth table, and ensure no
case disappears from all product contexts. Main, nightly, build, release, and
autorelease retain their owned gates.

### 5. Add Windows file shards if necessary

Introduce measured shard assignments and the stable aggregator. Verify branch
protection with a deliberate Windows-only failure before retiring the old job.

### 6. Stabilize and enforce budgets

Collect ten comparable green runs, calculate median and nearest-rank p95, then
enable elapsed-time and file-budget failures with operating headroom.

## Verification requirements

Each consolidation slice records:

- before and after node IDs and durations;
- removed-to-retained contract mappings;
- distinct incidents preserved;
- temporary mutation results where required;
- platform and skip changes;
- focused and broader commands actually run.

Before publishing the implementation:

- build and install the release settings codec;
- verify Node availability;
- run focused and subsystem tests;
- run the complete Linux product suite;
- run JS smoke, Cargo, Ruff check, and Ruff format check;
- obtain complete hosted Windows product evidence;
- inspect all skips and reject Node/codec/native availability skips.

Acceptance requires:

1. Ten comparable runs establish required-path p95 at or below 300 seconds.
2. Complete Windows product verification finishes within 600 seconds.
3. Every retained representative passes and every temporary mutation is detected
   at its intended boundary.
4. No test is absent from all required and complete product contexts.
5. Actual DPAPI, Win32 bindings, message-pump, junction/reparse, locking, codec,
   packaging, and subsystem contracts remain covered on Windows.
6. The stable required Windows status fails for a deliberate Windows-only fault.
7. Release and build workflows independently run complete product verification.
8. Timing artifacts make future regressions attributable by file and case.

## Risks and mitigations

### Equivalent-looking cases own different authority phases

Mitigation: compare effects and authority transitions, not exception text or
helper reuse. Boundary-specific mutation probes must fail for the intended
reason.

### Extended classification hides unique regressions

Mitigation: deletion review happens before tiering. New tests are required by
default. Each moved family names its retained required representative.

### Sharding introduces races or obscures failures

Mitigation: shard by whole file, never by case; preserve per-shard JUnit; use a
stable failing aggregator; do not adopt xdist.

### Runtime gates become flaky bureaucracy

Mitigation: enable them only after ten comparable runs and retain four-minute PR
headroom below the five-minute ceiling.

### Resource limits lose real-boundary coverage

Mitigation: keep actual maximum and one-over probes in the complete resource gate
while ordinary required tests retain small real codec/transport crossings.

### Test deletion erases incident knowledge

Mitigation: retain incident comments with the representative contract and record
removed-to-retained mappings in implementation evidence. Do not preserve
behaviorally equivalent cases solely as comments made executable.
