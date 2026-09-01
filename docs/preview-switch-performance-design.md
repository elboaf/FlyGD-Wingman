# Preview switch focus and latest-wins hotkeys

Design. Base: `main` (`5eac83d`), 2026-09-01. Revised after independent review.

## Outcome

Clicking a preview or using a preview hotkey should put the requested EVE client in the foreground promptly and reliably. Rapid hotkeys should resolve to one final requested client instead of replaying every intermediate switch. Enabling **Minimize inactive clients** should not expose the desktop before or after the requested client appears.

The change stays inside the existing preview subsystem. It does not add settings, alter persisted data, move or resize an EVE client, change system-wide foreground policy, or inject synthetic keyboard input.

## Evidence and current diagnosis

### The preview does not intentionally activate

Preview windows are created with `WS_EX_NOACTIVATE` and shown with `SW_SHOWNOACTIVATE` (`wingman/preview/window.py`). The application log instead contains repeated failures from `window.activate()`:

```text
Activation of 0x61022 did not take; foreground is 0x30018.
Windows refuses a foreground change from a process that has not received recent user input.
```

On the reporting machine, `0x30018` resolved to Windows Search (`Windows.UI.Core.CoreWindow`), not Wingman. A topmost preview remains visible when EVE activation is refused, making the preview look focused while another process still owns the foreground.

Wingman already attaches its preview thread to both the foreground and target input queues before calling `SetForegroundWindow`. Staging those same attachments differently is not itself a fix. Current TriffView adds a second attempt and `SetFocus`, but evidence from that project does not prove those additions will fix Wingman's reports. Any activation change remains a hypothesis until the Windows/EVE smoke run confirms it.

### Hotkeys queue as synchronous messages

`RegisterHotKey` delivers `WM_HOTKEY` to the preview host HWND. `_host_proc()` calls `_on_hotkey()` synchronously, and `_on_hotkey()` completes the switch before the pump can dispatch another message. Distinct rapid hotkeys therefore accumulate and replay in arrival order.

`MOD_NOREPEAT` prevents one held chord from auto-repeating. It does not collapse several distinct presses or chords.

### Minimize-first necessarily creates a visible gap

With **Minimize inactive clients** enabled, `_activate_client()` minimizes the outgoing EVE client before activating the target. The minimize uses `SendMessageTimeoutW` with a 100 ms budget and has exceeded that budget in real logs. If the outgoing client disappears first, Windows can expose the shell and topmost previews before target activation.

The current order avoids a different failure: a timed-out minimize can be delivered after `SendMessageTimeoutW` returns, so reasserting the target immediately after the timeout cannot defend against that later delivery. A safe replacement must avoid both gaps and late focus theft.

## Constraints

- Preview HWNDs and DWM resources remain owned and manipulated by the preview thread.
- Every successful `AttachThreadInput(..., True)` has exactly one matching detach, including failures and exceptions. Detach in reverse order.
- Activation success is determined from `GetForegroundWindow`, not `SetForegroundWindow`'s return value.
- No EVE HWND may reach `SetWindowPos`, `SetWindowPlacement`, `MoveWindow`, or another API capable of changing EVE geometry. Flags that request no movement do not weaken this rule.
- Do not change `SPI_SETFOREGROUNDLOCKTIMEOUT` or another system-wide foreground policy.
- Do not synthesize Alt or any other input into a live game client.
- A click and hotkey continue to converge on the same host-owned switch operation.
- A Win32 call already executing cannot be cancelled. Batching applies to requests still queued when dispatch begins.
- Relative cycle actions must retain their meaning; blindly keeping the newest message ID is incorrect.
- Linux CI can verify decisions, call ordering, batching, and cleanup. Only Windows/EVE can verify real foreground transitions.

## Design

### 1. Measure and harden activation without weakening queue safety

`wingman/preview/window.py:activate()` keeps the existing principle of attaching the preview thread to both the current foreground thread and the target thread before manipulating focus. The first implementation candidate is:

1. If the target is iconic, request `ShowWindowAsync(target, SW_RESTORE)`; do not return early merely because an iconic target is transiently still reported as foreground.
2. Read the foreground HWND and return only when it is already the target **and** the target is not iconic.
3. Resolve the preview, foreground, and target thread IDs.
4. Attach the foreground queue when distinct from the preview thread.
5. Attach the target queue when distinct from the preview thread and the already-attached foreground thread.
6. Call `SetForegroundWindow(target)`.
7. Read the final foreground verdict.
8. Detach the target queue, then foreground queue, in a `finally` block.

Task 4 removed the provisional `SetFocus` fallback and its ctypes binding: its required Windows/EVE comparison did not produce qualifying evidence that it converted a refusal. There is no retry, synthetic input, foreground-policy change, or unbounded wait. Failure remains logged at INFO.

The design does **not** claim this will fix all recorded refusals. An activation approach that needs another bounded attempt must have a separately reproducible Windows/EVE justification rather than shipping ceremonial retries.

#### Iconic target verdict

`ShowWindowAsync` makes an immediate foreground verdict inherently racy. The switch result therefore distinguishes:

- **activated** — target is observed foreground;
- **pending restore** — target was iconic, restore was requested, but it is not foreground yet;
- **refused** — target was not iconic and remains outside the foreground after the bounded attempts.

A pending restore is completed by posting a dedicated host message after a short one-shot timer, not by sleeping in the preview WndProc. Only the newest pending target is retained. The retry re-resolves the client by stable key and HWND, so a client that exits or recreates its window becomes a logged no-op rather than targeting a stale handle.

No outgoing client is minimized and no selection ring moves until pending restoration is observed to succeed. A bounded retry count prevents a non-restoring client from keeping a timer alive indefinitely.

### 2. Batch queued hotkeys by action, then switch once

The host drains queued `WM_HOTKEY` messages for its own HWND with `PeekMessageW(..., WM_HOTKEY, WM_HOTKEY, PM_REMOVE)`. Filtering by HWND and exact message range leaves timers, app messages, mouse messages, and other windows untouched.

The drained IDs are not reduced to the newest ID. They are converted to registered actions and folded into one final target:

1. Start from the actual foreground EVE client, or the existing `_last_cycled` fallback when focus is outside EVE.
2. A direct character-focus action replaces the virtual target with the character selected by that chord. It supersedes earlier pending focus/cycle actions.
3. A cycle action applies its `+1` or `-1` delta to the virtual target using the current sorted, non-excluded cycle roster.
4. Continue through the drained actions in arrival order.
5. Activate only the final resolved client.

Examples with clients `A, B, C, D` and `A` foreground:

- focus `B`, focus `D` → activate `D` once;
- next, next, next → activate `D` once;
- next, previous → remain on `A`, with no activation needed;
- focus `C`, next → activate `D` once;
- next, focus `C`, previous → activate `B` once because the later absolute focus supersedes the earlier cycle and the final relative action applies to it.

An offline direct target remains a no-op at that point in the fold; a later valid action may still establish a final target. If no action resolves, nothing activates.

While bind capture is armed, normal action folding is bypassed: the newest queued registered chord is captured once and capture is disarmed, matching the existing one-press/one-capture contract.

A DEBUG line records the number of coalesced messages and the final resolved action/target. It does not log every normal single press. The design acknowledges that `PeekMessageW` is called from a WndProc; the existing mouse-move coalescer establishes this pattern, and the foreground WinEvent callback remains record-and-post only.

### 3. Replace minimize-first only after an independently observed transition probe

A successful target activation must precede minimization of the outgoing client. A failed or pending activation minimizes nothing.

The only permitted first candidate is:

1. Confirm the target is foreground through the hardened activation path.
2. Update the host's latest switch generation and target.
3. Request minimization of the now-nonforeground outgoing EVE client with `ShowWindowAsync(previous, SW_MINIMIZE)`, which does not block the preview pump and does not create an abandoned synchronous message that can be delivered after a timeout.
4. Observe foreground transitions independently of the preview thread. If minimization moves foreground away from the target, post a generation-tagged recovery message to the host. Recovery reasserts only the latest target; stale generations do nothing.

The observer is the existing out-of-context foreground WinEvent hook, not polling inside the blocked switch. A short-lived host state records:

- switch generation;
- expected target HWND and stable key;
- outgoing HWND;
- recovery deadline.

During that deadline, the hook may request recovery only when foreground moves from the expected target to the outgoing client, the shell/desktop, or one of Wingman's non-activating preview windows as a direct consequence of the requested minimize. A transition to another EVE client or unrelated application is treated as new user intent and cancels recovery rather than stealing focus back.

The candidate is retained only if a Windows probe and real EVE smoke run show all of the following:

- target is foreground before outgoing minimization is requested;
- no desktop or preview is visibly exposed;
- delayed minimization does not leave focus away from the latest target;
- rapid switches do not let stale recovery reactivate an older target;
- the preview pump remains responsive;
- no geometry-capable API receives an EVE HWND.

If `ShowWindowAsync(SW_MINIMIZE)` still produces a visible desktop transition that cannot be recovered without stealing deliberate user focus, implementation stops and **Minimize inactive clients remains unchanged** for this change. No `SetWindowPos` fallback exists.

#### Switching ownership and cleanup

Changing to activate-first alters the pure switching policy:

- `switching.should_minimize()` becomes an after-success decision; its docstring and tests no longer say "BEFORE the switch".
- `switching.should_restore()` is removed if no caller remains. It exists only to roll back minimize-first refusal.
- `_activate_client()` and its tests are updated to the selected order.
- `docs/smoke-checklist.md` is updated wherever it asserts minimize-first or rollback behavior.
- Comments in `host.py`, `win32.py`, and `CLAUDE.md`-governed nearby code are corrected rather than left describing the old incident response.

Desktop-animation suppression is also an explicit behavior change: `_animation_off` runs only around a minimize operation. With minimization disabled, an ordinary activation does not query or alter animation state. Tests pin that new behavior.

### 4. Selection and alerts

The host updates `_foreground`, focused state, `_last_cycled`, and the sticky selection ring only after activation is observed to succeed. Pending or refused activation leaves prior state unchanged.

Click acknowledgement remains guaranteed even when activation fails. If clearing a persistent alert performs visible rendering before focus is requested, acknowledgement may move after the first focus attempt, but it still runs regardless of the verdict. This is not otherwise an alert redesign.

## Failure behavior

- Unknown hotkey IDs remain logged no-ops.
- A drained action whose character is offline does not resurrect an older discarded request.
- A refused or pending foreground switch minimizes nothing.
- Failure to attach an input queue does not raise by itself; the bounded attempt still runs and observed foreground remains authoritative.
- Exceptions detach every successful input attachment before propagating.
- A client that exits during pending restore or recovery becomes a logged no-op.
- Stale minimize-recovery generations never reactivate an older target.
- A deliberate user foreground change cancels minimize recovery.
- A failed asynchronous minimize does not turn successful activation into failure; smoke verification must confirm whether the client actually minimizes.

## Testing

All production changes are test-first.

### `tests/test_preview_window.py`

- Both distinct queues are attached before focus manipulation.
- A target thread equal to the foreground thread is attached only once.
- Attachments detach once each in reverse order on success, refusal, and exception.
- `SetForegroundWindow` return values are ignored in favor of observed foreground.
- An iconic target is restored even when initially reported foreground.
- An iconic target not yet restored returns pending rather than a false refusal.

### `tests/test_preview_host.py`

- One hotkey behaves unchanged.
- Rapid absolute focus actions activate only the newest resolved target.
- Repeated cycle actions fold their deltas and activate once.
- Mixed focus/cycle actions produce the hand-derived targets listed above.
- Non-hotkey messages are not consumed.
- Capture receives only the newest queued chord.
- Coalescing emits one DEBUG summary when messages were discarded.
- Pending restore retains only the newest target and is bounded.
- Minimize is never requested before successful activation.
- Refused and pending activation minimize nothing.
- Stale recovery generations do nothing.
- Deliberate foreground changes cancel recovery.
- With minimization disabled, animation and minimize APIs are untouched.

### `tests/test_preview_switching.py`

- Minimize policy is evaluated after successful activation.
- Existing disabled, no-previous, same-client, and never-minimize cases remain false.
- Obsolete rollback policy tests and `should_restore` are removed only when the production caller is gone.

### Binding and convention guards

- `SetFocus` is not bound: Task 4 did not establish that its provisional fallback changed an observed refusal.
- `ShowWindowAsync` is already bound and remains the only minimize candidate under consideration.
- Guards continue to reject bare `SendMessageW` and every geometry-capable API receiving an EVE HWND.

### Verification commands

```bash
uv run --no-sync python -m pytest tests/test_preview_window.py tests/test_preview_host.py tests/test_preview_switching.py tests/test_preview_wiring.py -q
uv run --no-sync python -m pytest tests/ -q
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
```

## Windows probes and EVE smoke checks

The probe uses a separate observer thread or the foreground WinEvent hook so it can see transitions while the preview thread is inside a Win32 call. Temporary synthetic windows may validate instrumentation, but only EVE clients decide whether a candidate ships.

1. Record timestamped foreground HWND, process, class, and title transitions for every switch attempt.
2. From EVE, Windows Search, a browser, and Wingman, click locked and unlocked previews. Requested EVE must become foreground; preview must never become foreground.
3. A provisional `SetFocus` comparison was attempted. It produced no qualifying observed conversion, so the binding and fallback were removed.
4. Press rapid direct-character hotkeys. Only the folded final target should appear.
5. Press repeated and mixed cycle chords. The final client must match folded deltas, with no intermediate clients displayed.
6. Enable **Minimize inactive clients**. Switch while clients are idle and during grid/session load. Target must appear first and no desktop/preview gap may follow.
7. During the recovery window, intentionally alt-tab to another EVE client and to an unrelated application. Wingman must not steal focus back.
8. Switch to a minimized target repeatedly. Pending restore must resolve or expire without blocking hotkeys.
9. Hold push-to-talk or another repeating key while clicking a preview. The switch must still take.
10. Exit Wingman and verify keyboard input remains with the correct EVE client, guarding against leaked `AttachThreadInput` state.

## Probe results — 2026-09-01

**Status: BLOCKED for the Task 5 transition gate.** The independent observer
hook installed successfully, but the disposable synthetic setup could not
establish the required source-foreground precondition under this desktop's
foreground policy. Three warmup target-activation attempts all remained
refused (0/3 final target foreground); two earlier IPC diagnostic attempts
were terminated after timing out and are not counted as runs. Therefore the
required 100-run fallback-off and fallback-on synthetic comparison has **zero
qualifying runs**, and the observer never saw a target transition to validate
its gap classification.

No EVE sequence was started: without a validated independent observer and a
valid synthetic baseline, comparing a different caller process against live
clients would not prove the production preview-thread result. Consequently,
EVE runs are 0; no EVE HWND was minimized, restored, moved, resized, or sent
input. The seven `eve-online.exe` processes present before the attempt were
left running. Disposable child processes were closed/terminated and a final
process check found no remaining probe child.

**Decisions.** `SetFocus` is dropped. It produced no qualifying conversion of
an otherwise-identical observed refusal, so keeping a production binding and
second foreground request would be unsupported. Task 5 is skipped: the EVE
transition gate did not pass (it was not measured), so minimize-inactive
clients retain the existing minimize-first order. This result does not claim
that synthetic refusal behavior predicts EVE behavior; it records the
instrumentation limitation and deliberately makes neither positive claim.

**Limitation.** The non-inject-input and no-foreground-policy-change
constraints exclude programmatically manufacturing the user-input entitlement
needed to make an arbitrary disposable process foreground. A future probe
needs a manually initiated source-window focus (or an in-process, user-driven
Wingman run with DEBUG logging) before it can make the required EVE decision.

## Non-goals

- Redesigning preview mouse gestures.
- Adding named cycle groups or changing hotkey registration syntax.
- Persisting focus batches, pending restore, or recovery state.
- Passing an EVE HWND to `SetWindowPos`, `SetWindowPlacement`, `MoveWindow`, or another geometry API.
- Changing Windows foreground-lock settings.
- Injecting keyboard input.
- Guaranteeing cancellation of a Win32 call already executing.
- Refactoring unrelated rendering, alerts, discovery, or settings code.
