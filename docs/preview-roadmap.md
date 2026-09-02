# EVE client previews: what is still open

The live roadmap for the preview subsystem. `docs/history/eve-preview-design.md`
is the design record — it states what was decided and why, and per
`docs/history/README.md` it is not corrected after the fact. This file is where
the record and the code have since diverged, and what is left to build.

Status as of #65. Every claim below was checked against the tree, not carried
forward from the record.

### Named cycle groups — shipped

Character groups with named forward-only cycle keybinds and scope-aware
history are complete. The All forward and All back rows remain the implicit
cycle-all fallback and are backward-compatible with settings files that have
no groups. Multiple group membership, backward group cycle keys, group-specific
preview geometry, and EVE-O/EVE-X profile import remain open (see items 12 and
13 below).

## Corrections to the record

The design document was last edited at #31 and is read as current more often
than it should be. Six of its statements no longer hold:

| The record says | Actually |
| --- | --- |
| Second slice items 7 and 8 shipped (client window placement, the placing watcher) | **Removed in #31.** Only item 9, `settings.update()`, survived — and it is now the boundary every settings writer in the package uses |
| `gestures.py` and `cycle.py` are *(deferred)* in the module table | Shipped in #26, which the same document states twelve lines later |
| Item 9 (alert flashing) is "the largest remaining chunk" | **Shipped** — everything but the render path in #65, the render path since — see below |
| `PreviewWindow.selected` is never set | `PreviewHost` tracks `_selected_key` from the foreground hook and calls `set_selected` (#65) |
| "Every one of the thirteen client-window-layout items is also unwalked" | That checklist section was deleted with the feature in #31. Two of its three weighted items asked whether EVE accepts a forced rect — the question that destroyed three characters' settings. They are answered by deletion |
| The rebind regression test covers `save_settings` only | `save_settings` and `set_recording_dir` no longer exist. `_write_setting` is the single writer and `ui/api.py` contains no rebind at all. `save_bookmarks` is the one writer still outside the test's reach |

Two counts in the record have drifted (it says "Sixteen items" where the
checklist section holds fifteen). Counts are not repeated here — cite the
section of `docs/smoke-checklist.md`, not a number.

## Open, in rough priority order

### The alert render path — the last mile of item 9

**Built.** #65 delivered detection, parsing and configuration:
`preview/alerts/{patterns,tailer,service,state}.py`, a validated
`preview.alerts` section with per-event colour, sound, duration and pulse
count, PvE filtering, persist-until-selected, the Previews-tab card, and
`PreviewHost.raise_alert` with a bounded queue drained on the pump. What was
missing was the drawing, and `PreviewHost._apply_alerts` was a no-op — a user
could enable alerts, configure colours, and observe no difference whatsoever,
which is worse than unshipped because everything reported success.

`preview/alertframes.py` now pre-renders one DIB per pulse phase and the host
pushes them on an 80ms timer that runs only while something is armed.
**Nothing in the suite renders a pixel, so this is verified by
`docs/smoke-checklist.md`'s "The alert render path" section and not by CI.**

Two constraints, both load-bearing:

- **Do not re-render the Pillow bitmap at flash frequency.** `redraw()` is keyed
  and a flash would defeat the key, putting a ~67k-pixel push back on a timer —
  the cost that made dragging stutter. (The record states this at
  `eve-preview-design.md:468-471`, cited from three other documents.) The same
  rule is why a resize mid-alert *invalidates* the frame cache and lets the
  next tick rebuild it, rather than rebuilding per `WM_MOUSEMOVE`.
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

**Partly done in #87:** labels can be switched off (`preview.show_labels`,
and `PreviewWindow._label_h()` returns 0 when they are). Still open: text
override, placement (top/bottom/centre), font size, colours. `chrome.render`
already takes the label; everything else is new settings and UI. `window.py`
passes `LABEL_H = 30` and `chrome.render`'s `font_size=17` default.

Anything here that changes the band's HEIGHT has to invalidate the alert
frame cache the way the on/off toggle already does — the frames bake the
band in, so a preview alerting while the height changes would keep flashing
the old geometry until the alert cleared (`PreviewWindow.arm_alert`'s
staleness check).

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

- **`preview.opacity` is wired** (#87), through `Thumbnail.update`'s
  `DWM_TNP_OPACITY` — `window.py` passes `self.opacity` at all three call
  sites now.

  This entry used to say opacity "must" go through
  `SetLayeredWindowAttributes`. **That would have broken previews outright**,
  and the ring probe above is why: one such call permanently disables
  `UpdateLayeredWindow` on that window, which is the preview's only means of
  drawing its own chrome. #87 took the thumbnail route independently and is
  correct; the claim is recorded here because it survived in this file long
  enough to have been followed.

  This entry also used to say that putting opacity in the Pillow bitmap's
  alpha "remains wrong … a layered window is hit-tested against its alpha
  channel, so that reintroduces click-through." **That holds at alpha 0 and
  nowhere else**, and taking it to mean every value is what left the slider
  shipping a dim preview rather than a translucent one for two releases.
  `DWM_TNP_OPACITY` alone cannot produce translucency: DWM composites the
  thumbnail over `chrome.render`'s own interior fill, so lowering the
  opacity blended the game content toward near-black instead of revealing
  the desktop. Measured on Windows, red backdrop, thumbnail at opacity 128:

  | interior alpha | sampled pixel | `WindowFromPoint` |
  | --- | --- | --- |
  | 255 (as shipped) | (4, 5, 135) — backdrop invisible | preview |
  | 1 | (126, 0, 128) — clean 50/50 over the backdrop | preview |
  | 0 | (127, 0, 128) | the window behind — click-through |

  So `chrome.render` now punches the thumbnail's own rect down to
  `THUMBNAIL_ALPHA = 1`: see-through where DWM draws, opaque everywhere the
  chrome is actually visible, and still hit-testable everywhere. The hole is
  derived from `geometry.thumbnail_rect`, so it cannot drift from the
  destination rect `window.py` hands DWM.

  Opacity still never collided with the alert render path, which this file
  once claimed it did. They touch different surfaces — thumbnail opacity
  fades the game content, the ring frames repaint the chrome around it —
  which is why they landed independently and in the opposite order to the
  one this file warned about.

- **A DWM thumbnail stretches to fill `rcDestination`; it does not preserve
  the source aspect ratio.** Measured with two solid-colour windows, a 2:1
  and a 4:1 source into a 1:1 destination, with a `fVisible=False` control:
  the picture filled the destination in every case. So a preview whose
  shape does not match its client has never letterboxed — it has been
  showing the game **distorted**. This is the third claim about this API
  to have read plausibly, gone unverified, and been followed; see the
  `SetLayeredWindowAttributes` and thumbnail-alpha entries above.

- **Lock previews has a UI** (#87): `previews.js` drives `set_preview_locked`
  per character.
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
