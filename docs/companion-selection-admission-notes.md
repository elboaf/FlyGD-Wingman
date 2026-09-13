# Companion selection admission — focused follow-up

## Current checkpoint — R1 addressed, final Linux gate GREEN

Independent general review found one Important test-helper gap (R1): synchronous
controller refusals return directly with `pending=False` and `operation_id=None`,
so a retained-operation-only lookup cannot find them. The coordinator verified
this with a real second selection while an admitted region picker remained open
and approved the minimum correction. `terminal()` now returns an already-terminal
supplied receipt directly; only pending receipts use the existing retained lookup.
No production code or admission policy changed.

`test_synchronous_selection_refusal_never_waits[receipt/wait_picker]` makes that
same real controller refusal, not a fabricated dict. The two cases respectively
require the supplied receipt immediately and an immediate picker assertion with
`Another source selection is pending`. An observer `Condition.wait` sentinel
proves neither waits; the test never intentionally spends the three-second
failure deadline. The picker count is captured before the refused request so the
still-open first picker cannot satisfy the second request. That admitted picker
is cancelled through its real callback in finally, with terminal cancellation
and readiness checked. Existing asynchronous retirement refusal/recovery cases
are unchanged and pass.

### Final commands and results

All Python commands ran in this linked checkout using
`UV_PROJECT_ENVIRONMENT=/tmp/wingman-companion-selection-admission-venv`; pytest
also used `PYTHONDONTWRITEBYTECODE=1` and `-p no:cacheprovider`.

- R1 test-first RED: **2 failed, 12 deselected, 2.74s**, both at the wait sentinel,
  no teardown errors. After the two-line helper fix, the same command returned
  **2 passed, 12 deselected, 2.13s**.
- Expanded host/backend-fixes/Wanderer companion integration/runtime/controller/
  family group: **99 passed, 15.74s**, no skips or teardown errors.
- Focused Ruff check and format: passed; **2 files already formatted**.
- Locked environment sync: **56 packages resolved / 39 checked**. Node
  **v26.5.0** confirmed. The existing built **release** and installed codec were
  verified before and after the full gate through the actual bundled-path lookup;
  both SHA-256 values remain
  `4a4b57f48829002be1aff6eda8193f9e1fb8257a9bef5666dd26b0e225e815b4`.
  No rebuild or codec replacement was necessary.

The coordinator authorized **one new full Linux gate on the corrected source**:

```bash
PYTHONDONTWRITEBYTECODE=1 UV_PROJECT_ENVIRONMENT=/tmp/wingman-companion-selection-admission-venv uv run --no-sync python -m pytest tests/ -q -rs -p no:cacheprovider --basetemp=/tmp/wingman-companion-selection-admission-r1-final-full --junitxml=/tmp/wingman-companion-selection-admission-r1-final-full.xml
UV_PROJECT_ENVIRONMENT=/tmp/wingman-companion-selection-admission-venv uv run --no-sync ruff check --no-cache .
UV_PROJECT_ENVIRONMENT=/tmp/wingman-companion-selection-admission-venv uv run --no-sync ruff format --check --no-cache .
node scripts/js_smoke.js
cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml
git diff --check
git diff --exit-code e24d0c4aee2c9ab77b2d165320cb6ca367f95b42 -- wingman
```

All exited 0. Full pytest: **11,762 passed, 13 skipped, 421.65s**. JUnit independently
confirms **11,775 cases, 0 failures, 0 errors**, including all 14 host and 7 backend
cases passing. The 13 skips are Windows-only (five junction, DPAPI, WinDLL, real
message pump/window station, three Win32 binding, tray backend and Wanderer DPAPI
cases); no Node/native-codec skips. Ruff all passed; format **431 files already
formatted**; Node all-page smoke passed; Cargo **1 passed, 0 failed/ignored**;
whitespace checks passed and production diff is empty. No test code changed after
these gates; subsequent edits only record evidence in the approved documentation.

The prior full result **11,758 passed / 2 failed / 13 skipped** and all intermediate
RED/mechanical failures remain recorded below and in the task report. This new
explicitly authorized gate verifies the corrected tests, not the cause of the
earlier unsnapshotted failures. Native Windows remains **NOT RUN**; issue 215's
own gate remains **uncleared**. The controlled main admission mechanism is proven,
but neither the original issue-215 failure nor the earlier full failures is
retrospectively proven to have that cause.

A scoped local commit of the two tests and two supplied docs is authorized after
these checks, with ordinary hooks only. Its resulting identity/status belong in
ignored `.superpowers/sdd/companion-selection-admission-plan/fix-round-1-report.md`
and the latest R1 section of `task-1-report.md`, not a self-referential committed
hash claim. Coordinator-owned post-implementation `/polish --fix` and actual
CodeRabbit still need that committed range; no such review or final acceptance
is claimed. No push, PR, merge, issue action, sibling-worktree change or user
app/settings/EVE manipulation was performed. The checkpoints below retain their
historical blocked/uncommitted status and are superseded by this section.

## Authorization and boundary

The maintainer approved a separate follow-up after issue 215's pre-PR full suite
hit a companion-picker timeout. First reproduce the admission/retirement boundary
deterministically on main, then use the existing runtime contract to decide whether
the correction belongs in test readiness or production behavior. Do not fold an
unrelated runtime change into the marker branch or silently relax a safety fence.

Worktree: `/mnt/c/dev/flygd-wingman/.worktrees/companion-selection-admission`.
Branch: `fix/companion-selection-admission`.
Base: `e24d0c4aee2c9ab77b2d165320cb6ca367f95b42`, verified upstream main after
PR 223 merged. Issue 214 is closed; its checks/Ubuntu/Windows CI passed. This
checkout does not contain the issue 215 marker changes.

Issue 215 remains unchanged and unpublished on `feature/preview-character-markers`
in its own worktree. Its reviewed patch survived rebasing byte-for-byte, but its
fresh full gate failed and is not cleared by isolated diagnostic passes.

## Evidence inherited from the bounded investigation

Original full failure: `test_master_off_keeps_admitted_region_lease_and_saved_definition_not_visible`
in `tests/test_companion_host.py`, waiting for `r.picks` for three seconds before
master-off is exercised. No terminal operation receipt was captured in that run.

Ten targeted trials per tree did not reproduce the exact timeout. One neighboring
whole-window selection case failed on the marker tree. Its trace showed:

1. Source enumeration releases its temporary selection lease.
2. With no enabled saved companion and no EVE demand, the runtime retires the pump.
3. A following selection reaches `acquire_selection` while `_stop_waiting` is true.
4. Acquisition returns None and the controller publishes a terminal refusal:
   `Another source selection is pending or the preview host is stopping`.
5. The pump finishes retiring and both workers return to normal idle waits.

This proves the captured neighboring refusal, not the cause of the original
unobserved timeout. Relevant companion runtime/controller/family code and the
imported fake pump fixture are identical on main and the marker tree. No natural
baseline failure or causal marker regression was established.

Detailed read-only evidence lives in the marker worktree under
`.superpowers/sdd/preview-character-markers-plan/pre-pr-timeout-diagnosis.md` and
`timeout-diagnostics/`. It may be read, not modified or made a committed test
dependency by this follow-up.

## Next experiment and constraints

- Hold ordinary pump retirement at a precise event/barrier in an isolated test on
  main; exercise the real controller/runtime admission and inspect the terminal
  operation receipt. Reproduce the captured interleaving without random stress.
- Determine whether existing documented/tested admission explicitly intends this
  refusal. Distinguish a test's missing readiness precondition from a production
  defect; do not choose the fix merely because it makes the test green.
- Preserve stop/shutdown admission, one retained owner, lease exclusivity and
  source validation. No timeout inflation, sleeps used as readiness, skip markers,
  retry-to-green full suites, or hidden replacement pumps.
- Initial phase may add a focused deterministic test or an ignored probe, but no
  production behavior change or commit until the coordinator has reviewed the
  diagnosis and minimal correction. Any material admission/API/ownership change
  requires explicit design approval.
- Use a dedicated environment, temporary test state and native doubles. No user
  app/settings, EVE/source windows, sibling worktree edits, pushes, PRs or issue
  changes during diagnosis.
- Any shipped correction receives independent review, `/polish --fix`, actual
  CodeRabbit review and fresh verification before PR creation. Windows/native
  acceptance is separate from Python/native-double evidence.

## Deterministic admission assessment — main e24d0c4a

Completed the approved focused experiment in the isolated checkout and dedicated
`/tmp/wingman-companion-selection-admission-venv` (`uv sync --locked --extra dev`).
No production/tracked-test edits, commits, pushes, PR/issue actions, new subagents,
full-suite retries, live application/native actions, or sibling-worktree writes.

- Three Event/Condition-controlled schedules: **3 passed, no skips, 6.06s**.
  Real runtime/controller/pump fixture; ordinary host stop paused only after
  runtime retirement committed, outside acquisition locks. Both whole and region
  selections returned terminal stopping refusals with no lease/native admission.
- The exact original region test body reproduced its picker-only three-second
  assertion under that ordering; its already-terminal refusal was inspected.
  This proves the mechanism on main, not the cause of the unobserved original
  full-suite failure. Issue 215's gate remains uncleared.
- Releasing retirement allowed both modes to save with an epoch-2 lease on the
  same retained runtime executor. Admitted region selection survived master-off
  and saved one hidden definition. With EVE active, readiness and region selection
  completed on the same epoch-1 pump without any stop. All owners closed cleanly.
- Existing runtime/controller verification: **41 passed, no skips, 5.80s**.
- Contract determination: fail-fast is intentional. Current runtime notes
  explicitly forbid leases on a pump committed to stopping; the normal
  last-demand-stop runtime test asserts refusal before final shutdown.

Recommended correction: test-only readiness after enumeration in the integrated
success helper and original master-off case; wait for no lease plus either a
stopped pump or an active pump with an active demanded family. Notify a test
Condition from the existing runtime callback, not sleeps; an unconditional
wait-for-stopped would hang with legitimate EVE demand. Inspect terminal receipts
alongside picker creation so refusal is reported directly. Add deterministic
whole/region retirement refusal/recovery and active-family readiness regressions.
Do not weaken admission or queue production requests without separate coordinator
approval for epoch ownership, bounded pending work, cancellation and shutdown.

Full assessment, exact commands/order/snapshots and proposed test design:
`.superpowers/sdd/companion-selection-admission-plan/diagnosis.md`.
Ignored harness/results: same directory's `probes/`. Await coordinator dispatch;
no implementation performed. Tracked diff remains empty.

## Task 1 implementation checkpoint — blocked at the full gate

The coordinator subsequently approved the narrow test-only implementation. Current
work remains **uncommitted** on `fix/companion-selection-admission` at base
`e24d0c4aee2c9ab77b2d165320cb6ca367f95b42`. The supplied plan is
`docs/companion-selection-admission-plan.md`. Production admission is unchanged;
`git diff --exit-code e24d0c4aee2c9ab77b2d165320cb6ca367f95b42 -- wingman`
returned 0 with no output.

### Implemented, not yet accepted

Only `tests/test_companion_host.py` was edited as code:

- One fixture Condition receives notifications after normal controller-state
  publication, picker append, and forwarding `controller.runtime_changed`.
  The normal `controller.state()` subscription is initialized before waiting.
  Callbacks never call production code while holding the observer Condition.
- Fresh-snapshot readiness requires no selection lease and either stopped, or
  active with an active sustained family. Active/no-demand is deliberately not
  ready. Failure states report context rather than retrying. This is a test-owned
  precondition, not atomic production admission.
- `add()` and the original master-off test establish readiness after successful
  enumeration. Picker waits correlate a new picker count with that operation's
  terminal receipt; completed refusal fails immediately with the semantic error.
- Real whole/region held-retirement regressions assert refusal without lease,
  picker, window or native command, then release cleanup and save using the same
  source choice in a new epoch on the retained executor. Region master-off occurs
  only after admission and leaves the persisted definition hidden/closed.
- A real EVE-demand case cancels one picker, then saves through a distinct new
  picker on the same thread/epoch without a stop. Whole recovery covers sustained
  companion-demand readiness. A Condition/Event handshake proves readiness
  actually waits while retirement is held, then wakes after real cleanup.
- Deliberate barriers release in finally; the fixture attempts both owner shutdowns
  before asserting results, joins both workers and asserts the host thread is gone.

### Fresh evidence and stop decision

All commands used the dedicated
`UV_PROJECT_ENVIRONMENT=/tmp/wingman-companion-selection-admission-venv`.
Exact commands, intermediate failures and limitations are in
`.superpowers/sdd/companion-selection-admission-plan/task-1-report.md`.

- Controlled RED: both whole and region old success assumptions failed on the
  terminal receipt during held ordinary retirement, not on missing helper code.
  Both receipts were `pending=False`, `applied=False`, `persisted=False`, error
  `Another source selection is pending or the preview host is stopping`.
  Two runs (the second exposed the complete receipt text): **2 failed** each.
- Final focused new cases: **3 passed, 9 deselected, 3.17s**.
- Final changed host + existing runtime/controller/family: **72 passed, 10.73s**,
  no skips. Focused Ruff check/format passed. All **12 host cases** also passed
  in the later full suite.
- Node **v26.5.0** was available. Built the locked release codec in this checkout,
  installed it in this checkout's ignored `packaging/bin`, verified the actual
  bundled-path lookup and availability. Source/installed SHA-256:
  `4a4b57f48829002be1aff6eda8193f9e1fb8257a9bef5666dd26b0e225e815b4`.
- The **one full Linux run FAILED**: **11,758 passed, 2 failed, 13 skipped** in
  **442.04s**. JUnit: `/tmp/wingman-companion-selection-admission-full.xml`.
  The failures are the whole/region variants of
  `tests/test_companion_backend_fixes.py::test_first_add_preserves_explicit_choice_among_identical_sources`.
  Whole asserted a non-persisted receipt; region hit its picker-only three-second
  timeout. The run did not capture either operation's terminal error/snapshot.
- Read-only inspection confirms those out-of-scope tests import `integrated` and
  select directly after enumeration without readiness. This is consistent with
  the established mechanism, but the cause of these particular failures is **not
  proven**; fixture notification timing may affect their schedule. They were not
  edited or rerun. The originally requested focused group did not include this
  importing consumer. Further investigation/correction requires coordinator scope
  approval, not an implicit readiness wait hidden inside every receipt.
- All 13 skips were Windows-specific; no Node or codec skips. No teardown errors
  were recorded, including for the two failed tests using the changed fixture.
- Remaining requested checks were completed without another suite run: Ruff all
  passed; format **431 files already formatted**; all-page Node smoke passed;
  Cargo **1 passed, 0 failed/ignored**; diff checks passed.

Stopped implementation and withheld the local commit after the out-of-scope full
failures. No push/PR/merge/issue action, production edit, subagent, external review,
user app/settings/EVE manipulation or sibling-worktree write. Independent review,
`/polish --fix`, actual CodeRabbit and any next full gate remain coordinator-owned.
Native Windows remains **NOT RUN**. The original unsnapshotted issue-215 failure
is not retrospectively proven, and issue 215's gate remains **uncleared**.

## Direct-caller follow-up — 2026-09-12 (UTC−04:00)

The coordinator authorized the minimum complete correction in the omitted direct
consumer, `tests/test_companion_backend_fixes.py`, and verification of the other
shared-fixture importer, `tests/test_wanderer_companion_integration.py`. The
coordinator owns the initial caller-scope omission. The host fixture was kept
unchanged during its independent review; its SHA-256 before/after this pass is
`3960f1fb23e65f703b5fef06d0f1afb0f721727cd8d5b0de139f817ab0f98e73`.

Inventory of every `test_companion_host` import in `tests/*.py` found exactly those
two files. Backend first-add bypasses `add`; its replacement helper also enumerates
and selects directly, but already has sustained companion demand. Wanderer uses
`add` and needed no edit. The separate native-backend harness was not changed.

Before changing the caller, an ignored cleanup-safe diagnostic ran the **unchanged
backend first-add test body** with real ordinary retirement held before selection.
Both whole and region captured operation 3's exact terminal receipt:
`pending=False`, `applied=False`, `persisted=False`, error
`Another source selection is pending or the preview host is stopping`.
Runtime was `pump=stopping`, epoch 1, both families stopped, no selection lease;
zero pickers/windows. The observer returned the original pending value and released
retirement before the unchanged region body's existing picker-only timeout.
The body then failed at its original whole persistence/region picker assertions:
**2 failed, 5.02s**, no skips or teardown errors. This is controlled evidence of
this caller's mechanism, not retrospective proof of either earlier unsnapshotted
full-run failure. Diagnostic source is ignored and not imported by shipped tests.

The backend-only code patch is **+7/-2 lines**: assert enumeration success and wait
for existing fixture readiness in first-add and replacement; record the picker
count before first-add selection and confirm through `wait_picker`'s returned new
callbacks. All explicit second-source/binding/persistence assertions are preserved.
There is no implicit readiness inside receipts, core-helper edit or policy change.

Fresh checks in the dedicated environment:

- First-add cases: **2 passed, 5 deselected, 2.60s**.
- Host, backend-fixes, Wanderer companion integration, runtime, controller and
  family together: **97 passed, 16.79s**, no skips/failures/teardown errors.
- Consumer Ruff check passed; **1 file already formatted**.
- Diff checks passed; `git diff --exit-code e24d0c4a -- wingman` remains empty.

Exact RED/GREEN commands and captured state are in the **latest caller pass**
section of `.superpowers/sdd/companion-selection-admission-plan/task-1-report.md`.
The prior full run remains **11,758 passed / 2 failed / 13 skipped**, not green.
No new full suite, commit, subagent, external review, CodeRabbit or publishing
was performed. Final full gate is **blocked pending coordinator review**; native
Windows remains **NOT RUN**, and issue 215's own gate remains **uncleared**.
