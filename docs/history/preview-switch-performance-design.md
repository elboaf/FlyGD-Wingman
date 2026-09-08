# Preview switch focus and latest-wins hotkeys

Design. Base: `main` (`5eac83d`), 2026-09-01. Revised after independent review.

## Outcome

Clicking a preview or using a preview hotkey puts the requested EVE client in
front promptly and reliably. Rapid hotkeys resolve to one final requested
client instead of replaying every intermediate switch. With **Minimize inactive
clients** enabled, the exact outgoing EVE client is minimized asynchronously
only after the target is observed foreground and the host has updated its
foreground-derived selection state.

## Evidence and current diagnosis

Windows smoke clarified the visible browser flash: browser -> EVE A is clean,
but the first EVE A -> EVE B switch flashes the maximized browser; later
switches do not. Because browser is not the outgoing EVE minimize target, that
sequence identifies synchronous minimize-first as the source: removing A
exposes the z-order below it before B activates. Activate-first removes that
known gap while retaining exact outgoing-HWND validation.

`ShowWindowAsync(previous, SW_SHOWMINNOACTIVE)` is deliberately fire-and-forget.
The command minimizes without activating the next top-level window, so late
async delivery after a rapid return is less able to steal foreground. Its BOOL
reports the previous show state, not asynchronous completion, and is never
treated as a success or failure verdict. A sufficiently rapid return to the
outgoing client can still race a late minimize request; Windows/EVE smoke is the
acceptance gate for that residual risk.

### Hotkeys queue as synchronous messages

`RegisterHotKey` delivers `WM_HOTKEY` to the preview host HWND.
`_host_proc()` completes its switch before the pump dispatches another message,
so distinct rapid hotkeys queue and would replay in arrival order without the
host's action fold. `MOD_NOREPEAT` prevents one held chord from auto-repeating;
it does not collapse several distinct presses or chords.

### Refusal remains a normal result

Windows can refuse a foreground change when Wingman lacks recent user input.
Previews intentionally remain non-activating, so `GetForegroundWindow` is the
activation verdict: a refusal leaves the source foreground and selection ring
unchanged, and performs no outgoing minimize. The retained `SetFocus` only runs
after an observed target foreground; it does not turn a refusal into success.

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

1. If the target is iconic, request `ShowWindowAsync(target, SW_RESTORE)` and return `PENDING_RESTORE` immediately. Do not read or manipulate foreground/focus until a timer retry sees it non-iconic.
2. Read the foreground HWND and return only when it is already the target.
3. Resolve the preview, foreground, and target thread IDs.
4. Attach the foreground queue when distinct from the preview thread.
5. Attach the target queue when distinct from the preview thread and the already-attached foreground thread.
6. Call `SetForegroundWindow(target)`.
7. Read the foreground verdict.
8. Only when the observed foreground is `target`, call `SetFocus(target)` while the target queue remains attached; ignore its return value.
9. Detach the target queue, then foreground queue, in a `finally` block.

The final behavior retains one `SetFocus(HWND) -> HWND` binding in the EVE-O slot based on the reviewed live foreground-but-focusless symptom. It is an input-focus repair, not another activation verdict or a refusal fallback. There is no synthetic input, foreground-policy change, or unbounded wait. Failure remains logged at INFO. A refused foreground activation leaves the application Windows retained untouched, while an observed target still receives the foreground-but-focusless repair before its queues detach.

The design does **not** claim this will fix all recorded refusals. An activation approach that needs another bounded attempt must have a separately reproducible Windows/EVE justification rather than shipping ceremonial retries.

#### Iconic target verdict

Because `ShowWindowAsync` restores asynchronously, foreground work in that same turn is inherently racy. The switch result therefore distinguishes:

- **activated** — target is observed foreground;
- **pending restore** — target was iconic at activation entry and restoration was requested; foreground work is deferred until the retry sees it restored;
- **refused** — target was not iconic and remains outside the foreground after the bounded attempts.

A pending restore is completed by posting a dedicated host message after a 20ms timer turn, not by sleeping in the preview WndProc. Only the newest pending target is retained. Each retry that still observes an iconic target makes another asynchronous restore request and remains pending; it does not infer completion from that request. The retry re-resolves the client by stable key and HWND, so a client that exits or recreates its window becomes a logged no-op rather than targeting a stale handle. Twenty-five retries provide about 500ms of wall-clock opportunity without blocking the pump; expiry drops and logs any saved outgoing minimize decision. If no live host HWND or retry timer can be armed, the pending request is logged and discarded instead of becoming unserviceable state.

No outgoing client is minimized and no selection ring moves until pending restoration is observed to succeed. The bounded retry count prevents a non-restoring client from keeping a timer alive indefinitely.

### 2. Batch queued hotkeys by action, then switch once

The host drains queued `WM_HOTKEY` messages for its own HWND with `PeekMessageW(..., WM_HOTKEY, WM_HOTKEY, PM_REMOVE)`. Filtering by HWND and exact message range leaves timers, app messages, mouse messages, and other windows untouched.

The drained IDs are not reduced to the newest ID. They are converted to registered actions and folded into one final target:

1. Start from the actual foreground EVE client, or the existing `_last_cycled` fallback when focus is outside EVE.
2. A direct character-focus action replaces the virtual target with the character selected by that chord. It supersedes earlier pending focus/cycle actions.
3. A cycle action applies its `+1` or `-1` delta to the virtual target using the current sorted, non-excluded cycle roster.
4. Continue through the drained actions in arrival order.
5. Activate only the final resolved client.

`_last_cycled` records the last virtual target established by a cycle action, not a later direct-focus target in the same folded batch. This preserves the sequential-dispatch fallback when the next cycle begins outside EVE.

Examples with clients `A, B, C, D` and `A` foreground:

- focus `B`, focus `D` → activate `D` once;
- next, next, next → activate `D` once;
- next, previous → remain on `A`, with no activation needed;
- focus `C`, next → activate `D` once;
- next, focus `C`, previous → activate `B` once because the later absolute focus supersedes the earlier cycle and the final relative action applies to it.

An offline direct target remains a no-op at that point in the fold; a later valid action may still establish a final target. If no action resolves, nothing activates.

While bind capture is armed, normal action folding is bypassed: the newest queued registered chord is captured once and capture is disarmed, matching the existing one-press/one-capture contract.

A DEBUG line records the number of coalesced messages and the final resolved action/target. It does not log every normal single press. The design acknowledges that `PeekMessageW` is called from a WndProc; the existing mouse-move coalescer establishes this pattern, and the foreground WinEvent callback remains record-and-post only.

### 3. Activate first, then request the exact outgoing minimize

The host resolves the previous stable key/HWND and `should_minimize` decision
before it asks `window.activate()` to change foreground. That decision is only
executed after `ActivationResult.ACTIVATED`:

1. mark the target foreground and update focused/selected previews;
2. re-resolve the saved previous key and require its HWND to match exactly;
3. request `ShowWindowAsync(previous.hwnd, SW_SHOWMINNOACTIVE)`, which
   minimizes without activating the next top-level window.

Pending restoration retains that same decision without minimizing anything. A
retry that observes target activation marks it first and then requests the
validated minimize. A pending target whose saved outgoing client exited or
recreated its HWND logs a skip. Refused activation minimizes nothing.

This removes minimize-first rollback, the host/window two-`IsIconic` ordering
race, synchronous `SendMessageTimeoutW(SC_MINIMIZE)`, and temporary desktop
animation suppression. The animation context cannot safely bracket an async
request because it restores before the target processes that request. No
foreground-observer recovery is added: the current architecture and focused
smoke evidence do not justify one.

### 4. Selection and alerts

The host updates `_foreground`, focused state, and the sticky selection ring only after activation is observed to succeed, before requesting any outgoing minimize. `_last_cycled` records a cycle action's virtual target during folding, so a later direct focus does not rewrite cycle fallback state. Pending or refused activation leaves foreground-derived state unchanged.

Click acknowledgement remains guaranteed even when activation fails. If clearing a persistent alert performs visible rendering before focus is requested, acknowledgement may move after the first focus attempt, but it still runs regardless of the verdict. This is not otherwise an alert redesign.

## Failure behavior

- Unknown hotkey IDs remain logged no-ops.
- A drained action whose character is offline does not resurrect an older discarded request.
- Pending restore leaves the outgoing EVE client alone until a retry observes the target foreground. A target or saved outgoing HWND that exits or changes is logged and dropped rather than reused.
- Refused activation leaves the previous EVE client untouched.
- `ShowWindowAsync` completion is intentionally not inferred. Its
  `SW_SHOWMINNOACTIVE` command avoids activating the next top-level window, but
  a rapid return to an outgoing client can still race a late async minimize
  request; this is a documented Windows smoke risk, not a recovered generation.
- Failure to attach an input queue does not raise by itself; the bounded attempt still runs and observed foreground remains authoritative.
- Exceptions detach every successful input attachment before propagating.

## Testing

All production changes are test-first.

### `tests/test_preview_window.py`

- Both distinct queues are attached before focus manipulation, and `SetFocus` runs only after `GetForegroundWindow` observes the target.
- A target thread equal to the foreground thread is attached only once.
- Attachments detach once each in reverse order on success, refusal, and exception.
- `SetForegroundWindow` return values are ignored in favor of observed foreground.
- An iconic target requests restore and returns pending without reading or manipulating foreground/focus.
- The timer retry performs the normal attached foreground/focus sequence only after the target is non-iconic.

### `tests/test_preview_host.py`

- One hotkey behaves unchanged.
- Rapid absolute focus actions activate only the newest resolved target.
- Repeated cycle actions fold their deltas and activate once.
- Mixed focus/cycle actions produce the hand-derived targets listed above.
- Non-hotkey messages are not consumed.
- Capture receives only the newest queued chord.
- Coalescing emits one DEBUG summary when messages were discarded.
- Pending restore retains only the newest target when its host timer is live, validates stable key and HWND, retries exactly 25 times at 20ms, logs a dropped saved minimize on expiry, and is bounded.
- Pending activation leaves the outgoing client alone until activation succeeds, then marks the target before asynchronously minimizing only an exact saved outgoing HWND.
- Refused activation and minimization-disabled/no-previous/same-target switches leave minimize APIs untouched.

### `tests/test_preview_switching.py`

- Minimize policy remains a before-switch decision.
- Existing disabled, no-previous, same-client, and never-minimize cases remain false.
- Refused and pending activation request no minimize; successful pending retries mark first, then async-minimize only an exact saved outgoing HWND.

### Binding and convention guards

- Exactly one `SetFocus(HWND) -> HWND` declaration is bound; `tests/test_preview_wiring.py` enforces the exact single declaration on every platform, while the ctypes completeness and pointer-sized-return tests in `tests/test_preview_win32.py` run only on Windows.
- `ShowWindowAsync(SW_SHOWMINNOACTIVE)` is the sole live-client minimize
  mechanism. Its return is ignored because it reports prior show state rather
  than completion.
- Guards reject synchronous minimize sends and every geometry-capable API receiving an EVE HWND.

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
4. Attempt a switch while Windows Search and, separately, a browser retain the foreground after Windows refuses activation. Type immediately into the retained application; keyboard input must still reach it because Wingman skips `SetFocus` unless it observed the EVE target foreground.
5. Press rapid direct-character hotkeys. The burst must end at its final absolute target.
6. Press repeated and mixed cycle chords. The final client must match folded deltas, with no intermediate clients displayed after the folded switch.
7. Enable **Minimize inactive clients** and switch while clients are idle and during grid/session load. The target must become foreground and selected before its exact outgoing client receives the `SW_SHOWMINNOACTIVE` request; record any desktop/preview gap or wrong foreground.
8. Rapidly return A -> B -> A while idle and during B's grid/session load, through both preview clicks and character hotkeys. Fail the smoke if A minimizes after return or foreground jumps to browser/desktop. With **Hide previews on lost focus** and **Minimize inactive clients** enabled, also do browser -> EVE A, then the first EVE A -> EVE B: the browser stays visible until A takes foreground and B appears without a browser or desktop frame.
9. Switch to a minimized target repeatedly. Pending restore must resolve or expire within about 500ms without blocking hotkeys; on success, target selection precedes an async minimize of only the exact saved outgoing HWND.
10. Hold push-to-talk or another repeating key while clicking a preview. The switch must still take.
11. Exit Wingman and verify keyboard input remains with the correct EVE client, guarding against leaked `AttachThreadInput` state.

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

Historical Task 5 ruling (superseded by the smoke clarification below):
minimize-first remained because the earlier probe did not establish a safe
transition.

### Smoke clarification and Task 5 ruling — 2026-09-01

The confirmed browser -> EVE A -> EVE B sequence supersedes the inconclusive
probe gate for this narrowly diagnosed regression. The clean browser -> A leg
excludes browser as a minimize target; the first A -> B flash directly matches
synchronous minimize-first exposing the z-order beneath A. Task 5 therefore
ships activate/mark/async-minimize without recovery generation. The next Windows
smoke pass must verify B appears without a browser or desktop frame and assess
the residual rapid-return/late-async-minimize risk.

### Final Windows/EVE smoke results — 2026-09-01

User retest on the updated candidate reported:

- browser -> EVE A was clean;
- EVE A -> EVE B showed no browser flash;
- rapid EVE A -> EVE B -> EVE A showed no late minimize;
- the outgoing client minimized;
- the outgoing client's preview remained live.

The user concluded, "test completed, all looks good."

## Non-goals

- Redesigning preview mouse gestures.
- Adding named cycle groups or changing hotkey registration syntax.
- Persisting focus batches, pending restore, or recovery state.
- Passing an EVE HWND to `SetWindowPos`, `SetWindowPlacement`, `MoveWindow`, or another geometry API.
- Changing Windows foreground-lock settings.
- Injecting keyboard input.
- Guaranteeing cancellation of an asynchronous minimize once Windows has accepted it.
- Refactoring unrelated rendering, alerts, discovery, or settings code.
