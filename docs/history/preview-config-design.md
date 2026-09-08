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

> **Superseded for switching behavior.** This document records the original
> minimize-inactive proposal, including its synchronous minimize sequence.
> The shipped activate-first, `SW_SHOWMINNOACTIVE` design and its Windows smoke
> acceptance criteria live in `docs/preview-switch-performance-design.md`.
> Its settings/storage decisions remain historical context; do not revive its
> switching sequence or update this record in place.

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

**But `preview.layouts` cannot store a lock on its own.** `layout.deserialize`
requires `x`, `y`, `w` and `h` and `continue`s past any entry missing one
(`layout.py:44-52`), and `validated_preview` rebuilds the section through it on
every write (`settings.py:413`). A lock written against a character who has
never dragged their preview is therefore discarded by the very next save — the
checkbox would appear to work and silently forget. This is why decision 5 puts
`locked` in its own list rather than in the layout entry.

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

**The click path activates before the host hears about it.** `PreviewWindow`
calls `activate(self._libs, self.client.hwnd)` and *then* `self._on_activate`
(`window.py:468-469`), and the host passes `on_activate=lambda c: None`
(`host.py:418`). By the time any host code runs, the foreground has already
moved and the previous client is unrecoverable. Minimize-inactive needs that
value, so activation ownership has to move — see decision 2a.

**A hand pass is a release gate, not a nicety.** `PRODUCT.md:143-144` — "Nothing
in the repository executes the page, so every UI change needs a hand pass
against `docs/smoke-checklist.md`" — and `CLAUDE.md:104-106` says to treat the
checklist as part of the change. Adding items to the checklist is not the same
as running them.

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
> Exactly two show-state calls are exempt, and no others: `SW_RESTORE` on
> activation, already shipped, and minimize, for the opt-in
> minimize-inactive setting. Maximize is NOT exempt — `SW_SHOWMAXIMIZED`
> fills the window to the work area, the same geometry hazard in
> show-state clothing.

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

### 2a. Activation moves into the host

`PreviewWindow` currently owns the click-path activation: it calls `activate()`
itself and then fires a callback the host has stubbed out
(`window.py:468-469`, `host.py:418`). The window therefore decides *and*
performs the switch, while the host — which knows the foreground, the roster
and the settings — learns nothing until it is over.

`PreviewWindow` stops calling `activate()`. `on_activate` becomes a real host
callback that owns the whole sequence below, matching the hotkey path, which
already runs in the host (`host.py:576`). The window's job narrows to
classifying the gesture, which is what `drag_result()` already does
(`window.py:35-45`).

Rejected: having the window capture `GetForegroundWindow()` before activating
and pass it out. Smaller, but it leaves two activation call sites to keep in
step and puts a policy decision — whether to minimize — behind a value the
window has no other use for. The host already owns the hotkey path; one owner
is worth the move.

This is the largest structural change in the slice and the one most likely to
regress click-to-focus, which is the preview subsystem's primary interaction.

### 3. `SendMessageTimeoutW`, not `PostMessageW` and not `SendMessageW`

TriffView uses bare `SendMessage` (`TriffViewSubsystem.cs:956`). Wingman cannot:
`SendMessage` blocks until the target processes the message, so a hung or
loading EVE client would stall the preview thread indefinitely, taking hotkeys,
alerts and the sweep with it.

`PostMessageW` — already bound (`win32.py:306`) — avoids the stall but does not
order against step 5. An earlier draft of this design claimed the two "land on
the client's own queue in order"; that is wrong. The minimize is posted to the
*previous client's* queue, while `activate()` calls `SetForegroundWindow`
directly from Wingman's thread (`window.py:77-98`). They share no queue and
there is no ordering between them, so the re-activation can land before the
minimize is processed — exactly the foreground-theft that step 5 exists to
prevent.

`SendMessageTimeoutW` with `SMTO_ABORTIFHUNG` and a short timeout (100 ms) gets
the ordering without the unbounded stall: it returns when the client has
processed the minimize, or gives up. A timeout is treated as "the minimize did
not happen" and logged; the client stays where it is, which is the safe
outcome.

Cost: a new bind in `preview/win32.py`, and up to 100 ms on the preview thread
on top of the 10 ms settle, on an explicit user switch only.

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

### 5. Lock is per-character, stored in its own list

`layout.Entry.locked` is keyed by character and there is no per-character row
on the Previews card except the keybind table. Lock therefore joins that table
as a second column rather than becoming a global checkbox, and never-minimize
joins it as a third. One table, three columns — keybind, lock, never-minimize
— against the existing `rows()` merge.

**Lock does not write to `preview.layouts`.** As recorded in the constraints
above, `layout.deserialize` drops any entry without a full rect
(`layout.py:44-52`), so a lock on a character who has never dragged their
preview would not survive the next save. `locked` becomes its own list under
`preview`, alongside `never_minimize`, deserialized by `roster.deserialize`
like the other two character lists.

`layout.Entry.locked` stays as it is and keeps being honoured — the host
resolves a window's lock from the list at creation and hands it to
`PreviewWindow` exactly as it does today (`host.py:427`). Nothing in the drag
path changes.

Rejected: synthesizing the character's current rect on a lock write so the
layout entry validates. It would work for a running client and fail for an
offline one, which is precisely the case the roster exists to serve
(`roster.py:3-5`) — a user binding an alt that flies on weekends.

Rejected: a global "lock all previews" checkbox. Simpler, and it would discard
the per-character flag that already persists and already works.

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
- A `SendMessageTimeoutW` timeout is treated as "the minimize did not happen",
  logged at INFO, and changes nothing else — the client stays where it is.
- A raise while reading any of the settings on the preview thread falls
  back to the shipped behaviour — labels on, unlocked, opaque, no minimize —
  and logs, per `_restoring()`'s contract (`host.py:709-726`). This covers all
  five live-read callables, `minimize_inactive_clients` and `never_minimize`
  included, not only the two that affect chrome.
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
stand in for. **These are a release gate, not documentation.** `PRODUCT.md:143`
requires a hand pass for every UI change, and this slice cannot ship on a green
suite alone:

- Labels off reclaims the band and the video grows into it; labels on restores
  it; both take effect on already-open previews without a restart.
- Opacity dims the mirror and leaves border and label at full strength.
- A locked preview refuses a left drag and accepts a right drag — **including
  a character who has never dragged their preview**, which is the case the
  layout-keyed storage could not serve.
- **Click-to-focus still works**, on every preview, after activation moved into
  the host (decision 2a). This is a regression check on the subsystem's primary
  interaction, not a new-feature check.
- Minimize-inactive: switching minimizes the previous client, the new client
  ends up foreground and stays there, and a never-minimize character is
  skipped.
- A failed activation leaves both clients where they were — no minimize.
- **A minimized client's preview keeps updating.** Minimize a client with
  visible motion — undocked, drones out, or the camera spinning — not a docked
  ship on a static scene, which looks identical whether the thumbnail is live
  or frozen on its last frame. This is the check that decides whether
  minimize-inactive is compatible with the previews it sits next to, and it
  blocks the merge: a frozen result sends the feature back to the user for a
  decision, per the plan's adaptation points.

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
