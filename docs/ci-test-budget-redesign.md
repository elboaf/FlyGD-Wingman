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

Delete the 25 committed witnesses in
`tests/test_fleetsharing_worker_timing_mutations.py` after using them as temporary
probes during consolidation. Preserve the underlying direct product regressions.
They do not move unchanged into another pytest tier.

A future bounded nightly mutation job is a separate test-strength tool, not part
of the product-test inventory. If evidence justifies adding one, it must combine
checks that can consume one shared expensive trace, own a separate runtime
budget, and be explicitly exempt from the rule that every product test appears
in required or complete product verification.

### Transport resources

- Keep normal maximum PUT escaping and memory-probe fallback behavior required.
- Move the 47 MB maximum legal response reader/codec test to the Windows resource
  gate.
- Retain a small ordinary-response real-client codec crossing in required CI if
  no existing case owns that seam.

The 47 MB gate owns successful decoding of the maximum supported response through
the real reader and codec, including exact byte and row counts. On Windows it
reports `K32GetProcessMemoryInfo`'s native process-lifetime peak working set as
`process_peak_working_set_bytes`; Linux and macOS retain their existing
`ru_maxrss` metric semantics. An externally active Windows tracer fails the test
before payload construction or decode and is never stopped. These values are
observability, not a pass/fail memory ceiling, decode-only allocation peak, or
before/after delta. The initial Windows case budget remains 75 seconds; the
complete product gate's 600-second ceiling remains authoritative. A wall-time
over the case budget fails with the recorded elapsed and peak values.

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

The workflow contract is explicit because each publisher owns its test gate; no
workflow may assume another run completed successfully:

| Workflow/event | OS and pytest command | Node and codec | Cargo | Evidence and skip enforcement |
|---|---|---|---|---|
| `ci.yml` pull request — Ubuntu | `ubuntu-latest`; `pytest tests/ -m "not extended and not resource and not mutation"` | Check Node; build and install the release codec | `cargo test --locked` | JUnit and timing artifact; forbidden availability skips fail |
| `ci.yml` pull request — Windows | Before sharding: one serial `windows-latest` required job with the same marker expression. If the measured stop/go gate authorizes sharding: whole-file required shard jobs use that expression behind one stable aggregator | Serial topology builds/installs the release codec locally. Sharded topology uses one codec-preparation job that builds/tests and uploads the release binary; every shard checks Node, downloads/installs the binary, and asserts availability | Serial job runs `cargo test --locked`; sharded codec-preparation job runs it once | Serial job uploads one JUnit/timing artifact. Sharded topology uploads per-shard evidence and the aggregator checks every shard, Cargo, and forbidden skips |
| `ci.yml` push to `main` — Ubuntu | `ubuntu-latest`; `pytest tests/ -m "not mutation"` | Check Node; build/install release codec | `cargo test --locked` | Complete-product JUnit/timing artifact and skip guard |
| `ci.yml` push to `main` — Windows | `windows-latest`; `pytest tests/ -m "not mutation"` | Check Node; build/install release codec | `cargo test --locked` | Complete-product JUnit/timing artifact and skip guard |
| `extended.yml` nightly/manual | `windows-latest`; `pytest tests/ -m "not mutation"` | Check Node; build/install release codec | `cargo test --locked` | Complete-product JUnit/timing artifact and skip guard; an optional future mutation job is separate |
| `build.yml` dispatch | `windows-latest`; `pytest tests/ -m "not mutation"` before installer build | Check Node; build/install release codec | `cargo test --locked` | JUnit/timing artifact and skip guard; installer build still `needs` this job |
| `release.yml` tag | `windows-latest`; `pytest tests/ -m "not mutation"` before publication | Check Node; build/install release codec | `cargo test --locked` | JUnit/timing artifact and skip guard; build/publish still `needs` this job |
| `autorelease.yml` version push/dispatch | `windows-latest`; `pytest tests/ -m "not mutation"` before publication | Check Node; build/install release codec | `cargo test --locked` | JUnit/timing artifact and skip guard; release still `needs` this job independently of `ci.yml` |

`checks` remains Ubuntu-only and continues its existing lexical/build invariants,
JavaScript smoke, Ruff, and manifest validation; it does not duplicate pytest or
Cargo. “Forbidden availability skips” means Node or codec absence and any native
contract that should execute on that OS. A shared result checker reads JUnit skip
reasons and fails those categories; intentional capability/platform skips remain
reported with `-rs`.

The exact commands retain `uv run --no-sync python -m pytest`, `--junitxml`, and
`--durations`; the table abbreviates only those common flags. Marker registration
uses `--strict-markers`. Product-test coverage guards operate on the collected
non-`mutation` inventory. Optional mutation tooling is not silently counted as a
product release gate.

### Windows file-level shards

Consolidation precedes sharding. If the consolidated Windows required selection
still cannot retain five-minute headroom serially, split it into two measured
file-level shards; add a third only if two are insufficient.

- Assign every test file to exactly one shard using measured Windows duration.
- Never split cases from one file across concurrent workers.
- Fail a guard if a test file is missing or assigned twice.
- Upload JUnit and timing evidence per shard.
- Rebalance only from measured drift, not file count.

The PR job topology is `checks`, Ubuntu required tests, Windows codec/Cargo
preparation, Windows pytest shards, then one aggregator whose explicit job name is
`test (windows-latest)`. The aggregator has `needs` edges to every required job,
runs under `if: always()`, and fails unless every `needs.<job>.result` is
`success`. A cancelled, skipped, or failed prerequisite therefore still emits a
failing Windows required status instead of suppressing it.

Every required job writes start/completion UTC timestamps to a small artifact.
The aggregator receives `actions: read`, queries the current workflow's job
records, and computes earliest required-job start through latest prerequisite
completion. It reserves fifteen seconds for its own bounded work: more than 285
seconds before aggregation fails the 300-second PR budget. Its measurement step
runs under a 15-second shell timeout and the job uses GitHub's one-minute minimum
`timeout-minutes` guard. JUnit sums remain diagnostic and do not substitute for
this cross-job measurement.

The serial topology keeps the current exact `test (windows-latest)` status and
has no aggregator. If sharding is authorized, one atomic workflow change replaces
the matrix with: an explicit Ubuntu job still named `test (ubuntu-latest)`,
non-required shard/preparation jobs, and the aggregator as the **only** producer
of `test (windows-latest)`. An optional legacy serial Windows comparison job must
use a distinct non-required name such as `test (windows legacy)`; duplicate
producers of the required name are forbidden.

`checks` also remains exact. `docs/branch-protection.md` is updated with the new
topology, then the transition PR verifies all three names appear under Required,
confirms the required Windows check URL belongs to the aggregator, and injects a
deliberate Windows-only failure into an assigned shard. The aggregator must turn
red while the explicit Ubuntu required job remains green. Any legacy comparison
job is removed after that proof.

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

A checked-in budget manifest records each product test file's owning subsystem,
cadence, Windows shard, and measured file limit. It is not a hand-maintained
case-count copy. A new or renamed file is treated as unbudgeted: collection still
assigns it to a deterministic required fallback shard so it cannot disappear,
while `checks` fails until its owner, cadence, shard, and provisional limit are
reviewed. Renames are explicit delete/add operations; limits never follow a path
silently. File limits change only with timing evidence and review.

The workflow records source SHA, collected-node-set hash, selection expression,
shard-manifest hash, workflow revision, runner image/version, OS, Python, Node,
uv, pytest, codec/Rust toolchain, cache-hit state, and required-job timestamps.
An automated report groups attempts only when source, selection, shard manifest,
and workflow revision match; image/tool changes are shown as strata rather than
silently pooled. Failed, cancelled, missing-artifact, or availability-skipped
runs never count as green samples.

Ten comparable green attempts are the minimum rollout sample, not a statistically
stable population p95. The report uses median and nearest-rank maximum and labels
the latter accurately; it does not infer a population tail. The sample resets
after any product selection, shard assignment, workflow topology, or test-runtime
change. Tool/image changes require either a new sample or an explicit stratified
comparison. The implementation coordinator collects the generated report and the
maintainer authorizes enabling or revising gates.

Budgets report without failing during that sample. Workflow `timeout-minutes`
remains deadlock protection rather than the performance metric. Timing reports
identify files that exceed budget and show manifest defaults separately.

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

Register markers strictly, implement the workflow/OS command table above, and
ensure no product case disappears from all required and complete product
contexts. Main, nightly, build, release, and autorelease retain their owned Node,
codec, pytest, Cargo, evidence, and skip-enforcement gates. Optional mutation
tooling is inventoried separately and is not subject to the product-context
coverage guard.

### 5. Add Windows file shards if necessary

Introduce measured shard assignments, timestamp artifacts/API collection, and
the fail-closed `if: always()` aggregator. Update and manually verify branch
protection with a deliberate Windows-only failure before retiring the old matrix
job.

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
4. No non-mutation product test is absent from all required and complete product
   contexts; any optional mutation corpus has its own explicit inventory and
   nightly command.
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
