# Preview-switch polish fix report

## Scope

Fixed the host/activation `IsIconic` transition race reported in
`polish-report.md`. If the host observes a non-iconic target, performs the
ordinary minimize-first send, and `window_mod.activate()` subsequently returns
`PENDING_RESTORE`, the host now revalidates the saved outgoing stable key and
HWND, requests rollback of that exact client, then retains the pending target.
The saved minimize decision remains in `_PendingSwitch` and is still applied
only if the later retry observes the target foreground.

Ordinary non-iconic minimize-first sequencing is unchanged. No Task 5 work or
geometry APIs were added.

## TDD

### RED

Added the transition-race regression test first, then ran:

```text
uv run --no-sync python -m pytest tests/test_preview_host.py::test_a_target_that_becomes_iconic_after_the_host_probe_rolls_back_before_pending -q
```

It failed as expected because the recorded sequence lacked the rollback call:

```text
Right contains one more item: ('activate', 4369)
```

### GREEN

Implemented the minimal pending-result branch: revalidate the current client
record against the saved stable key/HWND, request rollback before
`_arm_pending_activation()`, and log the explicit `ActivationResult` outcome
(`restored`, `is still pending`, or `was refused`) without enum truthiness.
The RED test then passed.

Added coverage for a replaced outgoing client (no stale-HWND rollback) and for
a refused rollback while the newer pending request remains timer-bounded.

## Self-review and decisions

- The rollback path is entered only when the original minimize was attempted
  under the host's non-iconic probe and the authoritative activation result is
  `PENDING_RESTORE`.
- Revalidation uses both the saved stable key lookup and exact saved HWND before
  the rollback call. A missing/recreated client is logged and not targeted.
- Pending state is armed only after the rollback decision. A refusal does not
  discard the pending target; the existing newest-wins replacement and bounded
  retry behavior remain in force.
- The direct `ActivationResult` identity checks keep `REFUSED` and
  `PENDING_RESTORE` distinct. No enum is used as a boolean.
- Reviewed the final diff and surrounding pending/minimize paths manually; no
  additional high-confidence safe polish change was identified. No subagents
  were dispatched, per instruction.

## Documentation

`docs/preview-switch-performance-design.md`, `docs/smoke-checklist.md`, and the
host rationale now describe the narrow two-probe race, exact-HWND rollback, and
remaining limitation: a refused rollback or delayed minimize can still briefly
expose the desktop. The smoke guidance no longer treats one successful switch
as proof that the gap is closed.

## Verification

Final commands run from `/mnt/c/dev/flygd-wingman-preview-switch`:

```text
uv run --extra dev ruff format tests/test_preview_host.py
1 file left unchanged

uv run --no-sync python -m pytest tests/test_preview_window.py tests/test_preview_host.py tests/test_preview_cycle.py tests/test_preview_switching.py tests/test_preview_wiring.py -q
348 passed, 1 skipped in 4.08s

uv run --no-sync python -m pytest tests/ -q
3329 passed, 8 skipped in 41.33s

uv run --extra dev ruff check .
All checks passed!

uv run --extra dev ruff format --check .
198 files already formatted

git diff --check
(no output)
```

## Remaining concern

The rollback is a best-effort Win32 activation request. Windows can refuse it,
and a previously timed-out minimize can be delivered late; the fix closes the
specific unhandled transition path but cannot guarantee that no desktop/preview
flash is visible. Windows/EVE smoke validation remains required for that
residual timing behavior.
