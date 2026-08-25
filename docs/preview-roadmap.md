# EVE client previews: what is still open

The live roadmap for the preview subsystem. `docs/history/eve-preview-design.md`
is the design record — it states what was decided and why, and per
`docs/history/README.md` it is not corrected after the fact. This file is where
the record and the code have since diverged, and what is left to build.

Status as of #65. Every claim below was checked against the tree, not carried
forward from the record.

## Corrections to the record

The design document was last edited at #31 and is read as current more often
than it should be. Six of its statements no longer hold:

| The record says | Actually |
| --- | --- |
| Second slice items 7 and 8 shipped (client window placement, the placing watcher) | **Removed in #31.** Only item 9, `settings.update()`, survived — and it is now the boundary every settings writer in the package uses |
| `gestures.py` and `cycle.py` are *(deferred)* in the module table | Shipped in #26, which the same document states twelve lines later |
| Item 9 (alert flashing) is "the largest remaining chunk" | **Shipped except the render path** in #65 — see below |
| `PreviewWindow.selected` is never set | `PreviewHost` tracks `_selected_key` from the foreground hook and calls `set_selected` (#65) |
| "Every one of the thirteen client-window-layout items is also unwalked" | That checklist section was deleted with the feature in #31. Two of its three weighted items asked whether EVE accepts a forced rect — the question that destroyed three characters' settings. They are answered by deletion |
| The rebind regression test covers `save_settings` only | `save_settings` and `set_recording_dir` no longer exist. `_write_setting` is the single writer and `ui/api.py` contains no rebind at all. `save_bookmarks` is the one writer still outside the test's reach |

Two counts in the record have drifted (it says "Sixteen items" where the
checklist section holds fifteen). Counts are not repeated here — cite the
section of `docs/smoke-checklist.md`, not a number.

## Open, in rough priority order

### The alert render path — the last mile of item 9

**Highest priority, because the feature is currently inert.** #65 built
detection, parsing and configuration: `preview/alerts/{patterns,tailer,service,state}.py`,
a validated `preview.alerts` section with per-event colour, sound, duration and
pulse count, PvE filtering, persist-until-selected, the Previews-tab card, and
`PreviewHost.raise_alert` with a bounded queue drained on the pump.

`PreviewHost._apply_alerts` is a no-op. It drains the queue so `raise_alert`
cannot back up unbounded, and draws nothing. A user can enable alerts,
configure per-event colours, and observe no difference whatsoever — which is a
worse state than unshipped, because everything reports success.

`docs/smoke-checklist.md` already carries a "Cannot run until the render path
lands" section for it.

Two constraints, both load-bearing:

- **Do not re-render the Pillow bitmap at flash frequency.** `redraw()` is keyed
  and a flash would defeat the key, putting a ~67k-pixel push back on a timer —
  the cost that made dragging stutter. (The record states this at
  `eve-preview-design.md:468-471`, cited from three other documents.)
- **Pre-rendered frames are the only remaining option.** The alternative this
  file used to offer — "pulse `SetLayeredWindowAttributes` alpha" — was probed
  on 2026-08-25 and does not work. See below.

Not verifiable by the suite — no test renders a pixel. Needs hands-on testing
against real clients.

#### What the ring probe established

Run on Windows against three layered preview-shaped windows with live DWM
thumbnails, captured with `BitBlt(CAPTUREBLT)` and measured off the pixels
rather than judged by eye. This answers the two questions
`eve-preview-alerts-plan.md`'s Task 1 asked, and one it did not.

**A ring wider than the thumbnail inset renders as corner brackets. Confirmed —
the conditional inset is necessary.** Measured ring width, in pixels:

| variant | top edge | side, in the label band | side, beside the thumbnail | bottom |
| --- | --- | --- | --- | --- |
| ring 2 / inset 2 | 2 | 2 | 2 | 2 |
| ring 6 / inset 2 | 6 | 6 | **2** | **2** |
| ring 6 / inset 6 | 6 | 6 | 6 | 6 |

The thumbnail overpaints the ring everywhere it covers, so a 6 px ring inside a
2 px inset survives only along the top edge and beside the label band — four
corner blocks joined by 2 px edges, exactly as the design predicted. Task 10
keeps its inset swap on arm and clear.

**`SetLayeredWindowAttributes` cannot pulse the ring, and permanently breaks
the window if called.** All four of the plan's observations, plus the recovery
path:

- The window does not blank. It dims — chrome *and* thumbnail together and
  uniformly, so the game content dims with the ring. That is the opposite of an
  alert: the pulse would fade the thing it is trying to draw attention to.
- It still receives clicks. `WindowFromPoint` at the centre returns the preview
  before and after, so the hit region survives.
- **A subsequent `UpdateLayeredWindow` fails**, with `ERROR_INVALID_PARAMETER`
  (87), and the surface stays frozen at the dimmed image. One
  `SetLayeredWindowAttributes` call ends the window's ability to draw for the
  rest of its life.
- It is recoverable, but only by force: dropping `WS_EX_LAYERED` and re-adding
  it resets the window to per-pixel-alpha mode, after which `layered.push`
  succeeds again and the ring returns to full brightness.

### 8. Label customisation

Text override, placement (top/bottom/centre), font size, colours. `chrome.render`
already takes the label; everything else is new settings and UI. `window.py`
passes `LABEL_H = 30` and `chrome.render`'s `font_size=17` default.

### 10. Switching behaviour

Minimize-inactive-on-switch (with a never-minimize list), hide-active-preview,
hide-all-on-lost-focus, always-maximize-on-activate, middle-click to minimize a
client. Nothing exists.

**Constraint that outranks the feature list:** Wingman must never move or resize
a real EVE client window. Minimizing and activating are not resizing, but this
slice is the one most likely to drift into it. See item 11 in the record for
what happened the last time something wrote a rect to a game client.

### 12. Multiple named profiles

The settings schema was deliberately shaped so this needs no migration: today's
values are a single implicit profile, and `preview.hotkeys` is already flat for
the same reason.

### 13. EVE-O / EVE-X preview profile import

Lowest priority, largest pure-parsing job.

## Smaller gaps

- **`preview.opacity` is dead config.** Stored and clamped to 20–255
  (`settings.py`), read by nothing: `window.py` calls `self._thumb.update(rect)`
  at both call sites, so it defaults to 255. **This entry used to say it "must"
  go through `SetLayeredWindowAttributes`. That is wrong, and the ring probe
  above is why:** that call permanently disables `UpdateLayeredWindow` on the
  window, which is the preview's only means of drawing its own chrome. Wire it
  through the thumbnail's own opacity instead — `Thumbnail.update` already takes
  `opacity` and already sets `DWM_TNP_OPACITY`, so this is passing a value that
  is presently hardcoded to the default. Putting it in the Pillow bitmap's alpha
  remains wrong for the original reason: a layered window is hit-tested against
  its alpha channel, so that reintroduces click-through.

  It also **does not** collide with the alert render path, which this file
  previously claimed it did. They touch different surfaces — thumbnail opacity
  dims the game content, the ring frames repaint the chrome around it — so
  neither has to compose with the other and they can land in either order.

- **Lock previews has no UI.** The plumbing is complete — `layout.Entry` carries
  `locked`, it survives a restart, right-drag overrides it — but nothing sets
  it. One checkbox, but it crosses the bridge (new `Api` method, `previews.js`,
  `index.html`), and nothing in the suite renders the page, so it lands
  unverified until someone opens it by hand.
- **Border thickness and colour are constants.** `chrome.render` takes `border`
  and `border_color`; `window.py` passes `BORDER = 2` and a literal
  `(0, 200, 220, 255)`. The third member of this group, `selected`, is done.

## Left behind by #26 (preview hotkeys)

Small enough to fold into whichever slice next touches the file. The record
lists these; these are the ones still live.

- **`cycle.ordered()` sorts case-sensitively** — still `sorted(set(keys))`, so
  `"Bob"` precedes `"alice"`. Deterministic and stable, which is all the cycle
  logic needs. Item 8 is the slice that will care. Note it is a **user-visible
  ordering change**: anyone already using cycle chords gets a different "next
  client" the day it changes.
- **The cycle anchor and the cycle order come from different places.**
  `_on_hotkey` scans `_clients` for the foreground HWND; order comes from
  `characters()`. Two sources for one decision; unify when item 10 touches
  switching.
- **`preview/host.py`'s "settings.save() is lock-serialised" comment is stale.**
  Writers go through `settings.update()` now. The conclusion it draws — writing
  from the preview thread is safe — still holds.
- **`settings.update()`'s rollback has a one-bytecode hole.** A `BaseException`
  landing between `data.clear()` and `data.update(before)` leaves the document
  empty, while the docstring promises an unconditional restore. Worth a
  docstring caveat, not a redesign.
- **Planner-dropped duplicate chords never appear in registration status**, so
  Python cannot say which of two identical bindings lost. The UI detects
  duplicates client-side, so nothing is currently invisible to the user.
- **Nothing pins that the defaults are fixed points of their own validators.**
  `validated_preview(_preview_defaults()) == _preview_defaults()` and its
  `eve_bookmarks`/`eve_settings` twins are the invariant that makes normalising
  on every save safe from drift. It holds; it is untested — and #65 widened it
  by adding the whole `preview.alerts` tree to what it must hold across.

## Cheap and unblocked

Three of the above need no verification and no design: the stale `host.py`
comment, the `settings.update()` docstring caveat, and the fixed-point test.
The test is the one with real value — it is pure, Linux-testable, and nothing
currently catches a default that its own validator rewrites.

## Verification still outstanding

The suite cannot tell you a preview appeared on screen, so most of this
feature's assurance comes from `docs/smoke-checklist.md`. These have not been
exercised by anyone:

- Closing one client mid-session — its preview disappears within ~1s while the
  others keep rendering and do not jump.
- Closing every client — no previews, no crash, the app still responsive.
- Starting a client while Wingman runs — a preview appears, at its saved
  position if that character had one.
- A never-previewed character logging in alongside placed ones — it should get a
  free slot rather than landing on top of an existing preview.
- The frozen build rendering labels in Inter. The font is a `datas` entry and
  PyInstaller exits 0 when one resolves to nothing; there is a post-build
  assertion, but nobody has looked at the packaged app.
- The "EVE preview hotkeys" section, of which `WM_HOTKEY` reaching a
  message-only window is the one that matters: documented behaviour, not
  measured, and if it fails the whole dispatch path moves to `hWnd=NULL`.

**Mixed-DPI multi-monitor placement outlives the checklist section that was
deleted with #31.** It passes on a single monitor whether or not the code is
correct — which is how a virtual-desktop read taken outside the DPI scope
survived ten reviews. Wingman still places windows across mixed-scale monitors;
they are its own previews now.

## Still open from "Risks and open questions"

- **`SetThreadDpiAwarenessContext` is Windows 10 1607+.** Confirm against
  Wingman's supported floor.
- **Thumbnail count is unmeasured.** Probes ran 2; users run 10–30. DWM cost per
  thumbnail is unknown, and it bears on the sweep interval.
- **Occlusion between topmost windows.** With TriffView also running, z-order
  among `WS_EX_TOPMOST` windows is arbitrary. Not a defect — it means running
  both simultaneously is not a supported configuration.
