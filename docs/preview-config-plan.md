# Preview configuration options — plan

Task list for `preview-config-design.md`. Ordered so each task leaves the suite
green and the app runnable. Tasks 1–6 are the three already-built settings and
carry no Win32 risk. Task 9 is a standalone refactor with no behaviour change.
Tasks 7, 8, 10 and 11 are minimize-inactive, the only part that touches a game
window. Tasks 13–14 gate the merge.

Baseline on branch `worktree-preview-config-options`: 2205 passed, 6 skipped.

---

## Task 1 — Settings keys

`wingman/settings.py`

Add to `_preview_defaults()`:

```python
"show_labels": True,
"minimize_inactive_clients": False,
"never_minimize": [],
"locked": [],
```

`opacity` already exists. `locked` is a list of character names, **not** a flag
inside `preview.layouts` — `layout.deserialize` drops any entry without a full
rect (`layout.py:44-52`), so a lock on a character who has never dragged their
preview would not survive the next save. See decision 5 of the design.

In `validated_preview()`, coerce `show_labels` and `minimize_inactive_clients`
with the `isinstance(..., bool)` guard the existing keys use
(`settings.py:205`), and run `never_minimize` and `locked` through
`preview_roster.deserialize` — both are character-name lists with exactly the
roster's constraints, including the `hwnd:` rejection.

Defaults chosen: labels **on** (what shipped; off would silently restyle every
existing install), minimize **off** (it changes what happens to game windows
and must be asked for), both lists empty.

**Verify:** `tests/test_settings_preview.py` — round-trip, clamping, and
`_preview_defaults()` not shared between calls. Add a test that a `locked`
entry for a character with **no** `preview.layouts` rect survives a
`validated_preview` round-trip — the exact case the layout-keyed storage
could not.

---

## Task 2 — `show_labels` through the render path

`wingman/preview/window.py`

`chrome.py` is not edited — `label_h=0` already yields a bandless tile
(`chrome.py:107-108`).

- `PreviewWindow` gains `show_labels: bool = True`, set from the host.
- A `_label_h()` helper returning `LABEL_H if self.show_labels else 0`.
- Use it at all three sites: `:321` and `:382` (`thumbnail_rect`) and the
  `chrome.render(label_h=...)` call at `:349`.
- Add `self.show_labels` to `_chrome_key()` (`:325-331`), or toggling it does
  nothing to an open window.

Both halves are required and each looks like it works alone: without the key
the bitmap never repaints; without the `thumbnail_rect` change the video stays
inset in a band that is no longer drawn.

**Verify:** `chrome.render(..., label_h=0)` produces no band and no text;
`geometry.thumbnail_rect(rect, border, 0)` reclaims the full height.

---

## Task 3 — `opacity` through the thumbnail

`wingman/preview/window.py`

- `PreviewWindow` gains `opacity: int = 255`.
- Pass it at `:321` and `:382`: `self._thumb.update(rect, self.opacity)`.
- Do **not** add it to `_chrome_key()` — it never changes the bitmap.

**Verify:** a fake `Thumbnail` records the opacity it was handed.

---

## Task 4 — Host: live-read seams and the restyle message

`wingman/preview/host.py`, `preview/win32.py`,
`wingman/__main__.py`

- `PreviewHost.__init__` takes `show_labels`, `opacity`,
  `minimize_inactive_clients`, `never_minimize` and `locked` callables
  alongside the existing `restore_positions`, read through guarded helpers in
  the shape of `_restoring()` (`host.py:709-726`) — a raise falls back to
  labels-on, opaque, no-minimize, nothing-locked, and logs. All five, not just
  the two that affect chrome.
- **Define and pass all five in `build_preview_host`**
  (`__main__.py:366-391`), beside `restore_positions`. That function is the
  only place these reach the host; a callable defined in `host.py` alone is
  never wired to anything. Follow `restore_positions`' comment exactly — read
  through `state`, which keeps its identity, never through a captured
  `preview` section, because `_normalize` replaces that object on every write.
- New `WM_APP_RESTYLE` in `win32.py` beside the existing `WM_APP_*`.
- `restyle()` — public, safe from any thread, `PostMessageW` like
  `set_hotkeys()` (`host.py:228-238`). This is the single live-update entry
  point for **all** of these settings, minimize included; there is no separate
  "minimize equivalent".
- Its handler walks open windows, sets `show_labels` / `opacity` / `locked`
  from the callables, calls `redraw()`, and re-issues `_thumb.update()` with
  the current label height and opacity. `minimize_inactive_clients` and
  `never_minimize` are read per switch, so they need no window walk.
- Apply all of it at creation in `_sweep`, so a preview that appears later is
  born with the current settings rather than the defaults.

**Verify:** `tests/test_preview_wiring.py` — a callable that raises leaves
labels on, opacity 255, and no minimize, and does not propagate. Assert
`build_preview_host` passes all five, in the shape of the existing test that
records what a lazily-resolved lambda cost last time (`__main__.py:383-386`).

---

## Task 5 — Bridge: three global endpoints

`wingman/ui/api.py`

Generalise `_write_alert_setting` (`:2024-2070`) to `_write_preview_setting`,
rooted at `preview` rather than `preview.alerts` — same nested-path descent
inside `settings_mod.update`, same no-op guard, same stale-reference warning
(`_normalize` reassigns `preview` wholesale, so the path is walked fresh both
times). Reimplement `_write_alert_setting` on top of it with
`("alerts", *path)` so there is one writer, not two.

Then:

- `set_preview_show_labels(enabled) -> dict`
- `set_preview_opacity(value) -> dict`
- `set_minimize_inactive_clients(enabled) -> dict`

Each writes, then calls `host.restyle()` so the change is live before the page
hears back — one entry point for all of these settings, defined in Task 4.
Clamping stays in `validated_preview` — `set_alert_event`'s docstring
(`:2097`) is explicit that the endpoint must not re-own a range that settings
already defines.

**Verify:** `tests/test_api_preview.py` — each returns `{applied, persisted}`,
each is a no-op when the value is unchanged, and an `OSError` from `update()`
is reported per decision 7 of the design.

---

## Task 6 — UI: Labels and Opacity

`web/index.html`, `web/settings.js`

Into the existing "EVE client previews" card, under the Enable row:

- **Labels** — `.check` wrapper (a bare input renders as a white Win32 widget
  on a dark card), "Show the character name on each preview".
- **Opacity** — a range input, 20–255, committing on `change` not `input`;
  discrete controls commit on change (`DESIGN.md:280`). Hint should say the
  border and label stay at full strength, since that differs from TriffView.

Follow `settings.js:458-500` for the commit shape, including the
previews-are-off dependence note.

**Verify:** `test_page_conventions.py`; the `?dev=1` harness renders the card
at 840×625 with no horizontal scroll.

---

## Task 7 — Minimize decision as a pure function

`wingman/preview/switching.py` (new)

```python
def should_minimize(*, enabled, activated, previous_key, next_key, never):
    """Whether to minimize the previously-active client after a switch."""
```

Returns False when the feature is off, when `activated` is False, when there is
no previous client, when previous and next are the same, or when the previous
character is in `never`.

The whole of the logic lives here, testable on Linux. `host.py` keeps only the
Win32 calls and the ordering. New module, so add it to
`[tool.setuptools] packages` if it lands as a subpackage — it does not, but the
rule is worth re-reading before assuming (`CLAUDE.md`).

**Verify:** a table test over all six False paths plus the True path.

---

## Task 8 — Win32 surface

`wingman/preview/win32.py`

Declare `WM_SYSCOMMAND = 0x0112`, `SC_MINIMIZE = 0xF020`, and
`SMTO_ABORTIFHUNG = 0x0002`, and bind `SendMessageTimeoutW`. Per decision 3:
`PostMessageW` does not order against the re-activation, and bare
`SendMessageW` can stall the pump on a hung client — it is deliberately **not**
bound.

Comment must name why this is here and why it is not the call the guard test
forbids: it changes show state, never geometry.

**Verify:** `tests/test_preview_wiring.py:465` still passes unchanged, and gains
an assertion that `SC_MINIMIZE` **is** present with a comment explaining the
distinction, so a future purge does not sweep it up by association. Add a
matching assertion that `SendMessageW` is absent — the bind list is where that
choice would silently erode.

---

## Task 9 — Activation moves into the host

`wingman/preview/window.py`, `preview/host.py`

**This is the structural change and it must land before Task 10.** Today
`PreviewWindow` activates and then fires a callback the host has stubbed:
`activate(self._libs, self.client.hwnd)` followed by `self._on_activate(...)`
(`window.py:468-469`), against `on_activate=lambda c: None` (`host.py:418`).
The host cannot see the previous foreground because the switch is already over.

- `PreviewWindow` stops calling `activate()`. It classifies the gesture — which
  `drag_result()` already does (`window.py:35-45`) — and calls `_on_activate`.
- The host supplies a real `on_activate` that performs the switch, matching the
  hotkey path which already lives there (`host.py:576`).
- Both paths then converge on the one sequence in Task 10.

Land this **on its own**, with no behaviour change: after this task, clicking a
preview still just focuses its client. That keeps the click-to-focus regression
separable from the minimize feature if the smoke pass finds one.

**Verify:** injected fake `user32` — a click still activates exactly once, and
the host callback receives the client. `tests/test_preview_wiring.py` gains a
guard that `window.py` no longer calls `activate(` in its message handler, so
a later change cannot quietly restore two owners.

---

## Task 10 — Host: the switch sequence

`wingman/preview/host.py`

One helper, used by both paths now that Task 9 has unified them:

1. Record the previous foreground client before activating.
2. `activate()` the target. **If it returns False, stop here** — no minimize.
3. `should_minimize(...)`; if False, done.
4. Sleep 10 ms (`SWITCH_SETTLE_MS`), matching TriffView's constant.
5. `SendMessageTimeoutW(prev.hwnd, WM_SYSCOMMAND, SC_MINIMIZE, 0,
   SMTO_ABORTIFHUNG, 100)`. A timeout logs at INFO and skips step 6 — the
   client stays where it is.
6. `activate()` the target a second time.

Steps 2 and 6 are the whole point; comment them with what breaks without each
(dropping to desktop on a failed switch; the minimize stealing foreground back).

**Verify:** injected fake `user32` — assert the call order, that a False
activation sends nothing, that a timeout skips the re-activation, and that a
never-minimize character is skipped.

---

## Task 11 — UI: the per-character table gains two columns

`web/index.html`, `web/previews.js`

`rows()` (`previews.js:37-55`) already merges running clients, `roster.seen`,
and any character carrying a binding, with the `Object.create(null)` guard.
Reuse it unchanged; add two controls per row:

- **Lock** — writes membership in `preview.locked`, **not** into
  `preview.layouts` (Task 1, decision 5). This is what makes the control work
  for a character who has never dragged their preview.
- **Never minimize** — writes membership in `preview.never_minimize`,
  and is disabled with an explanatory hint while minimize-inactive is off.

Two new bridge endpoints, `set_preview_locked(name, locked)` and
`set_never_minimize(name, enabled)`, both through `_write_preview_setting`,
both followed by `host.restyle()` — lock is read per drag
(`window.py:416`), so the live `PreviewWindow.locked` has to be refreshed.

The minimize checkbox goes in the same card, above the table.

**Verify:** `test_bridge_contract.py`; a character named `__proto__` still
appears; locking an offline character round-trips; the table fits at 840 CSS px.

---

## Task 12 — `PRODUCT.md`

Replace the first bullet of "What it must not become" (`:105`) with the
geometry-based rule from decision 1 of the design. This is the only change in
the slice that alters a stated product constraint, and it should be reviewed on
its own terms rather than as a mechanical edit.

---

## Task 13 — Smoke checklist

`docs/smoke-checklist.md`

Add the eight hardware checks from the design's verification section. The two
that matter most, and the ones most easily faked by a careless pass:

> **Click-to-focus still works.** Every preview, after activation moved into the
> host (Task 9). A regression check on the subsystem's primary interaction.

> **A minimized client's preview keeps updating.** Minimize a client with
> visible motion — undocked, drones out, or the camera spinning. A docked ship
> on a static scene looks identical whether the thumbnail is live or frozen on
> its last frame.

---

## Task 14 — Run the smoke pass

**This is a task, not a formality, and it gates the merge.** `PRODUCT.md:143`
requires a hand pass for every UI change; `CLAUDE.md:104-106` says to treat the
checklist as part of the change. Nothing in this slice has ever run against a
real client, which is the position every preview slice has shipped from — the
difference is that this one restructures click-to-focus.

Run every item added in Task 13 on the testrun desktop. Two outcomes are not
"note it and continue":

- **Click-to-focus regressed** → Task 9 is wrong; fix before anything else.
- **A minimized client's preview froze** → stop. The feature goes back to the
  user for a decision per the adaptation points below. Do not ship it with a
  hint and hope.

Record the result. A slice that merges without this having run is the failure
mode `PRODUCT.md:143` exists to prevent.

---

## Task 15 — Ship

- `uv run --extra dev ruff check .` and `ruff format --check .` (CI gates on
  the latter).
- Full suite on Linux; CI covers windows-latest.
- Move `preview-config-design.md` and `preview-config-plan.md` from `docs/` to
  `docs/history/` and add the row to its index table
  (`docs/history/README.md`). They live in `docs/` while the work is live
  because `docs/history/README.md` declares its contents "records, not
  instructions" — an active plan is an instruction, and filing it there before
  it ships invites exactly the confusion that note guards against.
- `my:polish-core --fix`, inspect, re-run.
- PR to `elboaf` from the `guarzo` fork, `gh -R` passed explicitly.

---

## Adaptation points

- **If a minimized client's preview goes blank or freezes**, minimize-inactive
  is incompatible with the feature it sits beside. Tasks 7, 8, 10 and 11 stop;
  the setting either ships with an explicit warning in its hint or is dropped,
  and that is the user's call, not the implementer's. Task 9 stands either way
  — it changes no behaviour and leaves one owner for activation. Bench
  observation so far says the preview stays live, but the discriminating check
  (Task 13, run in Task 14) has not been run.
- **If `SendMessageTimeoutW` times out routinely** rather than exceptionally,
  100 ms is too short for a loaded client — raise it, or reconsider whether
  step 6 is needed at all on this hardware. Do not switch to bare
  `SendMessageW`.
- **If click-to-focus regresses after Task 9**, that task is wrong and nothing
  downstream of it is trustworthy. It is deliberately landed alone and with no
  behaviour change so this is separable.
- **If 10 ms of settle is visible** as a hitch while cycling, move the tail of
  the sequence onto a posted delayed message and accept that a second switch
  can interleave.
