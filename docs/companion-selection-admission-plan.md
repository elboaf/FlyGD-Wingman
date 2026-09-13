# Companion Selection Test Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Execute the single task below test-first.

**Goal:** Make companion integration success tests establish selection readiness and expose terminal refusals, and fix the subsequently diagnosed production shutdown lost wakeup (approved Task 2 below).

**Architecture:** Test-fixture-owned readiness notifications plus a shutdown-flag recheck under the production worker's existing condition. Preserve intentional retirement refusal, final flushing and retained-owner semantics. No new admission policy or synchronization owner.

**Tech Stack:** Existing Python/pytest/threading worker, fixtures and native doubles. The only approved production extension is the Task 2 shutdown predicate correction; no dependency, persistence or UI changes.

**Spec:** `docs/companion-selection-admission-notes.md`; deterministic assessment `.superpowers/sdd/companion-selection-admission-plan/diagnosis.md`. The coordinator approves the test-only correction below based on the main-only reproduction and the existing runtime contract.

## Global Constraints

- Work only in the linked `companion-selection-admission` worktree on `fix/companion-selection-admission`. Original Task 1 base: `e24d0c4aee2c9ab77b2d165320cb6ca367f95b42`; after the ordinary main merge, Task 2 implementation base: `ba2863a7c424bdec1df5254ce84134382fdb2362`, whole-PR review base: `7e9962a60265e66aee3efc433ca2e9a207c5f243`.
- Production edits are limited to Task 2's condition-protected shutdown predicate. No runtime admission relaxation, new retry/queue policy, timeout inflation, sleeps used as readiness, or test skips to hide failures.
- Preserve lease exclusivity, retirement/final-close fences, source validation, retained ownership, and already-admitted master-off behavior.
- Test observers must forward production callbacks unchanged and notify only after production calls/locks are released. No observer waits while holding a production acquisition lock.
- Release every deliberate barrier in finally; assert cleanup of the existing controller/runtime/host owners. Do not ship the large diagnostic tracer or expected three-second timeout demonstration.
- Keep issue 215 and all sibling worktrees unchanged. No push/PR/merge/issue action without coordinator authorization. Every shipped follow-up receives independent review, `/polish --fix`, actual CodeRabbit and fresh verification.

### Task 1: Correct readiness and add deterministic admission coverage

**Files:** Modify `tests/test_companion_host.py`, its direct consumer `tests/test_companion_backend_fixes.py`, and `docs/companion-selection-admission-notes.md`; include this approved plan as documentation. Keep production and unrelated tests unchanged. The first full gate exposed an omitted direct consumer with the same immediate-selection assumption; coordinator authorizes this minimal caller correction. Also verify the other importer, `tests/test_wanderer_companion_integration.py`, without changing its existing `add()`-based setup.

**Consumes:** Existing `integrated`/`crop_pump`, `CompanionController.state()`/`runtime_changed`, `CompanionPorts.publish_state`, `PreviewRuntime.snapshot()`/`set_state_callback`, real host `stop`, existing native doubles.

**Produces:** Fixture-local notification/wait helpers (`wait_selection_ready`, receipt-aware `wait_picker`, and supporting predicate wait/terminal lookup), plus deterministic whole/region retirement and active-family cases. These are test helpers, never a production admission API.

- [x] **1. Pin identity and reproduce the old assumption.** Read the supplied main-only experiment and its recorded original-region AssertionError/terminal receipt. Re-exercise the controlled ordering if needed for RED evidence. The meaningful RED is selection attempted during held ordinary retirement, not merely a missing helper/import. Use `/tmp/wingman-companion-selection-admission-venv`, already synced. Preserve existing deadlines and source behavior.

- [x] **2. Add fixture-owned notification without tracing infrastructure.** One `threading.Condition` is enough. A runtime callback forwards `controller.runtime_changed(state)` first, then notifies. The publish-state port and `create_picker` notify after publishing/appending their results. Initialize normal controller subscription with `controller.state()` (which sets `_subscribed`) before waiting. A condition waiter checks fresh predicates under its own condition and uses the existing three-second deadline, with current runtime/receipt context on failure. Do not call production while holding an observer lock in callbacks.

- [x] **3. Establish the success precondition after enumeration.** In `add()` and the existing master-off region test, wait after the successful source receipt and before the success-path select. Use this exact state predicate:

```python
state = runtime.snapshot()
ready = not state.selection_pending and (
    state.pump == "stopped"
    or (
        state.pump == "active"
        and (state.eve == "active" or state.companions == "active")
    )
)
```

Inventory all imports/callers of this shared fixture, not just tests named companion. Apply the same explicit precondition at the backend-fixes first-add case and its successful replacement helper, after confirming terminal refusal with a controlled pre-fix schedule. Preserve selected-source/binding assertions and do not hide readiness inside every receipt; the deliberate retirement-refusal test must remain possible.

The test owns family-demand producers during this wait. Active/no-demand is not ready: enumeration may have released its lease before retirement is committed. Never wait unconditionally for a stopped pump when EVE or an enabled saved companion sustains it. Failed/unavailable states must fail with context, not trigger retries or be accepted as ready.

- [x] **4. Make picker waits receipt-aware.** Record picker count before each select. Wait for a newly appended picker or that operation's terminal receipt; if a terminal refusal arrives first, fail with the semantic receipt, not a generic three-second picker timeout. Do not accept a pending operation as admission or reuse a previous picker's callback. Existing successful callbacks and state mutations remain real. Only replace adjacent waits needed by this correction; do not rewrite every poll in the test suite.

- [x] **R1. Preserve synchronous terminal receipts.** Independent general review found that direct `pending=False`, `operation_id=None` refusals never enter the retained operation list. Return the supplied terminal receipt directly; retain ID lookup only for pending receipts. The real second-select-while-picker-open regression is parameterized over `receipt` and `wait_picker`, with a no-wait sentinel, picker count captured before refusal and real cancellation in finally. RED: 2 sentinel failures; GREEN: both cases pass. Keep asynchronous retirement refusal coverage unchanged. No generalized observation or production change.

- [x] **5. Add deterministic retirement/refusal/recovery regressions.** Parameterize `whole` and `region` over the real integration fixture. Arm a first non-final host-stop barrier before enumeration, outside runtime/controller locks. At the held stop, assert real `acquire_selection` refusal through the controller, exact terminal error, no lease and no native/picker admission for that operation. A pending receipt alone is not success. Always release the barrier in finally. After real retirement, establish readiness, use the same valid source choice and verify successful new-epoch selection/persistence. In region mode, turn master off only after picker admission; verify the admitted lease survives, confirmation persists, and windows remain hidden/closed after cleanup. Preserve the runtime executor; do not fabricate acquisition results.

Expected refusal remains the existing production contract:

```python
assert receipt["pending"] is False
assert receipt["applied"] is False
assert receipt["persisted"] is False
assert receipt["error"] == (
    "Another source selection is pending or the preview host is stopping"
)
assert runtime.snapshot().selection_pending is False
```

Do not import ignored probes or sibling worktrees from committed tests. Keep observation limited to assertions this regression needs, not the diagnostic event log and stack machinery.

- [x] **6. Pin the active-family readiness branch.** Enable EVE before enumeration, establish readiness and select a region successfully on the same pump thread/epoch without any stop. Also check readiness after a saved enabled companion supplies durable demand (the whole-mode recovery can cover this). Ensure a readiness wait cannot finish while deliberate retirement is held, then completes when notified of actual cleanup. Use Event/Condition handshakes, not scheduler luck, arbitrary sleep or larger deadlines.

- [x] **7. Run focused GREEN and boundary regression.** Run the changed file plus existing runtime/controller/family tests:

```bash
UV_PROJECT_ENVIRONMENT=/tmp/wingman-companion-selection-admission-venv uv run --no-sync python -m pytest tests/test_companion_host.py tests/test_companion_backend_fixes.py tests/test_wanderer_companion_integration.py tests/test_preview_runtime.py tests/test_companion_controller.py tests/test_companion_family.py -q -rs
UV_PROJECT_ENVIRONMENT=/tmp/wingman-companion-selection-admission-venv uv run --no-sync ruff check tests/test_companion_host.py
UV_PROJECT_ENVIRONMENT=/tmp/wingman-companion-selection-admission-venv uv run --no-sync ruff format --check tests/test_companion_host.py
```

Record actual RED/GREEN and named cases; diagnostic passes do not substitute for shipping tests. Do not rerun full suites until a focused correction is verified.

- [x] **8. Verify and report the minimal change.** After focused GREEN, follow the repository's Node/release-codec prerequisites before a single full suite, then Ruff check/format, all-page Node smoke, Cargo and diff checks. Record exact commands/counts/skips. Prove `git diff <base> -- wingman` is empty. Append the test-only conclusion and limitations to notes: the controlled main mechanism is established, but the original unsnapshotted full failure is not retrospectively proven. Do not claim issue 215's gate cleared until its own final verification runs with the accepted prerequisite.

The coordinator explicitly authorizes a scoped local commit after verification, ordinary hooks only. Report to `.superpowers/sdd/companion-selection-admission-plan/task-1-report.md`; no subagents or duplicate reviewers. Coordinator owns independent review/polish/actual CodeRabbit and publishing decisions.

## Current extension — shutdown correction implemented, Linux gates GREEN

After publication, Ubuntu CI failed in preview shutdown; Windows and checks passed.
A controlled probe reproduced a pre-existing lost shutdown notification with no
pending save or native work. The maintainer explicitly approved extending #225 with
a narrow production synchronization fix and deterministic regression. Task 2 now
adds `_shutdown` to the existing protected pre-wait predicate, continuing through
the normal final-flush loop. RED: **1 failed, 2.62s** at the lost-notification
assertion; GREEN: **1 passed, 1.29s**, controller file **24 passed, 2.54s**.
Expanded focused checks: **454 passed, 1 Windows-only skip, 26.23s**. The unchanged
CI lost-window probe now passes before teardown, with host counts `(1, 1)`.

The single fresh full Linux gate passed: **11,841 passed, 13 Windows-only skips,
292.37s**. Ruff check/format (**431 files**), all-page Node smoke, Cargo (**1 passed**)
and whitespace checks passed. Task 1 tests and the original bridge assertion are
unchanged; the whole-PR production diff against `7e9962a6` is only this guard.
Exact commands and limits are in the current notes and Task 2 report.

Current main was merged locally without rewriting published history. The resulting
`ba2863a7` tree exactly matches failing CI merge `cc0fcaf8`, before the correction.
A scoped ordinary local follow-up commit is authorized. Independent review,
coordinator-owned `/polish --fix`, actual CodeRabbit, final verification and updated
Windows CI remain pending; earlier test-only acceptance below is historical.
No CI rerun or new push has been performed; issue 215 remains unchanged.

## Historical pre-extension completion — test-only review resolved

The final test revision is `6e76e12c4833ed5b1e7c2014294858c24b308615`.
Independent review R1 and polish P1 are addressed. P1 requires the real condition
wait to report a notification, so the retirement regression cannot pass merely
by rechecking readiness after a timeout. Production behavior remains unchanged.

Fresh coordinator verification: **11,762 passed, 13 Windows-only skips, 347.91s**;
Ruff check/format, all-page Node smoke, Cargo and range checks passed. Actual
CodeRabbit completed on this revision after one user-authorized connection retry:
four files reviewed, one minor historical-checkpoint wording finding, corrected
in this documentation-only follow-up. The failed connection attempt is not counted
as a completed review. Exact commands and remaining limits are in the notes.

This is the authoritative latest status; checkpoints below describe their earlier
states. Local review and verification are complete, but no publication or Windows
native acceptance is claimed. Issue 215 still requires its own integration gate.

## Historical R1 checkpoint — Linux gate GREEN before polish

R1 is addressed with the approved two-line helper branch and two real-controller
regression cases. Test-first RED: **2 failed, 12 deselected, 2.74s** at the observer
wait sentinel, without teardown errors. GREEN: **2 passed, 12 deselected, 2.13s**.
Expanded six-file group: **99 passed, 15.74s, no skips**; focused Ruff/format passed.

After those results, the coordinator authorized one new full Linux gate on the
final corrected tests. Node v26.5.0 and the actual installed built release codec
were confirmed in the dedicated environment. Full result: **11,762 passed,
13 Windows-only skips, 421.65s**; JUnit confirms zero failures/errors. Ruff all and
format (**431 files**) passed; Node all-page smoke and Cargo (**1 passed**) passed;
production diff is empty and whitespace checks passed. No test code changed after
verification. Exact commands, R1 evidence and limitations are in the current notes
checkpoint and ignored `fix-round-1-report.md` / latest `task-1-report.md` section.

Step 8's local verification is complete; a scoped four-path local commit is
authorized with standard hooks. Record its identity only in ignored reports.
Coordinator-owned `/polish --fix` and actual CodeRabbit remain pending on that
committed range. Native Windows is **NOT RUN**; issue 215's gate is **uncleared**.
No publishing is authorized. Earlier failure history below is retained, not
relabeled: the earlier **11,758 passed / 2 failed / 13 skipped** gate was not green,
and its unsnapshotted failures remain unproven retrospectively.

## Historical caller checkpoint — 2026-09-12, gate then pending review

The authorized backend consumer correction is implemented (+7/-2 lines): explicit
enumeration success/readiness in first-add and replacement, and receipt-aware new
picker callbacks in region first-add. Inventory found only backend-fixes and
Wanderer companion integration importing the host fixture; Wanderer required no
edit. The unchanged backend case body produced both original assertions under a
cleanup-safe held-retirement schedule with the exact terminal stopping refusal
captured (2 failed, 5.02s). This proves the controlled mechanism, not the earlier
unsnapshotted full-run cause.

First-add GREEN: 2 passed. Expanded six-file focused group: **97 passed, no skips**.
Consumer Ruff check/format and diff checks passed; production diff is empty.
Host fixture bytes were not edited during independent review. At this checkpoint,
no new full suite or commit had run; step 8 was **then blocked pending coordinator
review**. That historical blockage is superseded by the completion checkpoint
above. Exact commands/evidence remain in the historical caller-pass report section.

## Earlier verification checkpoint — blocked, uncommitted

Steps 1–7 are implemented and focused GREEN (72 passed, no skips). Step 8 ran
once with Node and the installed release codec: 11,758 passed, 2 failed, 13
Windows-only skips. Both failures are the out-of-scope direct fixture consumer
`test_first_add_preserves_explicit_choice_among_identical_sources[whole/region]`
in `tests/test_companion_backend_fixes.py`. No full-suite retry or out-of-scope
edit was made. Ruff all/format, all-page Node smoke, Cargo and production/diff
checks passed. The full gate is not green; no commit was made. See the notes and
`.superpowers/sdd/companion-selection-admission-plan/task-1-report.md` for exact
evidence and remaining coordinator decisions.

## Task 1 preflight summary (historical)

Task 1 was test-only. Notification forwarding and waiter lock direction match the existing callback contract. Both no-demand retirement and durable active-family readiness are covered. Terminal receipt checks preserve refusal semantics. The later approved production extension is exclusively Task 2 below.

### Task 2: Prevent loss of a shutdown notification before the worker waits

**Authorization:** Maintainer explicitly approved extending #225 after the deterministic CI diagnosis. Preserve the existing lifetime contract, rather than weakening the API's correct refusal to destroy a still-owned preview runtime.

**Files:** `wingman/preview/companioncontroller.py`, `tests/test_companion_controller.py`, and the existing plan/notes. No edits to the original bridge assertion or unrelated code. Keep #215 untouched.

**Evidence:** `/mnt/c/dev/flygd-wingman/.worktrees/companion-ci-shutdown/.superpowers/sdd/ci-shutdown/diagnosis.md` and `probe.py`, read-only reference. The controller file is identical across common base, main, PR head and CI merge. The missing notification reproduces controller-only and in the exact CI test on merge and PR head. A notification delivered after the worker actually waits succeeds.

**Confirmed constraints:** `_run` samples `final` under its condition, then releases it for `_flush_geometry` and `_publish`. `shutdown()` can set `_shutdown` and notify during that gap. The protected pre-wait predicate omits `_shutdown`, allowing a stale `final=False` to enter an indefinite wait. Continue through the normal iteration; never return directly from the new guard, bypass final flush, shorten admitted persistence, replace an owner, or mask timeout failures by retrying shutdown.

**Blind spots to pin:** unrelated runtime dirtiness can hide the lost wakeup; start with genuinely settled empty work. A gate must sit outside acquisition locks, between sampling final and waiting. Failure cleanup may notify only after the original result has been asserted, not as part of the fix. Confirm final flushing and genuine blocked-save owner retention still work. No new architecture, public interface, data or deployment decision is needed for this approved correction.

- [x] **1. Reproduce RED first.** Add a deterministic regression using the real controller/worker and existing fixture seams. Hold it after `final=False` was sampled and before the wait, initiate actual shutdown, observe the flag/notification, and release. Assert bounded completion and the normal final flush. The old source must fail from the lost wakeup, not a missing fixture or arbitrary sleep. Restore hooks and release/join owners in finally. Do not import ignored probes from shipped tests.
- [x] **2. Apply the narrow correction.** Include `_shutdown` in the condition-protected pre-wait decision. Re-enter the existing worker loop so it recomputes final and drains/flushes as before. No deadline or admission change; no direct early return or duplicate finalization path.
- [x] **3. Focused GREEN and retention.** Run the new test, all companion-controller tests, the unchanged failing `test_shutdown_stops_the_host_even_when_enabled`, preview wiring, existing admitted-save/timeout-owner/runtime boundaries and the six-file Task 1 group. Exercise the retained CI probe as an additional check without modifying it or treating cleanup wakeups as success. Check Ruff and exact production delta.
- [x] **4. One fresh full integration gate.** On the branch containing current main plus the correction, confirm locked environment/Node/release codec; run the full suite once after focused GREEN, inspect every skip/failure, then Ruff all/format, all-page Node smoke and independent Cargo. Stop on additional failures rather than widening scope or rerunning to green.
- [ ] **5. Commit and review.** A scoped local follow-up commit is authorized after verification, ordinary hooks only. Preserve earlier failed history; update the current notes to explain the production synchronization fix, not claim the PR is still test-only. Coordinator owns independent review, `/polish --fix`, actual CodeRabbit on the whole PR delta against current main, final verification, PR title/body correction and push. No worker publication or history rewrite.
