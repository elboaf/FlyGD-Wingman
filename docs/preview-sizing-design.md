# Preview sizing: aspect lock, numeric size, snap toggle, reset

Four changes to how a preview's rectangle is decided.

## Intended outcome

A preview can be made to match its client's shape exactly (drag), sized to an
exact number (type), placed without magnetism (toggle), or put back (reset).

## What the probe established, and what it overturned

**DWM stretches a thumbnail to fill `rcDestination`. It does not preserve the
source aspect ratio.** Measured on Windows with two solid-colour windows, a
2:1 and a 4:1 source drawn into a 1:1 destination, with a `fVisible=False`
control to prove the capture was aimed correctly:

| source | destination | picture height | letterbox predicts | stretch predicts |
| --- | --- | --- | --- | --- |
| 400x200 (2:1) | 300x300 | 300px | 150px | 300px |
| 480x120 (4:1) | 300x300 | 300px | 75px | 300px |
| control, hidden | 300x300 | 0px (all background) | -- | -- |

This design was drafted on the opposite premise -- that a mismatched preview
letterboxes, wasting pixels. It does not. It **distorts**: the game is
squashed or stretched, so ship shapes, overview proportions and target
brackets are all subtly wrong on a window whose entire purpose is
at-a-glance recognition.

The feature survives and is worth more than when it was proposed. Only the
user-facing wording changes: every warning speaks of a stretched picture,
never of black bars.

Recorded because `docs/preview-roadmap.md` already carries two DWM claims
that read plausibly, went unverified, and were followed --
`SetLayeredWindowAttributes` as a pulse mechanism, and the thumbnail-alpha
claim that "left the slider shipping a dim preview rather than a translucent
one for two releases". This is the third. The probe was throwaway and is not
committed; this table is the artifact.

## Repository evidence

- **A global default preview size already exists and is live.**
  `preview.width` / `preview.height` (`settings.py:88-89`), validated with
  floors of 120/90 (`settings.py:253-256`, exactly `window.MIN_SIZE`), read at
  `__main__.py:415` into `PreviewHost(size=...)`, consumed by `_resolve_rect`
  -> `default_stack` (`host.py:942`). It has no user interface.
- **`self._size` is a construction snapshot** (`host.py:153`), unlike
  `show_labels`, `opacity`, `locked` and `restore_positions`, which are
  callables read live (`__main__.py:400-411`).
- **Cross-thread calls carry no payload.** `PostMessageW` takes integers
  only, so the established shape is: stash the value in a field under
  `self._lock`, post a bare signal (`host.py:167-172`, `set_hotkeys` at
  `284-295`, `_post` at `275`).
- **Reset has two states to clear.** `self._saved` is an in-memory mirror
  kept current within a session so a restarted client returns to its dragged
  position (`host.py:240-248`).
- **`LayoutStore` forbids wholesale replacement by design** (`store.py`
  docstring): a wholesale write deletes every offline character's position.
- **`move()` already invalidates the alert frame cache on resize**
  (`window.py:602-629`), so a programmatic resize inherits that.
- **The process is `PROCESS_SYSTEM_DPI_AWARE`** (`__main__.py:154`).
- **`WM.prompt(title, body, value)`** resolves to text or `null`, has exactly
  one input, sets its body with `textContent`, labels OK as "Set", answers on
  Enter and cancels on Escape (`panel.js:373-398`).
- **A snap toggle is a recorded deferred item**, together with a snap
  distance (`docs/preview-config-design.md:352`). The distance is
  `geometry.snap`'s `threshold=12`.

## Decisions

**D1. Sizes are window rects, not picture rects.** `preview.width`/`height`
already mean window pixels and are floored at `MIN_SIZE`; `preview.layouts`
persists window rects; dragging produces window rects. One vocabulary across
all four, and no migration on a live key. The cost is that a typed round
number is not exactly the client's ratio once chrome is subtracted, which the
dialog answers by naming the exact number that is.

*Alternative rejected:* picture rects, which would have made the typed ratio
directly comparable to the client's, at the price of two size vocabularies in
one feature.

**D2. The aspect lock is unconditional on the drag handle**, with no
modifier and no setting. The numeric field is the deliberate escape hatch.

**D3. Reset re-places at `self._size`, not a literal `DEFAULT_SIZE`.** The
configured default already exists and is already what unsaved previews use.

**D4. Snap distance stays deferred.** A toggle was asked for; a slider for a
12px pull is a control nobody tunes.

**D5. The aspect maths uses `BORDER`, never the live `_inset`.** An armed
alert widens the inset to `ALERT_BORDER`; reading it live would make a
preview change shape when a neighbour is shot at.

## Observable behaviour

**Resize.** The handle keeps the picture at its client's shape. The lock
applies to the picture area, not the window: the window is the picture plus
`BORDER * 2` horizontally and `BORDER * 2 + LABEL_H` vertically. Both drag
axes stay live. Precisely: subtract the chrome to get the candidate picture
size, take `pw = max(candidate_pw, candidate_ph * aspect)`, derive
`ph = pw / aspect`, then add the chrome back. Taking the max rather than
driving from width alone is what makes a mostly-vertical drag do anything.
`MIN_SIZE` is applied after the ratio correction, so the floor cannot
distort it either. A client with no readable client rect -- at character
select, or gone mid-drag -- falls back to today's freeform resize rather
than freezing.

**Size...** A per-row button beside `Edit...`, opening `WM.prompt` with the
current window size as its default text. Accepts `1280x720`, tolerant of
spaces, `X` and `x`. Anything else is refused the way a bad keybind is.
Empty is a no-op identical to Cancel. A shape that does not match the client
is accepted -- that is the escape hatch -- and the hint says what it costs
and what the alternative is. Both numbers are computed when the dialog
opens, from the row's current width and the client's rect:

> Your client is 1920x1080. At this width an undistorted preview is
> 640x392; a different shape will stretch the picture.

The chrome is `(4, 34)` -- `BORDER * 2` and `BORDER * 2 + LABEL_H` -- so a
640-wide window holds a 636-wide picture, and 636 at 16:9 needs 358 of
picture, hence 392 of window. Worked through here because getting it wrong
is silent: the preview simply renders slightly stretched.

For an offline character there is no client to compare against, the hint says
so, and the size is written to the saved layout for next time.

**Snapping.** A checkbox in the Previews card, on by default, matching
today's behaviour exactly. Off means a dragged preview goes where the pointer
puts it. Resize is unaffected: it does not snap today, and a snap pulling one
edge would fight the ratio holding the other.

**Reset all previews.** A `.btn.danger` button in the Previews card behind a
`WM.confirm`. Clears every saved layout and re-places open previews down the
rightmost monitor exactly as a first run would. Locks, never-minimize and
keybinds survive: they are preferences, not placement, and already live in
separate lists.

## Architecture

**Pure, and therefore tested in CI:**

- `geometry.parse_size(text)` -- returns `(w, h)` or `None`. Same contract as
  `gestures.parse`: no exceptions, no clamping.
- `geometry.lock_to_aspect(w, h, aspect, chrome, min_size)` -- the freeform
  candidate in, the ratio-corrected window size out. `chrome` is the
  `(BORDER * 2, BORDER * 2 + LABEL_H)` pair, passed in rather than imported,
  so the window/picture conversion lives in one tested function instead of
  being open-coded at three call sites.
- `window.resize_result` gains `aspect=None` and delegates. `None` reproduces
  today's rect exactly.

**Where the aspect is read.** `PreviewWindow._source_aspect()` -- one
`GetClientRect` on `self.client.hwnd`, already bound at `win32.py:276`. Read
**once, at `WM_LBUTTONDOWN`**, cached beside `_start_rect` for the drag. Not
per `WM_MOUSEMOVE`: that handler has a documented stutter history and a
`WINGMAN_PREVIEW_PERF` harness built to measure it, and a syscall per mouse
move is the cost that harness exists to catch. A degenerate rect yields
`None`.

**The snap flag rides the existing live-settings channel.** `PreviewWindow`
gains a `snap` attribute set by `host._restyle` beside `show_labels`,
`opacity` and `locked` -- no new push, and it inherits the property that a
settings change reaches open previews immediately.

**Two new posted messages**, `WM_APP_RESIZE_ONE` and `WM_APP_RESET_LAYOUTS`,
beside the four at `win32.py:69-72`. The resize payload -- a stable key and a
size -- travels in a field under `self._lock`, because `PostMessageW` carries
integers only. This is `set_hotkeys`' shape exactly.

**Reset clears three things, in this order**, on the preview thread:

1. Cancel the store's pending debounce. A drag that ended under a second ago
   has an unwritten entry in `_pending`; without this it fires after the
   clear and resurrects exactly one preview's old position, intermittently.
2. Clear the persisted `preview.layouts`, via a new `LayoutStore.clear()`
   that writes inside the same `update_settings()` context manager, under
   `_SAVE_LOCK`. Not a new call site doing a read-then-save pair, and not
   `record()` -- the store's first rule is merge-per-key-never-wholesale, and
   this is the one operation that legitimately needs the opposite.
3. Clear `self._saved` and re-place every open window through
   `_resolve_rect`. Without this the next sweep re-places from memory.

A reset landing mid-drag is left alone: the button-up writes the old rect
back. Rare, self-correcting on the next reset, and cheaper to accept than to
add a cancel path through the capture state machine.

**Bridge surface.** Three `Api` methods, all returning
`{applied, persisted, error}`:

- `set_preview_snap(bool)` -- one line through
  `_write_preview_setting(("snap",), ...)` plus `restyle()`, identical in
  shape to `set_preview_show_labels`.
- `set_preview_size(name, w, h)` -- writes the layout entry, and resizes the
  live window if one exists. An offline character is
  `applied: False, persisted: True`, reported as "saved; takes effect when
  that client is next running" rather than as a failure.
- `reset_preview_layouts()` -- the sequence above.

`get_preview_hotkey_state`'s payload gains a `sizes` map so the dialog can
open with the current numbers and compare against the client's shape. No new
`_push` name, so the bridge allowlist is untouched.

## Data model and compatibility

One new key, `preview.snap`, defaulting to `True` -- which is today's
behaviour, so no install changes on upgrade and no `defaults_version` bump is
warranted. A `bool` coercion in `validated_preview` beside
`restore_preview_positions`.

`preview.width`/`height` are **not** given a UI in this slice. They are
correct as they stand and reset now honours them; exposing them would first
require converting `PreviewHost`'s `size` from a construction snapshot into a
live callable, which is a separate change with its own testable behaviour.
Recorded so the next slice does not rediscover it.

No layout schema change: `layout.Entry` already carries `w` and `h`.

## Web layer

- `style.css`: `#preview-binds` goes to
  `grid-template-columns: repeat(6, max-content) minmax(0, 1fr)`, and the
  comment naming the five children is updated to six. That comment is
  load-bearing -- it is the only place the count is explained.
- `previews.js`: `makeRow` appends `Size...`; the cycle-row branch appends
  **three** filler spans, not two. `.row { display: contents }` means the
  grid cannot tell one row from the next, so a row short by one cell pulls
  the following row's children into the gap.
- `Size...` calls `endCapture()` before `WM.prompt`. This is mechanically
  enforced: `test_page_conventions.py:511-534` asserts `endCapture()` within
  400 characters above every `WM.prompt(` in this file.
- Commit shape follows the row controls already there: patch `state` in place
  on success, guarded by the `pushes` counter so a save resolving after a
  newer table has landed does not write into a stale render.
- `index.html`: a `.check`-wrapped checkbox and a `<button class="btn danger">`
  in the Previews card. `.btn.danger` is the only destructive treatment and
  `linkbtn danger` is asserted to have zero users
  (`test_page_conventions.py:743`). `#section-previews` currently has no
  buttons, so there is no accent conflict.
- `settings.js`: two blocks following `restore-preview-positions` verbatim,
  including the previews-off dependence note.
- `dev.js`: the fake payload gains `sizes` and `preview.snap`, or the `?dev=1`
  harness renders a page missing the controls being measured.

The confirm follows the house pattern -- short verb-phrase title, body naming
the irreversibility (`bookmarks.js:391`, `settings.js:401`) -- and quotes no
count, because derived numbers must be derived or test-asserted rather than
retyped.

## Verification

**CI can prove:** `parse_size` (whitespace, `X`, junk, zero, negative,
absurd); `lock_to_aspect` (both drag axes, the minimum applied after
correction, `aspect=None` reproducing today's rect); `resize_result`
delegating; the snap bypass; `LayoutStore.clear()` cancelling a pending
debounce. Plus the existing lexical guards staying green.

Also added, because this slice makes it cheap and
`docs/preview-roadmap.md` names it as unguarded: `validated_preview
(_preview_defaults()) == _preview_defaults()`, the fixed-point invariant that
makes normalising on every save safe from drift.

**CI cannot prove, and the smoke checklist must:** that the aspect lock
produces an undistorted picture against a real client; that the resize feel
is right; that six tracks fit at 840x625. The first two are Windows-only
against live clients. The third is checked in the `?dev=1` harness and
measured, not reasoned about.

**Nothing in the suite renders the page.** A handler that throws takes every
registration below it down silently and the screen loads as an inert copy of
itself. `docs/smoke-checklist.md` gains steps for all four behaviours, and
the screen is assumed broken until opened by hand.

## Assumptions that may change

- `GetClientRect` equals the thumbnail's source area under
  `SOURCECLIENTAREAONLY`. Probably identical; unconfirmed. If it is not, the
  lock will be consistently off by the difference and the fix is to measure
  the source rather than the window.
- "Larger of the two implied sizes" is the right resize rule. It is the
  standard way to keep both axes live, and it can feel grabby. A feel
  question, answerable only by dragging it.
- Typed pixels are physical at system DPI. Correct, and probably surprising
  on a scaled display; the hint says "pixels".

## Explicit exclusions

Per-preview snapping; snapping during resize; modifier-key overrides;
per-row reset; a UI for `preview.width`/`height`; snap distance; any change
to `host._restyle`, which was already fixed in #92. And the standing rule
throughout: Wingman never moves or resizes a real EVE client window.
