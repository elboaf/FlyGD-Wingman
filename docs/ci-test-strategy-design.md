# CI and test strategy redesign

## Status

Proposed design. This document changes verification strategy, not product behavior.
Implementation requires measured, independently reviewable stages; no stage may
weaken a release gate merely to meet a duration target.

## Problem

CI gives slow feedback for an application of this size and the suite increasingly
enumerates implementation-level edge cases rather than expressing product and
boundary contracts.

A representative successful pull-request run on 2026-09-09 took 10m53s on its
critical path. The `checks` job finished in 8s, Ubuntu in 3m55s, and Windows in
10m53s. Pytest alone consumed 3m26s on Ubuntu and 9m59s on Windows. Dependency
installation, the native settings-codec build, and Cargo tests together accounted
for less than a minute on Windows. The bottleneck is therefore test execution,
not workflow setup or dependency caching.

Baseline evidence is GitHub Actions run
[`34309253993`](https://github.com/elboaf/FlyGD-Wingman/actions/runs/34309253993)
at source `ba85247ad95125168912a353c14963a68682d7d5`. Its relevant job IDs are
`102332297776` (`checks`), `102332297953` (Ubuntu), and `102332297941`
(Windows). Timings above are step timestamps from `gh run view ... --json jobs`,
not queue-inclusive workflow timestamps.

At the measured source revision the suite collected about 9,050 cases from 193
files and roughly 125,000 lines of Python/CJS test code, compared with roughly
74,000 lines of production Python/JavaScript. Test count is not itself a defect,
but the distribution shows accidental cost:

- `tests/test_ui_setup_page.py` launches a fresh Node process for each of 183
  scenarios.
- Its Node harness, `tests/fixtures/ui_setup_page.cjs`, synchronously launches
  Python one or more times to construct common replies.
- Similar per-scenario process boundaries exist in formations, Profiles, and
  other frontend runtime harnesses.
- The suite contains 680 `pytest.mark.parametrize` declarations, including many
  cross-products over fields, malformed representations, operation phases, and
  lifecycle mutations.
- The complete suite runs on both Ubuntu and Windows even where the behavior is
  pure or lexical and has no platform-dependent path.

The present strategy buys broad regression protection, but its cost discourages
fast iteration and makes all assertions look equally important. It lacks an
explicit answer to: "What product risk does this test own?"

## Goals

1. Reduce required pull-request feedback from roughly eleven minutes to a target
   of three minutes, with five minutes as the initial acceptance ceiling.
2. Preserve high-confidence coverage of user workflows, external input
   boundaries, concurrency ownership, packaging, and Windows-native behavior.
3. Make required, extended, and release verification explicit rather than
   deriving importance from whichever file a test happens to occupy.
4. Remove redundant and impossible-state cases without replacing them with a
   coverage-percentage target.
5. Preserve useful per-scenario failure reporting even when expensive runtime
   harnesses share processes.
6. Prevent suite growth from silently degrading feedback time again.

## Non-goals

- Raising or enforcing line/branch coverage percentages.
- Removing Windows verification from a Windows-only product.
- Replacing manual WebView2, installed-build, DPI, clipboard, or assistive-
  technology smoke checks with DOM doubles.
- Adding a frontend framework, bundler, browser-test framework, or generalized
  test orchestration service.
- Making release publication depend on a separately triggered CI workflow.
- Optimizing dependency installation, which is already a negligible part of the
  critical path.

## Verification principles

### Test contracts, not permutations

Every retained case should protect at least one of these contracts:

1. **User workflow:** a user-visible operation succeeds, refuses safely, or
   recovers predictably.
2. **Trust boundary:** malformed or hostile filesystem, network, OAuth, update,
   setup-import, or bridge input is rejected without unsafe side effects.
3. **Ownership/concurrency:** an old, cancelled, detached, or duplicate result
   cannot overwrite newer authority or outlive shutdown incorrectly.
4. **Platform integration:** the actual Windows, codec, Node, filesystem, or
   packaging seam behaves as required.
5. **Source-shape invariant:** source spelling or placement is itself
   load-bearing and cannot be proven through executable behavior, such as bridge
   literal visibility or forbidding a build action from bypassing `uv run`.

A case that protects none of these is a deletion candidate. Multiple cases that
protect the same contract through equivalent inputs are consolidation candidates.

### Keep edge cases at real boundaries

"Fewer edge cases" does not mean optimistic happy-path testing. External input
boundaries retain representative equivalence classes:

- missing required data;
- wrong container or scalar type;
- minimum/maximum boundary and one value beyond it;
- malformed syntax;
- oversized input;
- unknown or duplicate fields where ambiguity matters;
- unsafe path, redirect, parser feature, or identity;
- transport interruption and partial persistence.

Testing every truthy spelling, every field against every malformed scalar, or
all operation-phase × edit-field combinations is justified only when those cases
produce distinct observable outcomes, side effects, authority transitions,
platform behavior, or previously caught regressions.

### Do not test impossible internal states

Internal objects may rely on constructors, validated settings, and controller
ownership guarantees. Tests should not fabricate states that production cannot
create unless they verify recovery from persisted data written by an older or
crashed version.

### Optimize before reducing confidence

Process-boundary consolidation lands before broad case deletion. This separates
"the same tests are faster" from "fewer tests run" and gives reviewers a clean
measurement of each decision.

## Suite architecture

### Fail-closed platform rule

The complete suite continues to run on Windows for every pull request through
process consolidation, fixture reuse, and the bounded parallelism experiment.
Reducing Windows selection is conditional, not an assumed destination: it occurs
only if those confidence-preserving changes cannot meet the five-minute ceiling.

If selection is still necessary, new and unclassified tests run on Windows by
default. A test may be omitted from Windows PR execution only through an explicit,
reviewed `portable` classification. Every classification change produces a node-ID
diff showing exactly which tests stop running on Windows. This reverses the
fail-open shape where forgetting a marker silently makes new behavior Linux-only.

### Required pull-request checks

The required path contains three stable status checks. Keeping stable names
avoids silently breaking the manually configured branch-protection ruleset.

#### `checks`

Ubuntu-only, expected under 30 seconds:

- WebView2 predicate agreement;
- executable JavaScript top-level smoke gate;
- Ruff lint and format;
- build-action `uv run` invariant;
- lightweight test-manifest and timing-budget validation introduced by this
  design.

#### `test (ubuntu-latest)`

The broad, fast suite:

- pure domain behavior;
- controller and bridge contracts;
- source-shape invariants that belong in pytest;
- representative trust-boundary validation;
- persistent-worker Node runtime workflows;
- native settings-codec integration on Linux;
- Cargo settings-codec regression.

Ubuntu remains broad because it starts processes and manipulates temporary files
substantially faster than Windows.

#### `test (windows-latest)`

Initially, this remains the complete suite. If the conditional selection stage is
needed, its required Windows confidence slice contains:

- real Win32 symbol binding;
- real DPAPI behavior;
- real `winreg` import/binding plus registry branch logic through injected fake
  hives—the current suite does not perform a real registry round trip;
- message-pump/window-station tests;
- junction, reparse-point, sharing, locking, and Windows path semantics;
- native settings-codec integration on Windows;
- packaging/version derivation that can differ by platform;
- persistent-worker frontend workflow contracts;
- one representative test for each major product subsystem so an import,
  encoding, path, or dependency assumption cannot make an entire subsystem
  Linux-only accidentally.

Selection is fail-closed and mechanically guarded. A new test runs on Windows
unless explicitly classified `portable`; a new native API binding or Windows-only
contract fails a guard if it is not included. The design does not rely on file-
name folklore or a hand-copied count. Adding a safe scratch-HKCU integration test
is a future coverage improvement, not a claim this redesign makes about existing
coverage.

### Extended suite

The extended suite exists only if confidence-preserving optimization cannot make
the complete PR suite meet the ceiling. It owns expensive compatibility and
scenario matrices that are valuable but do not need to block every edit:

- exhaustive accepted-format compatibility fixtures;
- rare parser combinations after representative security classes pass;
- broad lifecycle permutations that share a production branch;
- full Windows execution of otherwise platform-independent tests.

It lives in a separate `extended.yml` workflow and runs:

- on pushes to `main`;
- on a nightly schedule;
- through an explicit workflow dispatch for pre-merge investigation.

PR, main, nightly, and manual runs use distinct concurrency groups. Manual
investigations are never cancelled by routine pushes. GitHub's default failed-
workflow notifications are the initial maintainer notification mechanism; no
custom issue bot is added without evidence that defaults are insufficient.

A failure is visible and must be fixed or reverted, but the nightly job is not a
substitute for any Windows-native PR contract. Main failures block a subsequent
release because every release path independently reruns the complete gate.

### Release-owned gate

`release.yml` and `autorelease.yml` retain their own non-cancellable Windows test
job in the `needs` chain before building or publishing. The complete gate means:

- all pytest tests with no marker exclusion;
- explicit Node availability;
- release settings-codec build and native integration;
- `cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml`.

The same complete gate runs before `build.yml` produces a manual installer.
GitHub does not allow a release workflow to assume that another workflow
completed successfully, and the current owned gate is a load-bearing protection
against publishing untested artifacts.

The repeated Node/codec/pytest/Cargo setup is extracted into a repository-local
composite action as part of the workflow rollout so four handwritten copies do
not drift. `release.yml` and `autorelease.yml` share one repository-wide publish
concurrency group with `cancel-in-progress: false`; the version/tag is rechecked
immediately before publication. This serializes publishers, but does not assume
an unlimited FIFO—GitHub may replace an older pending run when another queues.

## Runtime harness design

### Persistent worker, isolated scenarios

The setup, formations, Profiles, and similar JavaScript runtime harnesses change
from one Node process per pytest case to a session-scoped persistent Node worker.
Pytest retains one parameterized node ID per scenario. Each request receives a
fresh VM context, fresh DOM/bridge doubles, and scenario-local resources so state
cannot leak between cases.

The newline-delimited JSON protocol is:

- Python supplies one scenario name, production paths, parsed page markup,
  explicit environment overrides, and precomputed fixture replies per request.
- Node reports a structured record with scenario name, pass/fail, assertion text,
  captured stack, and duration.
- A harness crash reports the active scenario and preserves stdout/stderr; the
  fixture may restart the worker for subsequent cases but cannot relabel the
  crashed case as an ordinary assertion.
- Existing pytest/JUnit node IDs and GitHub failure annotations remain specific
  to the failed scenario.
- A scenario can still be selected directly with ordinary pytest selection.

This keeps executable production JavaScript, scenario-level timeouts, and current
failure granularity while removing repeated Node startup, source parsing, page
markup parsing, and nested Python startup.

### Precompute common Python replies

Page markup and harness data that do not vary by scenario—limits, a standard
export, catalog fixtures, and common native projections—are constructed once in
Python and passed to the worker. A scenario invokes a real Python child only when
the child-process boundary is itself under test. The harness must not reimplement
production parsing or validation in JavaScript.

Scenario-specific encoding behavior such as `PYTHONIOENCODING=cp1252` is an
explicit request field and is passed to any Python child. It does not mutate the
shared worker's environment.

### Isolation contract

Fresh VM/DOM objects alone are insufficient. Every scenario recreates handlers,
bridge queues, clocks, timers, environment overlays, and production-JavaScript
contexts. The worker detects unhandled rejections, leftover timers, and unexpected
active handles after each request. A blocking extended isolation test runs
forward, reverse, and seeded-shuffle orders, prints its seed, and includes an
`A → B → A` sentinel whose two A outcomes must match.

## Case consolidation process

Case reduction is review work, not a mechanical test-count target.

For each high-volume module:

1. Assign a contract ID to each parameter group—not each scalar example—and
   identify any regression with distinct historical ownership.
2. Compare cases by observable dimensions: public entry point, normalized
   outcome/error class, side-effect and persistence trace, authority/state
   transition, trust-boundary class, and platform/encoding semantics.
3. Combine cases only when all observable dimensions agree and no case owns a
   distinct incident. Internal production branch count is supporting evidence,
   not the definition of equivalence.
4. Keep comments that explain the incident or product risk, but remove comments
   that justify only exact implementation spelling no longer under contract.
5. For validators, authority, path safety, and persistence, deliberately weaken
   the protected behavior and demonstrate that the retained representative fails
   before deleting a group member. If no credible mutation can be demonstrated,
   retain the case.
6. An "impossible state" deletion records why constructors, migrations, old
   persisted data, external input, and concurrency cannot create that state.
7. Record before/after case count and duration, but approve the change based on
   preserved contracts rather than percentage reduction.

The first review order is based on volume and measured duration:

1. setup-page runtime and setup model/controller/schema tests;
2. formations runtime and formation-sharing validators;
3. preview host/crop/wiring matrices;
4. Profiles runtime and page conventions;
5. remaining modules with large cross-products.

Source-shape assertions receive a separate overlap review. Lexical tests remain
where source shape is the contract; they are removed when an executable test
already proves the same user-observable behavior and exact spelling is not
load-bearing.

## Conditional classification mechanism

No classification is needed while the full suite meets the PR ceiling. If the
stop/go gate proves selection necessary, use orthogonal pytest markers rather
than directory moves:

- `windows_native`: requires or validates actual Windows semantics;
- `posix_contract`: validates intentional non-Windows fallback behavior;
- `portable`: explicitly reviewed as safe to omit from the Windows PR job;
- `extended`: valuable exhaustive compatibility/permutation coverage outside the
  required PR path.

Unmarked tests run in both required jobs. Ubuntu runs every test except
`extended`; Windows runs every test except `portable` and `extended`, while
`windows_native` is never permitted to carry either exclusion. The complete
main/release suite remains `tests/` without marker exclusion. The implementation
plan must publish the exact command/selection truth table and a collected node-ID
diff before changing CI.

Marker registration is strict and CI fails on unknown markers. Guards validate
the actual collected node sets for each command and assert that:

- every platform `skipif` has intentional platform classification;
- every production native symbol group derived by AST/static inventory maps to
  named `windows_native` node IDs;
- every major subsystem in the ownership manifest retains an unexcluded Windows
  PR contract;
- no `windows_native` test is `portable` or `extended`;
- no test disappears from all required and extended commands.

The manifest maps behavior/seam ownership, not hand-maintained counts. A module
that already has one native test does not thereby cover a newly bound symbol; the
inventory must account for every binding group.

## Workflow triggers and concurrency

Normal CI changes to:

```yaml
on:
  push:
    branches: [main]
  pull_request:
```

This avoids full branch-push runs in addition to pull-request runs. Forks may
still choose to run their own Actions, but the upstream workflow does not require
both event types for the same proposed change.

Concurrency identifies a pull request consistently and preserves independent
branches:

```yaml
concurrency:
  group: ci-${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: true
```

The separate extended workflow uses event-specific PR/main/nightly/manual groups
so one cadence cannot cancel another. Release and autorelease share a publish
group with `cancel-in-progress: false`; build-only dispatches use a different
group. GitHub retains at most one running and one pending member of a concurrency
group, so this serialization is not described as an unlimited queue.

The repository does not currently use merge queue. If `merge_group` is enabled
later, CI triggers and `docs/branch-protection.md` must be updated together or
required checks can wait forever.

## Measurement and budgets

Every pytest job prints at least the slowest 30 scenario durations. JUnit XML is
retained for failure annotations and uploaded as an artifact on success or
failure. A small timing reporter also emits machine-readable JSON for workflow
setup, pytest totals, Cargo, files, persistent harnesses, and individual runtime
scenarios; JUnit alone does not supply every promised aggregation.

The implementation records these baselines before changing behavior:

- wall time per workflow job and pytest step;
- duration aggregated by test file;
- collected cases by file;
- Node and Python child-process counts for runtime harnesses;
- skip reasons on both platforms.

Initial acceptance budgets:

- required PR critical path: absolute ceiling of five minutes, with a target of
  three minutes;
- `checks`: at most 30 seconds;
- ordinary runtime scenario: at most two seconds, with separately reported and
  reasoned exceptions for native/process contracts;
- each persistent harness has its own aggregate budget and per-scenario timeout;
- no silent Node or codec availability skips;
- complete release-owned Windows suite: at most ten minutes initially, then a
  target of five minutes after confidence-preserving optimization.

Critical-path wall time means earliest required-job start to latest required-job
completion and excludes Actions queue time. Thresholds are set from at least ten
comparable clean runs using median and p95, noting cache state and reruns. The
five-minute ceiling is enforced by an elapsed-time check after stable headroom;
job `timeout-minutes` remains a coarse deadlock guard, not the performance metric.
A threshold set exactly at one observed duration would create noise rather than
prevent regressions.

## Safety and failure handling

- The optimized harness and original harness run against the same scenario list
  during migration, and their pass/fail results are compared before the original
  path is removed.
- Persistent workers retain individual pytest/JUnit scenario IDs and timeouts.
- Worker isolation is tested in fixed forward and reverse order plus a printed,
  seeded shuffle in blocking extended verification. Required PR execution stays
  deterministic with a fixed order.
- Native codec integration continues to fail when the release codec is absent;
  it never becomes an availability skip.
- Node remains an explicit prerequisite wherever executable frontend tests run.
- Windows-native failures do not fall back to mocked Linux behavior.
- Extended/main failures prevent release: release workflows execute the complete
  suite independently, even if the latest main run was green.
- JUnit failure annotation remains available without authenticated log access.

## Branch-protection migration

The preferred first implementation keeps the existing required status names:

- `checks`
- `test (ubuntu-latest)`
- `test (windows-latest)`

If implementation needs different names or separate jobs, `docs/branch-protection.md`
and the repository ruleset must be updated and manually verified in the same
rollout. A deliberately Windows-only failure must block merge before the old
check names are retired. No CI job rename is complete merely because the workflow
itself is green.

## Delivery sequence

Each stage is independently measurable and revertible.

### Stage 1 — Observability and trigger hygiene

- Add duration reporting and JUnit artifact upload.
- Record exact initial baselines and begin the ten-run comparable sample.
- Restrict ordinary push CI to `main` and unify PR concurrency.
- Do not change test selection.

### Stage 2 — Confidence-preserving optimization

- Parse page markup and construct common Python fixtures once per test session.
- Convert setup-page scenarios to a persistent worker with one pytest ID per
  scenario.
- Convert formations, Profiles, and other runtime harnesses in descending
  measured cost.
- Preserve scenario semantics and compare old/new results during each migration.
- Re-measure both platforms after every harness.
- Benchmark bounded `pytest-xdist --dist loadfile` after worker conversion. Adopt
  it only if deterministic results, child-process pressure, and failure output
  remain acceptable.

### Stop/go gate

Collect at least ten comparable full-Windows PR timings after Stage 2. If the p95
meets the five-minute ceiling, stop: do not delete cases or reduce Windows
selection merely to approach the three-minute target. Test maintainability review
may continue separately, but it is not justified as a CI-speed requirement.

If the full suite still misses the ceiling, use the measured file/scenario data
to authorize Stage 3. Classification is authorized only if consolidation alone
cannot meet the ceiling without deleting distinct contracts.

### Stage 3 — Contract inventory and consolidation (conditional)

- Inventory high-volume modules by contract ID and observable outcome dimensions.
- Consolidate equivalent parameter matrices and proven-impossible internal
  states.
- Use deliberate mutation probes to demonstrate retained tests still fail when
  protected behavior is weakened.
- Keep the complete suite on both platforms during this stage so deletion is not
  confused with platform selection.
- Re-run the stop/go measurement before authorizing Stage 4.

### Stage 4 — Suite classification (last resort)

- Register orthogonal platform/cadence markers and add node-set/native-inventory
  guards.
- Produce the exact before/after Windows node-ID selection diff for review.
- Establish the Ubuntu broad suite and fail-closed Windows confidence suite.
- Add the separate main/nightly/dispatch extended workflow.
- Extract and use the complete pytest/Node/codec/Cargo action in release,
  autorelease, and test-build workflows.
- Verify branch protection with a Windows-only deliberate failure.

## Acceptance criteria

The redesign is complete when:

1. At least ten comparable PR runs establish a required-path p95 within five
   minutes; machine-readable timings distinguish job, pytest, harness, and
   scenario cost.
2. Persistent runtime workers preserve individual pytest/JUnit IDs, fresh state,
   focused scenario selection, per-scenario timeouts, and readable failures.
3. Required Windows CI executes actual DPAPI, Win32 binding, message-pump,
   junction/reparse, locking, codec, and subsystem confidence contracts. Registry
   coverage is described accurately as real binding plus branch logic through
   fakes unless a safe real integration test is added.
4. The complete Windows pytest and Cargo suite gates manual and automatic release
   publication.
5. No required Node or native-codec integration is skipped because a prerequisite
   is absent.
6. Each extended or consolidated parameter group has a contract ID and observable-
   equivalence rationale in its review record; high-risk deletions include a
   mutation demonstration.
7. Branch protection lists the actual three required statuses and a deliberate
   Windows-only failure blocks merge.
8. JUnit timing artifacts and slow-test output make future regressions
   diagnosable from GitHub Actions.
9. The manual smoke checklist remains unchanged unless implementation discovers
   a genuinely new manual acceptance obligation.

## Risks and mitigations

### A PR passes while an extended regression exists

Mitigation: classification is a last resort; unclassified tests remain Windows-
required; trust-boundary representatives and native behavior remain required;
main runs extended coverage; all release paths rerun complete Windows pytest and
Cargo. Extended classification requires a contract rationale and cannot hide sole
native coverage.

### Persistent-worker tests leak state

Mitigation: fresh scenario resources, explicit environment overlays, active-
handle checks, old/new result comparison during migration, and blocking forward,
reverse, seeded-shuffle, and `A → B → A` isolation probes.

### Worker failure disrupts later scenarios

Mitigation: individual pytest node IDs and scenario timeouts remain; a fatal
worker failure identifies the active case, preserves output, and permits a clean
worker restart for subsequent cases without converting the crash into a pass.

### Marker drift silently drops coverage

Mitigation: strict marker registration and mechanical guards connecting native
production seams and subsystem ownership to required tests.

### Duration budgets become flaky bureaucracy

Mitigation: report first, gate only after ten comparable runs establish stable
headroom, and allow reasoned native exceptions.

### Test deletion erases incident knowledge

Mitigation: preserve distinct regression contracts and incident explanations;
consolidate only cases equivalent across observable outcome, side-effect,
authority, trust-boundary, and platform dimensions. Use mutation evidence for
high-risk groups, never a desired percentage reduction.
