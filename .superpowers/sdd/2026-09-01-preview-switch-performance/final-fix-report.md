# Preview-switch final fix report

## Scope

This final-review wave starts at `5ee9f4a` (`fix: roll back pending preview
switch race`) and addresses all nine supplied findings. It does not implement
Task 5, geometry APIs, synthetic input, or general activate-first minimization.

## Changes

- `window.activate()` now calls `SetForegroundWindow`, observes
  `GetForegroundWindow`, and calls `SetFocus` only if that observation is the
  target. The observation remains the only `ActivationResult` verdict and
  `SetFocus`'s return remains ignored. This preserves the
  foreground-but-focusless repair without stealing keyboard focus when Windows
  retains Search or a browser.
- Pending restore remains timer-driven at 20ms but now has 25 retry turns
  (about 500ms). Expiry explicitly logs that the saved outgoing minimize was
  dropped, including its HWND.
- Pending retries deliberately do **not** enter `_animation_off`: that context
  changes a system-wide animation setting, so entering it every 20ms would
  cause setting thrash. Only the successful saved minimize retains animation
  suppression.
- Ordinary refused-switch rollback and transition-race rollback both report
  `ACTIVATED`, `PENDING_RESTORE`, and `REFUSED` as distinct outcomes.
- `should_restore()` documents both refusal and pending-transition rollback.
- A folded batch stores `_last_cycled` from its last virtual cycle target, not
  a later direct focus target, preserving the next cycle's outside-EVE
  fallback.
- Capture reads only `_registered_text.get(registered[-1][0])`. If an armed
  capture cannot resolve that newest chord, it consumes no binding and stays
  armed rather than capturing an older chord or activating the newest one.
- Pending state is retained only after a live host HWND and a nonzero timer
  are available. Missing host/timer paths log and discard the request.
- The design and smoke checklist state the 20ms/25-retry bound, require the
  outgoing client to minimize after a successful restore, describe the
  two-`IsIconic` branch, and remove remaining release-relative wording from
  the preview-switch design.

## TDD

### RED

Test expectations were added before production changes. The first focused
run was:

```text
uv run --no-sync python -m pytest tests/test_preview_window.py tests/test_preview_host.py -q
```

It failed with 10 expected behavioral failures: focus was called before the
observed foreground verdict (including refusal and pending restore), folded
cycle fallback was overwritten by a later focus, capture fell back to older
text, unarmable pending state was retained, retry expiry occurred at five
rather than 25 attempts without the dropped-minimize diagnostic, and ordinary
rollback collapsed pending/refused outcomes.

The capture test was then strengthened to prove an incomplete newest-text map
also cannot activate that chord. Its separate RED run was:

```text
uv run --no-sync python -m pytest tests/test_preview_host.py::test_capture_does_not_fall_back_to_an_older_registered_text -q
```

It failed as expected with `assert [8738] == []` before the armed-capture
no-op was implemented.

### GREEN

After the minimal code changes:

```text
uv run --no-sync python -m pytest tests/test_preview_host.py::test_capture_does_not_fall_back_to_an_older_registered_text -q
1 passed in 1.02s

uv run --no-sync python -m pytest tests/test_preview_window.py tests/test_preview_host.py tests/test_preview_cycle.py tests/test_preview_switching.py tests/test_preview_wiring.py -q
356 passed, 1 skipped in 3.97s
```

The full final verification results are recorded below.

## Self-review

Reviewed the final diff against every supplied finding and the preview
constraints. In particular:

- the sole `SetFocus` remains inside attached queues and is gated by the
  observed target foreground;
- retries do not toggle `_animation_off`, while successful deferred minimize
  still does;
- retry count is exactly 25 timer attempts after the first pending activation;
- no pending request remains if no timer can service it;
- no EVE geometry API, synthetic input, Task 5 behavior, or general ordering
  change appears in the diff.

No independent reviewer or subagent was used, as instructed.

## Verification

Final verification was run from `/mnt/c/dev/flygd-wingman-preview-switch`:

```text
uv run --no-sync python -m pytest tests/test_preview_window.py tests/test_preview_host.py tests/test_preview_cycle.py tests/test_preview_switching.py tests/test_preview_wiring.py -q
356 passed, 1 skipped in 3.97s

uv run --no-sync python -m pytest tests/ -q
3337 passed, 8 skipped in 41.07s

uv run --extra dev ruff check .
All checks passed!

uv run --extra dev ruff format --check .
198 files already formatted

git diff --check
(no output)
```

## Remaining concern

Windows/EVE smoke validation remains a merge gate. The retained minimize-first
ordering can still expose the desktop when Windows refuses a switch, a rollback
is refused, or a timed-out minimize is delivered late. The 500ms retry bound
is deliberate non-blocking behavior, not a guarantee that an EVE restore will
complete.
