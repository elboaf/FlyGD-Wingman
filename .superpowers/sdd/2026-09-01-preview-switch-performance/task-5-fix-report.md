# Task 5 review-fix report

## Scope and implementation

- Replaced the outgoing async command with `SW_SHOWMINNOACTIVE = 7`. It keeps
  the activate -> selection-ring -> exact-HWND-revalidation order and ignores
  `ShowWindowAsync`'s BOOL as before. The command minimizes without activating
  the next top-level window, reducing the late-delivery foreground risk after a
  rapid return.
- Restored the guarded exception log around the direct switch activation. There
  is no rollback: activation occurs before minimize, but a preview click arrives
  through a ctypes WndProc that otherwise swallows the traceback.
- Simplified the foreground-client lookup to return only `previous_key`.
- Restored the pure, Linux-testable-policy rationale in `switching.py`, and the
  load-bearing show-state-only / no-EVE-geometry rationale in `win32.py`. The
  latter names the 2026-08-24 destructive incident and directs maintainers to
  the placement-boundary guard.
- Restored the refused-switch foreground and selection-ring invariant. The
  pending test now rejects only an outgoing `SW_SHOWMINNOACTIVE`, so a valid
  target restore using `ShowWindowAsync` does not make it fail.
- Restored the minimized-preview liveness smoke check, including the
  docked/static-scene caveat. Added a standalone LOAD-BEARING rapid A -> B -> A
  check for idle and grid/session-load conditions; it fails if A minimizes after
  return or foreground jumps to browser/desktop.
- Restored the hotkey-queue and refusal evidence in the current switch design.
  Added supersession notes to the two non-history preview-config documents;
  their original synchronous sequence remains intact as historical context.

The removed never-minimize smoke note was not restored: it described a column
in the Global keybinds card, but the current UI places the exceptions in the
`preview-nm-exceptions` disclosure directly below the minimize control.

## TDD evidence

Tests were changed before production code. The initial focused run failed as
expected for the absent `SW_SHOWMINNOACTIVE` constant/call and absent exception
log: 3 failed, 1 passed. The passed test was the restored refusal-state
invariant, which Task 5's activate-first implementation already preserved.
After the production changes, the same focused run passed: 4 passed.

## Verification

```text
uv run --no-sync python -m pytest tests/test_preview_window.py tests/test_preview_host.py tests/test_preview_cycle.py tests/test_preview_switching.py tests/test_preview_wiring.py -q
335 passed, 1 skipped in 4.32s

uv run --no-sync python -m pytest tests/ -q
3316 passed, 8 skipped in 44.63s

uv run --extra dev ruff check .
All checks passed!

uv run --extra dev ruff format --check .
198 files already formatted

git diff --check
(no output)
```

The final safety audit found no `SW_MINIMIZE` production reference and no
`SetWindowPlacement`, `GetWindowPlacement`, `WINDOWPLACEMENT`, `MoveWindow`, or
`SPI_GETWORKAREA` declaration in `wingman/preview`. The only preview
`ShowWindowAsync` call sites are target restore (`SW_RESTORE`) and outgoing
post-success minimize (`SW_SHOWMINNOACTIVE`).

## Self-review and remaining risk

A local polish pass found and fixed Ruff's nested-context (`SIM117`) issue; no
other high-confidence safe fixes were found. Per the task instruction, no
subagents or external reviewers were dispatched.

Windows/EVE smoke remains the acceptance gate. In particular, confirm command
7 actually minimizes EVE, keeps a minimized preview live, and does not allow a
rapid return to minimize A or move foreground to browser/desktop.
