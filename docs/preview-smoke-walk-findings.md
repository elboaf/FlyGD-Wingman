# Preview smoke walk — outstanding items

Findings from walking `docs/smoke-checklist.md` against a live install on
2026-08-24. Twenty-nine items were walked, two bugs were fixed in the same
branch, and the items below were **not** fixed. They are recorded here so
they are not carried as folklore.

**Test configuration.** This matters more than usual, because every defect
found was invisible in the ordinary setup:

| | |
|---|---|
| Monitors | 3, staggered tops, mixed DPI |
| | `x 0..3840, y 0..2160` @192 DPI (primary) |
| | `x 3840..6400, y 291..1731` @96 DPI |
| | `x -2560..0, y 306..1746` @96 DPI |
| Clients | up to 4 concurrent, all borderless fullscreen |
| Build | source checkout, not frozen |

The two monitors either side start ~300px below the primary's top edge.
That single fact is what exposed the placement bug, and any arrangement
with aligned tops hides it completely.

---

## 1. The client window layout feature is the wrong feature

**Severity: high. Destructive. Slated for removal.**

`restore_clients_on_launch` was meant to restore the **preview** windows to
their saved size and position. What is implemented moves the **game client**
windows, through `clientwin32.apply_placement` -> `SetWindowPlacement`.

The wanted behaviour already exists and already works by another route:
`preview/layout.py` + `preview/store.py` persist each preview tile's rect
per character and restore it on launch, with no toggle and no button.
Verified the same day — previews returned byte-identical across a restart:

```
saved                                    restored
Amelio  3363..3683 / 488..698     ->     3363..3683 / 488..698
Guarzo  3363..3683 / 698..908     ->     3363..3683 / 698..908
Isiga   3363..3683 / 908..1118    ->     3363..3683 / 908..1118
```

So the feature is redundant with something that works, and it carries a
hazard the working path does not.

### It corrupts borderless-fullscreen clients

The checklist listed the fullscreen case as *"genuinely unknown — accepted,
ignored, or a mode switch"*. It is a fourth outcome nobody listed:

**Accepted, and destructive.** The window takes the rect, `GetWindowRect`
confirms it, `apply_placement` returns true, and the log says `Restored`.
Meanwhile EVE reads the resize as a resolution change and rewrites its own
configuration. Every signal the feature reads reports success while the
client's settings are being destroyed.

This was found by doing it. Three characters' settings were ruined and all
three clients had to be exited.

### The watcher does this unattended

It is not only the two buttons. With `restore_clients_on_launch` enabled,
the watcher places each client as it appears. Observed during the session,
with no button pressed:

```
15:22:29 INFO clientlayout: Restored Guarzo Togenada to Rect(x=0, y=0, w=3840, h=2160)
15:22:33 INFO clientlayout: Restored Amelio Pellion to Rect(x=0, y=0, w=3840, h=2160)
```

The toggle defaults to `False`, which is the only reason this has not
reached users.

### Removal surface

`preview/placement.py`, `preview/clientwin32.py`, `preview/clientlayout.py`,
the `save_client_layout` / `restore_client_layout` /
`set_restore_clients_on_launch` / `start_client_layouts_if_enabled` bridge
methods, the card in `web/settings.js`, the `client_layouts` and
`restore_clients_on_launch` settings keys and their validation, the
construction in `__main__.py`, the associated tests, and the whole "EVE
client window layouts" section of the smoke checklist.

Nothing in the preview path depends on any of it — `clientlayout.py` owns
its own scheduler precisely so `host.py` never had to know about it.

**Do not touch focus switching.** Click-to-focus and the hotkeys go through
`window.py`'s `SetForegroundWindow` + `AttachThreadInput` sequence, which
only raises a window and never sets a rect. That is the one thing the app
should be doing to a game client, and it tested clean.

### Rule going forward

Wingman must never change the size, position, or resolution of an EVE game
window. Raising one to the foreground is the only permitted interaction.

---

## 2. With previews off, the Previews tab claims every chord is registered

**Severity: medium. The tab reports the opposite of the truth.**

This is the regression the checklist item *"with previews off, the Previews
tab reads as off, not as live"* exists to catch, and it is back.

Python is blameless. `Api.get_preview_hotkey_state` gates on `is_running`
and correctly returns `characters: []` and `registration: {}` once the host
has stopped, exactly as its comment says.

The defect is in `web/previews.js:55`:

```js
if (state.registration[gesture] === false) { return 'refused'; }
return null;
```

With previews off the map is empty, so the lookup yields `undefined`, not
`false`. The refused branch never runs and the chord renders as an ordinary
button. Three states are collapsed into two:

| Python sends | Means | Renders as |
|---|---|---|
| `true` | registered | normal |
| `false` | refused by Windows | warned |
| *absent* | unknown / previews off | **normal** |

Confirmed against Windows at the time — previews off, and `RegisterHotKey`
succeeded from a probe process for all four chords, so nothing held them
while the tab said they were registered:

```
previews enabled = False
Ctrl+Alt+F9   FREE - nothing holds it
Ctrl+Alt+F10  FREE - nothing holds it
Ctrl+Alt+F11  FREE - nothing holds it
Ctrl+Alt+F12  FREE - nothing holds it
```

**Fix shape:** distinguish absent from `false`. Absent means "we cannot
know" and should render as neither registered nor refused.

---

## 3. Dimming is the only "off" signal, and it says nothing when everything dims

**Severity: low-medium. Reported by the user as "I don't see anything that
indicates they are online".**

`previews.js:183` passes `state.enabled && entry.online`, so with previews
off every row is forced offline and the whole list greys at once. Dimming
only carries information by contrast with an undimmed row; a uniformly dim
list is indistinguishable from "all my characters happen to be logged off".

Combined with finding 2, the tab reads as a healthy, fully-registered bind
list at the exact moment the preview thread is gone and Windows holds
nothing.

**Fix shape:** give the list an explicit off state rather than implying it
by styling every row identically.

---

## 4. A successful Restore is indistinguishable from a no-op

**Severity: low. Moot if finding 1 is actioned.**

Pressing **Restore now** when the windows already match their saved rects
produces a correct "Restored 3 clients." and no visible change. During the
walk this read as the button doing nothing, and it was pressed four times —
each press issuing a full round of `SetWindowPlacement` calls:

```
15:12:33,847   15:12:34,240   15:12:34,516   15:12:34,753
```

Idempotent and safe, but the feedback does not distinguish "moved 3
windows" from "3 windows were already correct".

---

## Testing caveats worth carrying

**A static preview cannot be told from a dead one by pixel diffing.** The
"live video, not a frozen frame" check was done by capturing each preview
twice and diffing. One preview showed *zero* changed pixels across 8
seconds while others showed ~35%. That was a genuinely still scene — a
client parked in empty space — not a failed thumbnail. Any automated
version of this check has the same blind spot, and the checklist's stated
causes (minimised, occluded) are not the only explanations.

**From WSL, `WINGMAN_LOG_LEVEL` needs `WSLENV`.** Environment variables do
not cross into a Windows process otherwise. Without it the app starts
normally and logs nothing extra, which looks exactly like the feature being
broken. Cost one run to work out; now documented in the checklist.

---

## Not walked, and why

| Item | Reason |
|---|---|
| Frozen build renders labels in Inter | needs a build; CI already asserts the file lands, so only "does it render" is untested |
| Tab-isolated hotkey captures | needs the bookmark engine |
| Bookmark collision warning | needs the bookmark engine |
| Close every client at once | avoided — would have meant more disruption to live clients after finding 1 |
| Character list updates when the tab is opened | needs a client to start on cue |
| A state update mid-hotkey-capture | needs a client to start or stop on cue |
| A binding survives a restart while that character is logged off | not reached |
| All remaining "EVE client window layouts" items | moot if finding 1 is actioned |

`engine_exe()` is bundled-only by design — it deliberately refuses
`shutil.which()`, because an AutoHotkey v2 interpreter on PATH would parse
the v1 script into errors that read like script bugs. So a source checkout
never has it, and the two bookmark items are not walkable this way. The
interpreter is fetched at build time by `packaging/fetch_autohotkey.py`.

---

## What the three coordinate bugs have in common

Two bugs were fixed in this branch, and #23 fixed a third of the same kind
during review. All three are **unit or coordinate-space confusions that are
arithmetically invisible in the common configuration** — not Win32 API
misuse:

| Bug | Confusion | Invisible when |
|---|---|---|
| Preview default placement (this branch) | bounding rectangle treated as the union of monitors | one monitor, or aligned tops |
| Main window placement (this branch) | physical pixels handed to an API expecting logical | scaling is 100% |
| Virtual-desktop read (#23, caught in review) | read outside the DPI scope, compared against physical rects | one monitor |

That is what this subsystem is prone to. It argues for checklist items that
name the **configuration** required to observe a failure, not just the
action to perform — the two placement items added to the checklist in this
branch are written that way deliberately.
