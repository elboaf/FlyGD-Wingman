# Preview configuration options — design

Four settings that close the largest remaining gaps between Wingman's preview
subsystem and TriffView's, chosen from a full option-by-option comparison
rather than from a feature request. Item 8 ("Label customisation") and the
first half of item 10 ("Switching behaviour") of
`docs/history/eve-preview-design.md:459,473`, plus two of the "Smaller gaps"
listed at `:684`.

The trigger was a user report that the character name cannot be turned off.
That is the headline, but three of the four settings below are already built
and merely unreachable, so the slice is mostly wiring rather than new
machinery.

## Intended outcome

On the Previews section of Settings:

- **Labels** — a checkbox. Off hides the character-name band on every preview
  and gives its 30 px back to the mirrored video.
- **Lock** — a per-character control. A locked preview cannot be moved by a
  left drag; right-drag still moves it deliberately.
- **Opacity** — a slider, 20–255. Dims the mirrored video only; the border and
  label stay at full strength.
- **Minimize inactive clients** — a checkbox plus a per-character
  "never minimize" list. When Wingman switches you to a client, the one you
  were on is minimized.

`PRODUCT.md`'s client-window rule is restated to match what the code has always
done.

## Evidence and constraints

**Three of the four are already built.**

| Setting | What exists | Reference |
| --- | --- | --- |
| `show_labels` | `render()` already skips the band when `label_h` is 0 | `chrome.py:107-108` |
| `locked` | `layout.Entry.locked` persists, is restored, and is honoured | `layout.py:15`, `host.py:427`, `window.py:416` |
| `opacity` | key validated and clamped 20–255; `DWM_TNP_OPACITY` already set | `settings.py:211-215`, `thumbnail.py:38,43` |

`chrome.py` needs no edit at all. `band_bottom = min(h - 1, border + label_h)`
guarded by `if band_bottom > border` means `label_h=0` already produces a
bandless tile. `show_labels` is three call sites in `window.py`, nothing more.

`opacity` is likewise two call sites: `thumbnail.update()` takes
`opacity: int = 255` (`thumbnail.py:31`) and both callers
(`window.py:321`, `:382`) accept the default.

**Wingman already changes a running client's show-state.** `activate()` calls
`IsIconic` and `ShowWindowAsync(hwnd, SW_RESTORE)` on the *client's* window
handle (`window.py:77-78`), reached from both the click path
(`window.py:468`) and the hotkey path (`host.py:576`). Click-to-focus depends
on it: a minimized client cannot be brought forward without it.

This matters because `PRODUCT.md:105` currently reads "It must not touch a
running EVE client's window." Taken literally that forbids shipping code. The
rule that the codebase actually follows, and that the incident of 2026-08-24
actually established, is narrower: **never set a client's rect or size.**
`docs/history/eve-preview-design.md:495` states the mechanism — EVE reads a
resize as a resolution change and rewrites its own configuration. Show-state
changes carry no such hazard; minimize and restore are what the taskbar button
and alt-tab already send.

**The live-read seam is an injected callable.** `_restoring()`
(`host.py:709-726`) reads a setting fresh on the preview thread inside the
sweep, wrapped in a guarded `except` that falls back to the safe behaviour
because "it must not be the thing that kills the pump." Every new setting the
preview thread needs follows this shape rather than being captured at
construction.

**`redraw()` early-returns on an unchanged chrome key** (`window.py:325-343`),
so a setting that changes the bitmap must join `_chrome_key()` or the toggle
silently does nothing to open windows.

**The per-character table already exists.** `previews.js:37-55` merges running
clients, `roster.seen`, and any character carrying a binding, with an
`Object.create(null)` guard against a character named `__proto__`. The
never-minimize list and the lock control reuse it rather than inventing a
control.

**Settings commit per field.** No Save button; every field returns
`{applied, persisted, error}` and the page distinguishes refused / applied-not-
persisted / ok (`DESIGN.md:280-286`). `_write_alert_setting`
(`api.py:2024-2070`) is the nested-path reference, including its warning that
`_normalize` reassigns `preview` wholesale so a reference held across
`update()` is stale.

**TriffView's minimize ordering is tuned, not incidental.**
`TriffViewSubsystem.cs:779-799`:

1. resolve the previous client,
2. activate the new one — **and return early if that fails**,
3. sleep `SwitchSettleBeforeMinimizeMs` (10 ms, `:22`),
4. minimize the previous via `SendMessage(WM_SYSCOMMAND, SC_MINIMIZE)`,
5. **activate the new client a second time.**

Steps 2 and 5 are the difference between this and the naive version. Bailing on
a failed activation is what stops a failed switch from minimizing your client
into an empty desktop; the second activation is what stops the minimize from
stealing foreground back off the client you just switched to. The README calls
the result "no more dropping to desktop or lagging when cycling"
(`../TriffView/README.md:30`), which reads as the scar tissue from both.

**`SendMessageW` is not bound in `preview/win32.py`** — only `PostMessageW`
(`win32.py:306`). `WM_SYSCOMMAND` and `SC_MINIMIZE` are not declared either.

**The client-placement guard test** (`tests/test_preview_wiring.py:465`)
asserts `SetWindowPlacement`, `GetWindowPlacement`, `WINDOWPLACEMENT`,
`SPI_GETWORKAREA` and `SystemParametersInfoW` are absent from
`preview/win32.py`. `SC_MINIMIZE` is not on that list and adding it does not
trip the test — but the guard exists because the last feature to reach into a
client window destroyed three characters' settings, so the new call site
inherits the burden of proof.

## Decisions for review

### 1. The client-window rule is restated, not excepted

`PRODUCT.md:105` becomes a rule about **geometry**, not about contact, and
names the two show-state calls that ship:

> **It must not set a running EVE client's position or size.** Not moved, not
> resized, not repositioned. EVE reads a resize as a resolution change and
> rewrites its own configuration; a test once destroyed three characters'
> settings that way. Previews are separate windows that mirror a client.
> Changing a client's *show state* is not the same thing and is allowed where
> the user asked for it: `SW_RESTORE` on activation has always shipped, and
> minimize-inactive is opt-in. Neither can alter a client's resolution.

Rejected: leaving the line as-is and treating minimize as an exception. The
line as written is already false — `window.py:78` restores a client on every
activation — and a rule contradicted by shipping code teaches the next reader
to discount it. That is worse than the rule being narrower.

Reviewers should push back here if they disagree. This is the only change in
the slice that alters a stated product constraint.

### 2. Minimize follows TriffView's ordering, including the second activation

Activate first; abort the whole minimize if activation returned false; settle;
minimize; re-activate. Ported deliberately rather than reinvented — steps 2
and 5 are exactly the failure modes that are invisible until you are cycling
six clients on real hardware.

The settle is 10 ms of dead time on the preview thread, which also pumps
hotkeys, alerts and sweeps. Accepted rather than deferred to a timer: the
handler budget is ~1.8 ms against 320 messages/s (`window.py:194`), so 10 ms
is real but bounded, and it happens only on an explicit user switch, never on
a poll. A posted delayed message would avoid the stall at the cost of splitting
one atomic switch across two pump turns, where a second switch can interleave.
Not worth it for 10 ms.

### 3. `PostMessageW`, not `SendMessageW`

TriffView uses `SendMessage`. Wingman uses `PostMessageW`, which is already
bound. `SendMessage` blocks until the target window processes the message; a
hung or loading EVE client would stall the preview thread indefinitely, taking
hotkeys, alerts and the sweep with it. `PostMessage` queues and returns.

The tradeoff: with `PostMessage` the minimize is not guaranteed to have
happened before the re-activation at step 5. In practice both land on the
client's own queue in order, so the client processes the minimize first. If
hardware shows the re-activation racing the minimize, the fallback is
`SendMessageTimeoutW` with a short timeout — not bare `SendMessage`.

### 4. Opacity dims the video only, and this differs from TriffView

TriffView sets `Opacity` on the whole WinForms overlay form
(`TriffViewSubsystem.cs:3518,3598`) — one form for every preview — so chrome,
label and video fade together, globally. Wingman has one layered window per
preview and takes the per-thumbnail route, so the border and label stay crisp
over a dimmed mirror, per preview.

Chosen because it is two lines and it is the only safe route:
`chrome.py:88-95` records that a layered window is hit-tested against its own
alpha, so putting opacity in the Pillow bitmap makes a translucent preview pass
a share of its clicks to whatever is behind it. The whole-window alternative
(`SetLayeredWindowAttributes`) was ruled out for these windows by
`docs/history/eve-preview-alerts-design.md:766`.

Consequence to state in the UI: a user arriving from TriffView will find their
labels no longer fade. Worth a word in the hint text.

### 5. Lock is per-character; the other three are global

`layout.Entry.locked` is keyed by character and there is no per-character row
on the Previews card except the keybind table. Lock therefore joins that table
as a second column rather than becoming a global checkbox, and never-minimize
joins it as a third. One table, three columns — keybind, lock, never-minimize
— against the existing `rows()` merge.

Rejected: a global "lock all previews" checkbox. It would be simpler and it
would discard the per-character flag that already persists and already works.

### 6. Live re-apply gets one new pump message

`show_labels` and `opacity` must reach already-open windows. `set_hotkeys()`
(`host.py:228-238`) is the precedent: store the desired state under the lock,
then `PostMessageW(WM_APP_REBIND)`. A new `WM_APP_RESTYLE` does the same for
chrome — the handler walks open windows, calls `redraw()` and re-issues
`_thumb.update()` with the current `label_h` and opacity.

`show_labels` also joins `_chrome_key()` (`window.py:325-331`). `opacity` does
**not** — it never changes the bitmap, only the thumbnail properties, so
adding it to the key would force pointless re-renders.

### 7. Failure handling

- A failed `activate()` aborts the minimize entirely (decision 2).
- A raise while reading any of the four settings on the preview thread falls
  back to the shipped behaviour — labels on, unlocked, opaque, no minimize —
  and logs, per `_restoring()`'s contract (`host.py:709-726`).
- A failed persist returns `{applied: True, persisted: False}` where the change
  took effect for the session, and `{applied: False}` where `update()` rolled
  the live document back, following `set_restore_preview_positions`
  (`api.py:2214`) and `_write_alert_setting` (`api.py:2024`) respectively.

## Testing and verification

Everything below runs on Linux; no Win32 call in this slice can be tested by
the suite, which is the same position every preview slice has shipped from.

- `settings.py` — the four keys survive `validated_preview`, clamp, and are not
  shared between `_preview_defaults()` calls.
- `chrome.render(label_h=0)` draws no band and no text. Pure, already testable.
- `geometry.thumbnail_rect(rect, border, 0)` reclaims the full height.
- Minimize ordering as a pure function: given (activation result, setting,
  never-minimize list, previous client) return whether to minimize. This is the
  part with real logic and it is the part that must not be reached only through
  Win32.
- Bridge contract: each new `_push` name exists in `WM.HANDLERS`
  (`test_bridge_contract.py`).
- `test_page_conventions.py` — the new controls use `.check` wrappers and the
  slider carries a label.
- A guard that `preview/win32.py` still omits the placement surface, extended
  with a note that `SC_MINIMIZE` is deliberately present.

**Hardware checks** (`docs/smoke-checklist.md`), none of which the suite can
stand in for:

- Labels off reclaims the band and the video grows into it; labels on restores
  it; both take effect on already-open previews without a restart.
- Opacity dims the mirror and leaves border and label at full strength.
- A locked preview refuses a left drag and accepts a right drag.
- Minimize-inactive: switching minimizes the previous client, the new client
  ends up foreground and stays there, and a never-minimize character is
  skipped.
- A failed activation leaves both clients where they were — no minimize.
- **A minimized client's preview keeps updating.** Minimize a client with
  visible motion — undocked, drones out, or the camera spinning — not a docked
  ship on a static scene, which looks identical whether the thumbnail is live
  or frozen on its last frame. This is the check that decides whether
  minimize-inactive is compatible with the previews it sits next to.

## Explicit exclusions

Not in this slice, and each already recorded in
`docs/history/eve-preview-design.md`:

- The rest of item 8 — label text override, position, font size, colours.
- The rest of item 10 — hide-active-preview, hide-all-on-lost-focus,
  always-maximize-on-activate, middle-click to minimize.
- `hidden_clients` (hide one character's preview entirely), snap toggle and
  distance, `hotkeys_require_eve_foreground`, border thickness and colours.
- Item 12 (named profiles), item 13 (EVE-O / EVE-X import).
- Alert `cooldown_s` / `duration_ms` / `pulses` controls. The bridge already
  accepts them (`api.py:2097`); only the UI is missing.

Permanently out: `AlwaysMaximizeClients` and `AutoRestoreClientLayouts`. Both
set a client's rect, which is the rule in decision 1 and the incident behind
it. `ClientColors` is dead config in TriffView too — declared, normalized, and
referenced nowhere else.
