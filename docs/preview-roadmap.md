# EVE client previews: what is still open

The live roadmap for the preview subsystem. `docs/history/eve-preview-design.md`
is the design record — it states what was decided and why, and per
`docs/history/README.md` it is not corrected after the fact. This file is where
the record and the code have since diverged, and what is left to build.

Status as of #178 (`4848fbf`). Every claim below was checked against the tree,
not carried forward from the previous revision of this file, which stopped at
#65. The designs and plans for the work that shipped in between are records
now: `docs/history/preview-config-{design,plan}.md` (#87, #88),
`preview-sizing-plan.md` (#127), `preview-switch-performance-design.md` (#121,
#141), `preview-direct-activation-design.md`, `preview-cycle-groups-{design,plan}.md`
(#145), `previews-character-table-{design,plan}.md`,
`preview-layout-continuity-copy-plan.md` and `preview-smoke-walk-findings.md`.
`docs/preview-sizing-design.md` and the cropped-preview documents
(`preview-evolution-crops-design.md`, `preview-crop-prototype-results.md`,
`preview-crops-production-results.md`) stay in `docs/` because `ui/api.py` and
the manual harness cite them.

## Shipped since #65

Listed once so the open items below can be read without the record.

| Feature | Where |
| --- | --- |
| Labels on/off, opacity, per-character lock, minimize-inactive-on-switch | #87, #88 — `preview.show_labels`, `preview.opacity`, `preview.locked`, `preview.minimize_inactive_clients` in `settings._preview_defaults()` |
| Ring moves on the switch, not the next sweep | #116 |
| Minimize first, activate second, no window animation | #121 (`preview/switching.py` is the pure policy) |
| Left click switches on the way down, right drag moves | #123 (`preview/gestures.py`) |
| Uniform and manual sizing, aspect lock, ring colour, EVE-O button grammar, name overlay | #127 — `preview.width/height`, `preview.lock_aspect`, `preview.selection_color`; `geometry.lock_to_aspect` |
| Responsive switching | #141 |
| Named cycle groups | #145 — `preview.hotkeys.groups[]`, each `{id, name, cycle}` |
| Never-minimize list, hide every preview on lost focus | `preview.never_minimize`, `preview.hide_on_lost_focus` (`preview/visibility.py` is the pure decision) |
| Per-character placement continuity and geometry copy | `preview.layouts`, `copy_preview_layout` |
| Cropped previews: prototype, then persistent per-character crops | #162, #174 — `preview.crops`, `preview/crops.py`, `cropstore.py`, `cropcontroller.py`, `cropwindow.py`, `croppicker.py` |
| The alert render path | see below; `preview/alertframes.py`, `PreviewHost` `ALERT_MS = 80` |
| The defaults-are-a-fixed-point test this file asked for | `tests/test_settings_preview.py::test_the_preview_defaults_are_a_fixed_point_of_their_own_validator` |

Alert detection itself moved house: the modules this file used to name as
`preview/alerts/{patterns,tailer,service,state}.py` are `wingman/alerts/`
(`patterns`, `state`, `service`, `sound`) and the tailer became the shared
gamelog stream in `wingman/telemetry/gamelogs.py`, feeding one coordinator
that previews, the fleet bar and fleet sharing all subscribe to.

## Corrections to the record

The design document was last edited at #31 and is read as current more often
than it should be. Six of its statements no longer hold:

| The record says | Actually |
| --- | --- |
| Second slice items 7 and 8 shipped (client window placement, the placing watcher) | **Removed in #31.** Only item 9, `settings.update()`, survived — and it is now the boundary every settings writer in the package uses |
| `gestures.py` and `cycle.py` are *(deferred)* in the module table | Shipped in #26, which the same document states twelve lines later |
| Item 9 (alert flashing) is "the largest remaining chunk" | **Shipped** — detection and configuration in #65, the render path after it — see below |
| `PreviewWindow.selected` is never set | `PreviewHost` tracks `_selected_key` from the foreground hook and calls `set_selected` (#65) |
| "Every one of the thirteen client-window-layout items is also unwalked" | That checklist section was deleted with the feature in #31. Two of its three weighted items asked whether EVE accepts a forced rect — the question that destroyed three characters' settings. They are answered by deletion |
| The rebind regression test covers `save_settings` only | `save_settings` and `set_recording_dir` no longer exist. `_write_setting` is the single writer and `ui/api.py` contains no rebind at all. `save_bookmarks` no longer rebinds the settings object either; the re-aimed regression test in `tests/test_api_settings_fields.py` asserts the object survives a per-field write |

Two counts in the record have drifted (it says "Sixteen items" where the
checklist section holds fifteen). Counts are not repeated here — cite the
section of `docs/smoke-checklist.md`, not a number.

## Open, in rough priority order

### The alert render path — the last mile of item 9

**Built.** #65 delivered detection, parsing and configuration: a validated
`preview.alerts` section with per-event colour, sound, duration and pulse
count, PvE filtering, persist-until-selected, the Alerts card, and
`PreviewHost.raise_alert` with a bounded queue drained on the pump. What was
missing was the drawing, and `PreviewHost._apply_alerts` was a no-op — a user
could enable alerts, configure colours, and observe no difference whatsoever,
which is worse than unshipped because everything reported success.

`preview/alertframes.py` now pre-renders one DIB per pulse phase and the host
pushes them on an 80ms timer (`ALERT_MS`) that runs only while something is
armed. **Nothing in the suite renders a pixel, so this is verified by
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

What is still open here is only verification: no test renders a pixel, and the
checklist section has to be walked by hand against real clients after any
change to `alertframes.py`, `chrome.py` or the window's inset handling.

#### What the ring probe established

Run on Windows against three layered preview-shaped windows with live DWM
thumbnails, captured with `BitBlt(CAPTUREBLT)` and measured off the pixels
rather than judged by eye. This answers the two questions
`docs/history/eve-preview-alerts-plan.md`'s Task 1 asked, and one it did not.
`preview/alertframes.py`, `chrome.py` and `window.py` cite this section for the
numbers; keep the tables.

**A ring wider than the thumbnail inset renders as corner brackets. Confirmed —
the conditional inset is necessary.** Measured ring width, in pixels:

| variant | top edge | side, in the label band | side, beside the thumbnail | bottom |
| --- | --- | --- | --- | --- |
| ring 2 / inset 2 | 2 | 2 | 2 | 2 |
| ring 6 / inset 2 | 6 | 6 | **2** | **2** |
| ring 6 / inset 6 | 6 | 6 | 6 | 6 |

The thumbnail overpaints the ring everywhere it covers, so a 6 px ring inside a
2 px inset survives only along the top edge and beside the label band — four
corner blocks joined by 2 px edges, exactly as the design predicted.
`PreviewWindow._inset` swaps between `BORDER` and `ALERT_BORDER` on arm and
clear for this reason.

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

**Partly done in #87:** labels can be switched off (`preview.show_labels`).
Still open: text override, placement (top/bottom/centre), font size, colours.
`chrome.render_label` already takes the label and a `font_size` that defaults
to `chrome.LABEL_FONT = 17`; everything else is new settings and UI.

Anything here that changes the band's HEIGHT has to invalidate the alert
frame cache the way the on/off toggle already does — the frames bake the
band in, so a preview alerting while the height changes would keep flashing
the old geometry until the alert cleared (`PreviewWindow.arm_alert`'s
staleness check).

### 10. Switching behaviour

**Mostly shipped.** Minimize-inactive-on-switch with a never-minimize list
(#87, `preview.never_minimize`), hide-all-on-lost-focus
(`preview.hide_on_lost_focus`), minimize-first activation without the window
animation (#121) and responsive switching (#141) are in. Still open:
hide-the-active-character's-own-preview, always-maximize-on-activate, and
middle-click to minimize a client — no setting, gesture or policy exists for
any of the three (`preview/gestures.py` knows left and right only).

**Constraint that outranks the feature list:** Wingman must never move or resize
a real EVE client window. Minimizing and activating are not resizing, but this
slice is the one most likely to drift into it. See item 11 in the record for
what happened the last time something wrote a rect to a game client.

### Cycle groups — what #145 left open

Groups carry one forward `cycle` chord each. Multiple group membership,
backward group cycle keys, and group-specific preview geometry remain open.
The All forward and All back rows stay the implicit cycle-all fallback and are
backward-compatible with settings files that have no groups.

### 12. Multiple named profiles

Still open. The settings schema was deliberately shaped so this needs no
migration: today's values are a single implicit profile, and `preview.hotkeys`
is already flat for the same reason. Note that "profiles" elsewhere in the app
(#151, the Profiles route) means EVE settings folders, not preview layouts;
the word is taken, so this feature needs another name in the UI.

### 13. EVE-O / EVE-X preview profile import

Lowest priority, largest pure-parsing job. Nothing exists.

## Smaller gaps

- **`preview.opacity` is wired** (#87), through `Thumbnail.update`'s
  `DWM_TNP_OPACITY`.

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

  So `chrome.render` punches the thumbnail's own rect down to
  `THUMBNAIL_ALPHA = 1`: see-through where DWM draws, opaque everywhere the
  chrome is actually visible, and still hit-testable everywhere. The hole is
  derived from `geometry.thumbnail_rect`, so it cannot drift from the
  destination rect `window.py` hands DWM.

- **A DWM thumbnail stretches to fill `rcDestination`; it does not preserve
  the source aspect ratio.** Measured with two solid-colour windows, a 2:1
  and a 4:1 source into a 1:1 destination, with a `fVisible=False` control:
  the picture filled the destination in every case. **Addressed twice since:**
  `preview.lock_aspect` with `geometry.lock_to_aspect` (#127) keeps the
  window the client's shape, and cropped previews (#162, #174) let the user
  choose which part of the client fills it instead. A preview with the lock
  off and no crop still shows the game distorted, by choice.

- **Lock previews has a UI** (#87): `previews.js` drives `set_preview_locked`
  per character.
- **Ring colour is a setting** (`preview.selection_color`, #127);
  `PreviewWindow._border_color()` falls back to `(0, 200, 220, 255)` when it
  is unset. **Border thickness is still a constant**, `window.BORDER = 2`.

## Left behind by #26 (preview hotkeys)

Small enough to fold into whichever slice next touches the file. The record
lists these; these are the ones still live, and the ones since closed.

- **`cycle.ordered()` sorts case-sensitively** — still `sorted(set(keys))`, so
  `"Bob"` precedes `"alice"`. Deterministic and stable, which is all the cycle
  logic needs. Item 8 is the slice that will care. Note it is a **user-visible
  ordering change**: anyone already using cycle chords gets a different "next
  client" the day it changes.
- **The cycle anchor and the cycle order come from different places.** The
  anchor is found by scanning the live clients for the foreground HWND; order
  comes from the character list. Two sources for one decision; unify when
  item 10 next touches switching. (Unverified against HEAD beyond the
  `cycle.step` "anchor has gone" handling in `host.py`.)
- **`preview/host.py`'s "settings.save() is lock-serialised" comment** — gone;
  the file no longer mentions `settings.save()`.
- **`settings.update()`'s rollback has a one-bytecode hole.** Still there: a
  `BaseException` landing between `data.clear()` and `data.update(before)`
  leaves the document empty, while the docstring promises an unconditional
  restore. Worth a docstring caveat, not a redesign. The docstring does not
  carry the caveat yet.
- **Planner-dropped duplicate chords.** The planner now drops a duplicate on
  purpose and says so in place: Windows would refuse the second registration
  anyway, and dropping it at plan time keeps the reported status honest about
  which binding lost. The UI still detects duplicates client-side, so nothing
  is invisible to the user.
- **Nothing pins that the defaults are fixed points of their own validators** —
  closed for previews by
  `test_the_preview_defaults_are_a_fixed_point_of_their_own_validator`. The
  `eve_bookmarks` / `eve_settings` twins this file asked for are unverified
  against HEAD.

## Cheap and unblocked

One of the three remains: the `settings.update()` docstring caveat. The stale
`host.py` comment is gone and the fixed-point test exists.

## Verification still outstanding

The suite cannot tell you a preview appeared on screen, so most of this
feature's assurance comes from `docs/smoke-checklist.md`. These remain
unchecked there:

- Closing one client mid-session — its preview disappears within ~1s while the
  others keep rendering and do not jump.
- Closing every client — no previews, no crash, the app still responsive.
- Starting a client while Wingman runs — a preview appears, at its saved
  position if that character had one.
- A never-previewed character logging in alongside placed ones — it should get a
  free slot rather than landing on top of an existing preview (the checklist
  now also covers the mixed-DPI variant of this).
- The frozen build rendering labels in Inter. The font is a `datas` entry and
  PyInstaller exits 0 when one resolves to nothing; there is a post-build
  assertion, but nobody has looked at the packaged app.
- The "EVE preview hotkeys" section, of which `WM_HOTKEY` reaching a
  message-only window is the one that matters: documented behaviour, not
  measured, and if it fails the whole dispatch path moves to `hWnd=NULL`. The
  checklist marks it load-bearing and unwalked.

**Mixed-DPI multi-monitor placement outlives the checklist section that was
deleted with #31.** It passes on a single monitor whether or not the code is
correct — which is how a virtual-desktop read taken outside the DPI scope
survived ten reviews. Wingman still places windows across mixed-scale monitors;
they are its own previews now. The preview thread is per-monitor-DPI-aware
while the rest of the process is system-DPI-aware, and that split is an open
question in its own right, not closed by the aspect-lock work.

## Still open from "Risks and open questions"

- **`SetThreadDpiAwarenessContext` is Windows 10 1607+.** `host.py` calls it
  on the pump thread; `packaging/installer.iss` declares no `MinVersion`, so
  the supported floor is still undeclared. Confirm one and declare it.
- **Thumbnail count is unmeasured.** Probes ran 2–3; users run 10–30. DWM cost
  per thumbnail is unknown, and it bears on the sweep interval. Cropped
  previews (#174) add a second DWM relationship per cropped character, which
  makes the question more pressing, not less.
- **Occlusion between topmost windows.** With TriffView also running, z-order
  among `WS_EX_TOPMOST` windows is arbitrary. Not a defect — it means running
  both simultaneously is not a supported configuration. The checklist says the
  same where it notes TriffView would hide the previews.
