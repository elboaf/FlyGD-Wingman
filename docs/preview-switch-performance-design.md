# Preview switch focus and latest-wins hotkeys

Design. Base: `main` (`5eac83d`), 2026-09-01. Revised after independent review.

## Outcome

Clicking a preview or using a preview hotkey should put the requested EVE client in the foreground promptly and reliably. Rapid hotkeys should resolve to one final requested client instead of replaying every intermediate switch. **Minimize inactive clients** remains minimize-first: the evidence did not justify changing its order, so this change does not close the known desktop-gap risk.

The change stays inside the existing preview subsystem. It does not add settings, alter persisted data, move or resize an EVE client, change system-wide foreground policy, or inject synthetic keyboard input.

## Evidence and current diagnosis

### The preview does not intentionally activate

Preview windows are created with `WS_EX_NOACTIVATE` and shown with `SW_SHOWNOACTIVATE` (`wingman/preview/window.py`). The application log instead contains repeated failures from `window.activate()`:

```text
Activation of 0x61022 did not take; foreground is 0x30018.
Windows refuses a foreground change from a process that has not received recent user input.
```

On the reporting machine, `0x30018` resolved to Windows Search (`Windows.UI.Core.CoreWindow`), not Wingman. A topmost preview remains visible when EVE activation is refused, making the preview look focused while another process still owns the foreground.

Wingman already attaches its preview thread to both the foreground and target input queues before calling `SetForegroundWindow`. Staging those same attachments differently is not itself a fix. Reviewed teammate commit `3f4466f` supplies a live Wingman symptom report: the target became foreground but remained focusless, losing roughly the first 0.5–1 seconds of input. It also identifies EVE-O Preview parity: `ActivateWindow` calls `SetFocus` immediately after `SetForegroundWindow` while the queues remain attached. That evidence supports the focus assignment in that exact slot, but it is not a controlled fallback-on/off experiment and does not show `SetFocus` converting an activation refusal. `GetForegroundWindow` therefore remains the only activation verdict.

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

`wingman/preview/window.py:activate()` keeps the existing principle of attaching the preview thread to both the current foreground thread and the target thread before manipulating focus. The retained sequence is:

1. If the target is iconic, request `ShowWindowAsync(target, SW_RESTORE)`; do not return early merely because an iconic target is transiently still reported as foreground.
2. Read the foreground HWND and return only when it is already the target **and** the target is not iconic.
3. Resolve the preview, foreground, and target thread IDs.
4. Attach the foreground queue when distinct from the preview thread.
5. Attach the target queue when distinct from the preview thread and the already-attached foreground thread.
6. Call `SetForegroundWindow(target)`.
7. Call `SetFocus(target)` while the target queue remains attached; ignore its return value.
8. Read the final foreground verdict.
9. Detach the target queue, then foreground queue, in a `finally` block.

The final behavior retains one `SetFocus(HWND) -> HWND` binding in the EVE-O slot based on the reviewed live foreground-but-focusless symptom. It is an input-focus assignment, not another activation verdict or a refusal fallback. There is no synthetic input, foreground-policy change, or unbounded wait. Failure remains logged at INFO. Because `SetFocus` is unconditional after `SetForegroundWindow`, a refused foreground activation may remove keyboard focus from the application that Windows kept in the foreground; this accepted risk requires the retained-application keyboard smoke check below.

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

### 3. Retain minimize-first after an inconclusive transition probe

The activate-first/asynchronous-minimize candidate required independent transition observations and real EVE smoke evidence. The external probe established neither: it had zero qualifying synthetic runs and zero EVE runs. The candidate therefore did not ship.

General non-iconic switching remains minimize-first. If activation is refused after the outgoing client was minimized, Wingman attempts to restore that outgoing client. This preserves the previous rollback behavior but cannot guarantee that the desktop or a preview is never exposed between those operations. A timed-out synchronous minimize may also be delivered later, which is why an unvalidated asynchronous replacement would not be a safe cleanup.

An iconic target is the narrow exception required by pending restoration: Wingman normally leaves the outgoing client alone while the target restore is pending, then minimizes the exact saved outgoing HWND only after the target is observed in the foreground. The host's initial `IsIconic` probe can lose a race to `activate()`'s own probe, however. If the first probe chose ordinary minimize-first and `activate()` subsequently returns pending restore, Wingman revalidates the saved stable key and HWND and requests rollback before retaining pending state; the saved minimize decision remains for a later successful retry. A refused rollback or a minimize delivered late can still expose the desktop briefly, so this narrow recovery does not close the retained minimize-first gap. This exception does not establish that activate-first is safe for ordinary switches.

No minimize-recovery generation, foreground observer recovery, or asynchronous minimize was added. `switching.should_minimize()` remains a before-switch decision, `switching.should_restore()` remains the refusal rollback decision, and desktop-animation suppression remains scoped around the existing switch operation. No `SetWindowPos` fallback exists.

### 4. Selection and alerts

The host updates `_foreground`, focused state, `_last_cycled`, and the sticky selection ring only after activation is observed to succeed. Pending or refused activation leaves prior state unchanged.

Click acknowledgement remains guaranteed even when activation fails. If clearing a persistent alert performs visible rendering before focus is requested, acknowledgement may move after the first focus attempt, but it still runs regardless of the verdict. This is not otherwise an alert redesign.

## Failure behavior

- Unknown hotkey IDs remain logged no-ops.
- A drained action whose character is offline does not resurrect an older discarded request.
- A pending restore normally minimizes nothing until the target is observed in the foreground; if its target became iconic between the host and activation probes, any already-attempted outgoing minimize is revalidated and rolled back before pending state is retained.
- A refused non-iconic switch attempts to restore the outgoing client after the existing minimize-first operation; a visible desktop gap remains possible.
- Failure to attach an input queue does not raise by itself; the bounded attempt still runs and observed foreground remains authoritative.
- Exceptions detach every successful input attachment before propagating.
- A client that exits or changes HWND during pending restore becomes a logged no-op.

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
- Pending restore retains only the newest target, validates stable key and HWND, and is bounded.
- An iconic pending target leaves the outgoing client alone until activation succeeds.
- A refused non-iconic activation exercises the retained minimize-first rollback.
- With minimization disabled, minimize APIs are untouched.

### `tests/test_preview_switching.py`

- Minimize policy remains a before-switch decision.
- Existing disabled, no-previous, same-client, and never-minimize cases remain false.
- Refusal rollback remains covered by `should_restore`.

### Binding and convention guards

- Exactly one `SetFocus(HWND) -> HWND` declaration is bound; `tests/test_preview_wiring.py` enforces the exact single declaration on every platform, while the ctypes completeness and pointer-sized-return tests in `tests/test_preview_win32.py` run only on Windows.
- `ShowWindowAsync` is already bound and remains the only minimize candidate under consideration.
- Guards continue to reject bare `SendMessageW` and every geometry-capable API receiving an EVE HWND.

### Verification commands

```bash
uv run --no-sync python -m pytest tests/test_preview_window.py tests/test_preview_host.py tests/test_preview_cycle.py tests/test_preview_switching.py tests/test_preview_wiring.py -q
uv run --no-sync python -m pytest tests/ -q
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
```

## Windows probes and EVE smoke checks

The probe uses a separate observer thread or the foreground WinEvent hook so it can see transitions while the preview thread is inside a Win32 call. Temporary synthetic windows may validate instrumentation, but only EVE clients decide whether a candidate ships.

1. Record timestamped foreground HWND, process, class, and title transitions for every switch attempt.
2. From EVE, Windows Search, a browser, and Wingman, click locked and unlocked previews. On an accepted switch, requested EVE must become foreground; on a refusal, the source must remain foreground. The preview must never become foreground.
3. After every successful switch, send keyboard input promptly. The foreground target must receive it without a focusless interval; `SetFocus` is retained for this symptom, not as proof of refusal conversion.
4. Attempt a switch while Windows Search and, separately, a browser retain the foreground after Windows refuses activation. Type immediately into the retained application; keyboard input must still reach it despite Wingman's unconditional `SetFocus` call.
5. Press rapid direct-character hotkeys. The burst must end at its final absolute target.
6. Press repeated and mixed cycle chords. The final client must match folded deltas, with no intermediate clients displayed after the folded switch.
7. Enable **Minimize inactive clients** and switch while clients are idle and during grid/session load. Record any desktop/preview gap or wrong foreground; these remain known risks of the retained minimize-first order, not a fixed behavior.
8. Switch to a minimized target repeatedly. Pending restore must resolve or expire without blocking hotkeys, and the outgoing client must stay up until the target is observed foreground.
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

**External probe decision.** The probe is inconclusive: it produced 0 qualifying
runs and therefore no controlled activation-refusal conversion, timing,
desktop-gap, or stale-focus result. The non-inject-input and
no-foreground-policy-change constraints excluded manufacturing the user-input
entitlement needed to make an arbitrary disposable process foreground. This
result does not predict EVE behavior.

**Accepted supplemental evidence and controller ruling.** Independent review of
teammate commit `3f4466fdd2c3eeb482b88e84982c9b34bc2e6efb` accepted only its
live foreground-but-focusless input-loss symptom, EVE-O `SetFocus` parity, and
relevant smoke-check intent. The commit was neither cherry-picked nor merged.
`SetFocus` is retained in the attached-queue slot, while
`GetForegroundWindow` remains authoritative; this is not claimed to convert an
activation refusal. The ruling preserves this branch's action-aware hotkey
folding, exact-HWND drain, `ActivationResult`/pending restore, and deduplicated
reverse detach.

Task 5 remains skipped and minimize-first behavior remains unchanged. The
teammate's posted `SC_MINIMIZE` was rejected: asynchronous delivery can occur
after activation-refusal rollback and race the restored foreground, while the
blocked probe supplied no safe-transition evidence. A future transition probe
still needs a manually initiated source-window focus or an in-process,
user-driven Wingman DEBUG run before changing minimize order.

## Non-goals

- Redesigning preview mouse gestures.
- Adding named cycle groups or changing hotkey registration syntax.
- Persisting focus batches, pending restore, or recovery state.
- Passing an EVE HWND to `SetWindowPos`, `SetWindowPlacement`, `MoveWindow`, or another geometry API.
- Changing Windows foreground-lock settings.
- Injecting keyboard input.
- Guaranteeing cancellation of a Win32 call already executing.
- Refactoring unrelated rendering, alerts, discovery, or settings code.
