# Preview direct activation and non-blocking foreground observation

Implemented through Task 4 on 2026-09-02. Base: `main` (`20f2939`). Automated validation is complete; the Windows/EVE acceptance pass remains pending.

## Outcome

Clicking a preview or using a preview hotkey switches to an already-visible EVE client without blocking the preview message pump in `SetForegroundWindow`. The active-character outline follows promptly, keyboard and mouse input land in the selected client, minimized targets retain their existing asynchronous restore behavior, and genuine foreground refusals retain the current attached-input fallback.

This change addresses activation after a click has been dispatched. It does not change the unlocked preview gesture grammar: an unlocked left press remains deferred until release so it can be distinguished from a left drag.

## Evidence and diagnosis

An opt-in trace measured mouse dispatch, activation calls, foreground hook delivery, restore retries, selection, alert cleanup, and outline bitmap pushes against live EVE clients.

### Baseline

With **Minimize inactive clients** off, the existing attached-input `SetForegroundWindow` call was the dominant delay:

- 31 calls exceeded 100ms;
- median blocking time was 902ms;
- observed range was 175-1,683ms;
- the preview thread could not update the outline while the call was blocked.

The outline renderer was not the cause. Across 201 pushes its median cost was 1.55ms, and the median complete selection pass was 0.85ms.

Unlocked previews add a separate 60-110ms mouse-down-to-release classification delay. Locked previews dispatch in about 1ms. That gesture tradeoff is outside this design.

### Direct-first probe

A first probe called `SetForegroundWindow` before attaching input queues, then immediately inspected the foreground:

- the direct call returned in about 1ms;
- 52 of 53 immediate observations returned foreground `0`;
- immediately entering the attached fallback still reduced median activation from about 902ms to about 328ms, showing that the direct request had started the transition;
- the attached fallback remained the source of the residual blocking.

Foreground `0` in these measured transitions was inconclusive rather than a refusal: the requested client subsequently became foreground.

### Non-blocking observation probe

The final probe treated foreground `0` as a pending transition and returned to the host pump. It retried on the existing 20ms activation timer instead of immediately attaching input queues.

Across 64 switches:

- 64 completed;
- 0 entered the attached-input fallback;
- 0 expired or remained incomplete;
- 0 logged a refusal;
- 0 produced reported swallowed, lost, or misdirected keyboard/mouse input.

Results by initial outcome:

| Initial outcome | Runs | Median outline | Median completion |
| --- | ---: | ---: | ---: |
| Directly foreground | 11 | 7.9ms | 11.5ms |
| Foreground transition pending | 20 | 39.9ms | 56.8ms |
| Minimized target pending restore | 33 | 27.7ms | 38.6ms |

Pending-foreground switches required a median 1.5 timer retries and completed within 73.5ms. That probe reissued the direct foreground request on a pending timer turn, however, so it validated non-blocking retries but not a strictly observe-only loop. The production implementation closes that gap: it issues one direct request, then timer turns only observe foreground until completion, cancellation, or the bounded attached fallback. Automated tests enforce that no activation call is reissued during observation; live Windows/EVE acceptance remains pending.

A separate manual pass prepared distinct chat-input contents in two EVE clients, switched by preview and hotkey, typed and clicked immediately, and exercised a held repeating key. The tester reported that all input landed correctly.

## Constraints

- Preview HWNDs, thumbnails, layered surfaces, and selection rendering remain owned by the preview thread.
- Wingman must never move or resize an EVE client window.
- No system-wide foreground policy may be changed.
- No keyboard or mouse input may be synthesized.
- A successful `AttachThreadInput(..., True)` must have exactly one matching detach in reverse order, including exceptions.
- `GetForegroundWindow`, not the return value of `SetForegroundWindow`, remains the activation verdict.
- Foreground `0` is not accepted as success. It means the direct request is unresolved and may be observed within a bound; it does not justify repeated foreground requests.
- A pending retry must not steal focus back after the user deliberately foregrounds another application.
- Pending timing is bounded by `time.monotonic()`, not by assuming a number of `WM_TIMER` messages equals wall time.
- A click and a hotkey continue to converge on `PreviewHost._activate_client`.
- Newer activation intent supersedes an older pending target. Existing latest-wins hotkey folding and exact-HWND checks remain intact.
- The exact outgoing EVE client may be minimized only after the target is observed foreground.
- The existing minimized-target restore path remains asynchronous and bounded.

## Design

### 1. Direct-first activation for visible targets

`wingman/preview/window.py:activate()` retains its existing early cases:

1. If the target is iconic, request `ShowWindowAsync(target, SW_RESTORE)` and return `PENDING_RESTORE`.
2. If the target is already foreground, return `ACTIVATED`.

For another visible target, activation then proceeds as follows:

1. Call `SetForegroundWindow(target)` without attaching input queues.
2. Read `GetForegroundWindow()` immediately.
3. If it is the target, return `ACTIVATED`.
4. If it is `0`, return `PENDING_FOREGROUND` without attaching or waiting.
5. If it is another nonzero HWND, run the existing attached-input activation fallback.

The direct success path does not call `SetFocus`. Live click, hotkey, keyboard, mouse, and held-key testing found no focusless interval. This also matches EVE-O Preview's direct activation behavior. `SetFocus` remains in the attached fallback, where the target queue is attached and the existing foreground verdict gates it.

### 2. Keep the attached fallback explicit

Extract the current attached-input sequence into a window-module operation that bypasses the direct path. It can be called in two cases:

- immediately, when the initial direct request leaves the request-time foreground window in place;
- once after an observe-only pending transition reaches its monotonic deadline, after source and target are revalidated.

If a different nonzero window has become foreground since the request, the pending switch is stale and is cancelled rather than stealing focus back.

The attached sequence remains unchanged:

1. resolve preview, current foreground, and target thread IDs;
2. attach each distinct nonzero foreign input queue once;
3. call `SetForegroundWindow(target)`;
4. read the foreground verdict;
5. call `SetFocus(target)` only after observing the target foreground;
6. detach successful attachments once each in reverse order in `finally`;
7. return `ACTIVATED` or `REFUSED` from the observed foreground.

The extracted operation must not retry the direct path. It rechecks `IsIconic` before attaching; an iconic target returns to the restore phase rather than recreating the desktop-flash race the current restore path prevents.

### 3. Observe pending foreground without blocking the host

Add `ActivationResult.PENDING_FOREGROUND`. `PreviewHost` retains an explicit pending phase alongside the target stable key/HWND, request-time foreground key/HWND, exact outgoing minimize decision, and a monotonic phase deadline.

A foreground-pending timer turn re-resolves the target by stable key and exact HWND and performs observation only:

1. `IsIconic(target)` moves the request to `PENDING_RESTORE` with a fresh restore-phase counter and deadline.
2. `GetForegroundWindow() == target` completes the switch.
3. Foreground `0` or the unchanged request-time foreground keeps observation pending until the deadline.
4. Any different nonzero foreground means newer user intent won; cancel without attaching, marking, or minimizing.

Observation turns never call `SetForegroundWindow`, `AttachThreadInput`, or normal `activate()`.

Restore retries retain the existing 25-turn behavior. Foreground and restore phases have separate counters/deadlines that reset on a phase transition; one phase cannot consume the other's budget.

A newer click or folded hotkey result supersedes the pending request but inherits the last virtual target as its cycle cursor and carries forward the exact original outgoing/minimize decision where appropriate. A rapid A → B(pending) → C sequence therefore resolves relative actions from B and does not lose the decision about A merely because live foreground is temporarily `0`.

### 4. Monotonic deadline fallback

The observed foreground-pending maximum was 73.5ms. Use a 250ms `time.monotonic()` deadline, providing more than three times that measured maximum without turning timer-delivery count into elapsed time.

At the deadline the host samples state once more:

- target foreground: complete normally;
- target iconic: enter the restore phase;
- a different nonzero foreground: cancel as stale user intent;
- foreground still `0` or still the request-time source: invoke the extracted attached fallback exactly once, using the validated request-time source thread when live foreground is `0`.

Before fallback, require the same target stable key/HWND and verify the request-time source HWND still names the same client when it is used. If validation fails, clear and log without touching a replacement.

If fallback activates, mark then optionally minimize. If it refuses or raises, clear the pending request, drop the saved minimize, and log. The fallback may block on an unusually busy client, but only once after the bounded fast path; no observed pending switch required it.

### 5. Selection, supersession, and foreground-hook ordering

The foreground hook remains record-and-post only. It may update the outline before the activation observer sees completion; the observer's later `_mark_client_activated` call is idempotent.

Selection remains downstream of an observed target foreground. No speculative outline is drawn while foreground is `0`, and the outgoing client is not minimized while the result is pending.

While a switch is pending, host resolution uses the pending virtual target rather than live foreground `0` for cycle anchoring. Supersession preserves the original outgoing key/HWND and minimize policy until a target is observed or the operation is cancelled. A delayed hook or fallback can never revive a superseded generation.

### 6. Remove diagnostic-only code

The production change removes:

- `WINGMAN_PREVIEW_DIRECT_ACTIVATE_PROBE` and its module constant;
- switch timing events and temporary state added around mouse, activation, hooks, alerts, and rendering;
- diagnostic-only tests that assert log formatting.

The existing `WINGMAN_PREVIEW_PERF` drag diagnostic returns to its original drag-only scope. Behavioral tests derived from the probe remain.

## Failure behavior

- A direct request accepted immediately completes without attachment.
- A temporary foreground `0` leaves the current client and saved minimize decision untouched while observe-only polling continues.
- The unchanged request-time foreground may receive the existing attached fallback; a different later foreground cancels stale intent.
- A transition exceeding the 250ms monotonic deadline receives at most one attached fallback, not an unbounded request or retry loop.
- A refused direct/fallback activation leaves foreground-derived selection unchanged and minimizes nothing.
- A target or outgoing client that exits or changes HWND is dropped rather than retargeted by character name alone.
- A newer switch cancels the older pending target before it can mark or minimize anything.
- An iconic target continues through the existing restore path; this design does not call foreground APIs while it remains iconic.

## Testing

All production behavior changes are test-first.

### `tests/test_preview_window.py`

- A non-iconic direct request observed foreground returns `ACTIVATED` without calling `AttachThreadInput` or `SetFocus`.
- A direct request followed by foreground `0` returns `PENDING_FOREGROUND` without attachments.
- A direct request that leaves another nonzero foreground enters the attached fallback.
- The attached fallback retains exact attach/detach ordering and calls `SetFocus` only after observed target foreground.
- Existing iconic, already-foreground, refusal, failed-attachment, and exception cleanup cases remain green.

### `tests/test_preview_host.py`

- Initial `PENDING_FOREGROUND` arms the 20ms timer and neither marks nor minimizes.
- N observation turns issue zero additional `SetForegroundWindow` or `AttachThreadInput` calls.
- A later observed success marks before optional asynchronous minimize.
- The 250ms bound uses an injected monotonic clock rather than timer-turn count.
- A different nonzero foreground during observation cancels without fallback.
- Deadline rechecks iconic state and invokes the attached fallback at most once.
- Deadline fallback uses a still-valid request-time source when live foreground is `0`.
- Successful deadline fallback completes normally; refused and raising fallback clear state and minimize nothing.
- Foreground/restore phase transitions reset independent counters and deadlines.
- A newer target supersedes pending foreground, retains the correct outgoing decision, and resets its own deadline.
- Cycle actions during pending foreground anchor on the pending virtual target.
- Stable-key/HWND validation prevents a recreated target or outgoing client from receiving stale intent.
- Teardown, absent host HWND, and timer-arm failure clear `PENDING_FOREGROUND` exactly as they clear restore state.
- Existing 25-turn minimized restore behavior remains unchanged.

### Verification

The automated suite and static checks below passed after the temporary probe code was removed. The Windows/EVE checklist is the remaining acceptance gate.

```bash
uv run --no-sync python -m pytest tests/test_preview_window.py tests/test_preview_host.py tests/test_preview_cycle.py tests/test_preview_switching.py tests/test_preview_wiring.py -q
uv run --no-sync python -m pytest tests/ -q
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
```

Windows verification repeats:

- locked and unlocked preview clicks with minimization on and off;
- direct-character and cycle hotkeys, including rapid latest-wins sequences;
- immediate chat typing and harmless clicks after switching in both directions;
- held push-to-talk/repeating-key switching;
- minimized targets;
- Windows Search/browser retained-foreground refusal checks;
- rapid supersession and cycle actions while foreground is temporarily `0`, with expected final target and minimize behavior asserted;
- process exit/restart to guard against leaked input-queue attachment.

## Non-goals

- Changing unlocked left-click/left-drag classification or adopting EVE-O's right-drag movement grammar.
- Moving activation to a worker thread; that alternative adds serialization, cancellation, and shutdown complexity even though the EVE HWND itself is not preview-thread-owned.
- Changing minimize policy, never-minimize semantics, cycle ordering, or hotkey registration.
- Guaranteeing a foreground transition that Windows ultimately refuses.
- Moving, resizing, maximizing, or otherwise changing EVE client geometry.
- Changing system animation or foreground-lock settings.
