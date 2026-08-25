# Preview alerts

Design. Base: `main` (be43305), 2026-08-25. Implements deferred item 9 of
`eve-preview-design.md`, and the half of item 10 that the border work needs.

## Outcome

When a player shoots one of your clients, scrambles it, or decloaks it, that
client's preview pulses in a colour that says which of the three happened, and
a sound plays. The pulse keeps going until you switch to that client. The
preview you are looking at carries a thin ring; the others carry none, so a
pulsing preview is the only coloured ring on the screen.

The parent design calls this "the largest remaining chunk", and it is the last
thing in the port that changes what previews are *for*: without it a preview is
something you look at, and with it a preview is something that tells you to
look.

Most of what it needs is already here and unwired. `chrome.render` already
takes `border_color`, `border` and `selected` and is pure and CI-tested
(`preview/chrome.py:63-89`). `combatlog.find_gamelogs_dir()` already locates the
log folder (`combatlog.py:88-95`) and `gamelogs_dir` is already a persisted,
validated setting with a picker and an auto-detect behind it
(`settings.py:75`, `:293-294`, `ui/api.py:1322-1366`). The preview thread
already owns a real `GetMessage` pump (`preview/host.py:238-240`) and an
`HWND_MESSAGE` window that outlives every preview so there is always a valid
`PostMessageW` target (`:242-287`).

What does not exist at all: any reading of a log *body*, any per-preview
foreground state, any sound, and any preview settings UI beyond two checkboxes.

**What "no border" actually looks like.** `INTERIOR_BG = (8, 10, 14, 255)` is
opaque and load-bearing — a layered window is hit-tested against its own alpha,
so a transparent pixel is click-through and drag breaks (`chrome.py:22-30`). The
DWM thumbnail is inset by the border width (`geometry.py:76-87`) and does not
cover it. So an unselected preview does not render as a borderless rectangle of
game video; it renders with a near-black frame the width of the inset. Against a
dark desktop that reads as nothing, which is the intent. Against bright game
content behind it, it is a visible dark edge. That is the honest description and
the hand pass should judge it.

## Decisions taken before designing

Six questions were settled first, because each changes the shape of the rest.

**Three events, not TriffView's seven.** `combat`, `warp_scramble`, `decloak`.
TriffView also ships `fleet_invite` and `convo_request`, which are social rather
than tactical and fail PRODUCT.md's audience test — this is a toolkit for
flying several accounts through wormhole space, not for managing invitations.
It also ships `system_change`, which was considered and dropped: unlike the
other three it fires on something *you just did*, so it is confirmation rather
than warning, and it wants a quieter treatment that would have been the only
exception in the table.

**`attack` and `attack (miss)` are one event.** TriffView splits them because
the two log lines look nothing alike — a damage line matches on the colour code
`0xffcc0000`, a miss on the literal `misses you`. That is a parsing detail. A
pilot being shot at and missed is being shot at. Two matchers, one event.

**`warp_scramble` stays separate from `combat`.** TriffView's own cooldowns are
the evidence: 1 s for attack, 8 s for scramble. Merged under one cooldown either
the scramble drowns inside a continuous combat pulse, or the combat alert
arrives eight seconds into the fight. They are also different decisions —
"I am taking damage" and "I cannot leave" produce different reactions — which
is the argument for letting them have different colours.

**An alert never touches a game window.** No `SetForegroundWindow`, no bring to
front, no taskbar flash. PRODUCT.md's hard line is about moving and resizing,
but focus-stealing falls under "it must not automate gameplay": a client pulled
to the foreground mid-fight takes the keystrokes you were sending to a different
ship. TriffView's alert path never calls it either. This is a rule, not an
omission.

**The NPC filter ships on, and gates `combat` and `warp_scramble` both.**
Sleeper sites are core wormhole activity and put every client running one under
continuous NPC fire. Sleepers and Drifters also apply warp disruption routinely,
so filtering only `combat` would leave any site producing a continuous,
persistent, top-severity scramble alert on every client — the exact failure the
filter exists to prevent. `decloak` is not filtered because its line carries no
attacker source to test; the corpus must confirm that.

**Persistence ships on.** An alert that expires after 1200 ms while you are in
a browser has told you nothing, and "you were not looking" is the entire case
for the feature. This is the default most likely to want flipping after real
use; see `defaults_version` under Settings.

## Behaviour

**Selection.** The foreground window is tracked. If it belongs to a known EVE
client, that client's preview is selected and draws a 2 px ring; every other
preview draws nothing. If the foreground window is anything else — a browser,
Discord, Wingman itself — *no* preview is selected and no preview has a ring.

Selection is deliberately the real foreground and not "the last EVE client you
used". Sticky highlighting was rejected for two reasons: an alert on the client
you last touched could not be told apart from the highlight, and acknowledgement
would clear alerts you never actually saw.

**Alerts.** A matched log line raises an alert against the character whose log
produced it. That character's preview arms: a 6 px ring in the event's colour,
pulsing from alpha 110 to 255 over 1200 ms in three pulses, and a sound. The
ring is drawn whether the preview is selected or not.

A live alert of higher severity is never replaced by a lower one — the lower
event **extends the expiry** and leaves the colour alone. A higher-severity
event arriving over a live lower one **replaces it outright**, which rebuilds
the frame cache mid-pulse. An **equal-severity** event — the common case, since
a fight produces a combat line every server tick — restarts the pulse from phase
zero and re-stamps the expiry, leaving the colour and the frame cache untouched.
With a 1 s combat cooldown against a 1200 ms pulse that means a sustained fight
pulses continuously without ever completing a cycle, which is the intended
reading of "still being shot". Ranks are `warp_scramble` 3, `combat` 2,
`decloak` 1.

Note that under the shipped default the extend half of that rule is inert: with
`persist_until_selected` on there is no expiry to extend, so a lower-severity
event over a live higher one does nothing at all. The rule matters only when
persistence is off, and it is written down so that turning persistence off does
not quietly change which colour is showing.

**Persistence and acknowledgement.** With `persist_until_selected` on, an alert
does not expire on its own. It clears when either of two things happens:

- that client becomes the selected one — you switched to it; or
- **you click its preview**, whether or not the click succeeded in raising the
  client.

The second is not decoration. `window.py:102-116` already records that Windows
refuses a foreground change from a process that has not had recent user input,
and calls it the expected top field complaint. Acknowledging only on real
foreground would mean that every time activation is refused, the ring pulses
forever and clicking it does nothing — the alert becomes unclearable by the one
gesture the user will try. Clicking is the signal that you looked.

An alert armed on a client that is *already* selected is not persistent, because
you are looking at it.

**Cooldowns** are keyed `(character, event)` and stamped **in the service, when
the line matches**, before the alert is handed to the preview thread. A
suppressed event is invisible everywhere — no state change, no sound, no
history.

An earlier draft had the cooldown stamped only once an alert was actually
applied to a preview. That is not implementable across this boundary: the
service posts to the pump and learns nothing about delivery, and whether a
preview exists is knowable only on the pump thread. Making it work would need a
delivery acknowledgement travelling back, and would have to move sound onto the
pump thread to keep it gated — which the design deliberately avoids. So the
cooldown stays wholly inside the service, and the accepted cost is that an event
arriving when no preview can show it still burns the window. The cases where
that happens are narrow: the host mid-restart, or a client that has just closed.

| Event | Cooldown | Severity | Colour | Sound |
|---|---|---|---|---|
| `combat` | 1 s | 2 | `#ff4d4d` | chime |
| `warp_scramble` | 8 s | 3 | `#ffd24d` | bell |
| `decloak` | 8 s | 1 | `#4dd2ff` | chime |

All three: 1200 ms, three pulses.

## Architecture

Three new modules under `obs_youtube_uploader/alerts/`, split on the line CI
enforces — CI is `ubuntu-latest` and every module must import cleanly on Linux
(`eve-preview-plan.md:13-28`).

`alerts` must be added to `pyproject.toml:71-77`. The failure mode is documented
at `:67-70`: a missing entry installs cleanly and fails at import time in the
built artifact, not in the checkout.

### `alerts/patterns.py` — pure, Linux-testable

Line in, `(event, source)` or `None` out. No I/O, no Win32, no clock. This is
where the whole parse lives and where the test suite does its real work.

All tests are on the lowercased line except the two extraction regexes:

```
combat        = ("(combat)" and "0xffcc0000" and "from</font>")
                or ("(combat)" and "misses you")
warp_scramble = "warp scramble attempt" | "warp disruption attempt"
                | "warp disruption zone"
decloak       = "(notify)" and "cloak deactivates"
```

Source extraction needs the `<font>` regex and its stripped-text fallback, plus
`strip_markup` — drop tags, collapse whitespace, discard everything up to the
first `] ` so the timestamp does not reach the NPC test.

`is_likely_npc(source)`: true when the source contains none of `[ ] ( )` and no
`'s `. Player attackers carry a corp ticker in brackets and a hull in parens;
player drones carry `'s`; NPCs are a bare name. It is applied to `combat` and
`warp_scramble`. `decloak` has no attacker source, so there is nothing to test.

**This heuristic is ported on trust and must be validated before it ships.** It
now gates whether a persistent alert fires at all, so a false negative means you
are not told you are being attacked. It is also unclear whether a scramble line
even yields a source through the `<font>` path, since its shape differs from the
damage line. Neither repository contains sample log bodies. See Testing.

### `alerts/tailer.py` — the watcher thread

Polls; there is no `FileSystemWatcher` in the standard library and
`eve-preview-plan.md:24` forbids new runtime dependencies. TriffView polls at
1 s anyway as a belt-and-braces layer under its watcher, so this is its
mechanism without its optimisation.

Two cadences: `stat()` tracked files every **1 s**, rescan the directory for new
ones every **5 s**. One second of latency on "you are being shot" does not
change the decision the alert exists to prompt.

Three rules ported because each exists for a reason:

- Ignore files whose mtime is older than **12 hours**. Bounds the working set on
  a machine with months of logs.
- Open a pre-existing file at `size`, not at 0. Without this, ticking Enable
  replays this morning's fight as a burst of alerts. A file that appears *while*
  running starts at 0, because it is live.
- Cap the tracked set at **64**, ordered mtime-descending, and applied **after**
  header filtering. All three qualifiers matter. `combatlog.py:48-50` records
  that character-less stubs are 47% of a real folder, so a cap applied before
  filtering is half-consumed by files that can never produce an alert; and an
  unordered cap drops live logs at random. TriffView's 200 is generous and ten
  is too tight — six clients that each relog once inside twelve hours is already
  twelve real logs before stubs. The symptom of getting this wrong is silent:
  some characters simply never alert.

Character attribution reuses `combatlog.parse_header()` (`combatlog.py:44-79`)
for the `Listener:` line, with TriffView's two guards: `Listener: EVE` is
rejected as not a character, and where one character has several logs the newest
`Session Started` wins.

Robustness that bites if skipped: buffer a trailing partial line until its
newline arrives, since a read can land mid-write; if size drops below the stored
position the file rotated and position resets to 0; decode UTF-8 with
`errors="replace"` so one bad byte cannot kill the thread.

The uploader's own `combatlog.build_archive` (`combatlog.py:287-334`) reads
these same files while the tailer holds them open. Read-sharing makes that
benign on Windows, but the rotation rule must not misfire on anything the
archiver does.

### `alerts/service.py` — cooldowns and dispatch

Owns the cooldown map, applies the NPC filter, plays the sound, and posts to the
preview thread.

**It reads settings live, through a callable, never through a captured
subtree.** `settings.py:373-378` states the rule: `_normalize` reassigns
`data["preview"]` wholesale on every call, so a reference held to an inner dict
across an `update()` goes stale — hold `data`, not `data["preview"]`. The
service needs per-event `enabled`, `cooldown_s`, `color` and `sound` plus the
two global toggles at event time, on the tailer thread, and anything captured at
construction is reading an orphaned dict after the first settings write. The
established pattern is `__main__.py:369-379`'s `restore_positions` callable,
whose comment says exactly this.

`import winsound` is **deferred, not module-scope** — CI is `ubuntu-latest` and
a top-level import fails collection. `evewindows.py:1-14` is the pattern
(`eve-preview-plan.md:32`).

`winsound.PlaySound(path, SND_FILENAME | SND_ASYNC)` returns immediately; one
sound preempts another, which is TriffView's accepted behaviour and saves any
mixing. Called from this thread, off the pump, as discipline.

**Sound files resolve through `paths.bundle_dir()`** (`paths.py:88-98`), not
through `Path(__file__).parent`. They live in `assets/sounds/` and need a new
`datas` entry in `packaging/uploader.spec` whose destination matches what
`bundle_dir()` resolves — `uploader.spec:32-36` records that the `web/`
destination was chosen for precisely that reason.

Do **not** copy `chrome.py`'s font handling as the precedent. It resolves
`Path(__file__).resolve().parent.parent / "assets" / "fonts"`
(`chrome.py:17-19`) → `<_MEIPASS>/obs_youtube_uploader/assets/fonts/`, while
`uploader.spec:63` collects to `assets/fonts` → `<_MEIPASS>/assets/fonts/`.
Those disagree, and `chrome.py:40-51` degrades silently with a warning when the
font is missing, which is why nobody has noticed. Copying it would reproduce
"silent in the frozen build only" — the exact failure this section is trying to
avoid. Fixing the font path is out of scope here but worth a follow-up.

An unknown sound id normalises to `"none"` and logs; a dropdown entry with no
file behind it is indistinguishable from a broken alert.

**Dispatch is a mailbox plus a signal, not a message payload.** `PostMessageW`
is bound `[HWND, UINT, WPARAM, LPARAM]` (`preview/win32.py:301-305`) and carries
integers only. The existing hotkey handoff is the shape to copy and says so in
its own comment (`preview/host.py:122-130`): the value travels in a
lock-protected field on the host and only the signal is posted, exactly as
`set_hotkeys` does (`:186-192`). So an alert is appended to a lock-protected
queue on the host and a bare `WM_APP_ALERT` is posted; the pump drains the queue
on receipt.

**Startup ordering.** `host.start()` returns before the preview thread has
created `_hwnd` (`:139-147`, `:219-235`), so there is a window in which there is
no post target. The queue accepts writes at any time and the post is guarded on
`_hwnd` being set — again the `set_hotkeys` pattern — and the pump drains
whatever is queued when it comes up, so nothing raised during startup is lost.

**Lifecycle: one reconciliation path, not several start/stop calls.** The
service exposes a single idempotent `reconcile()` that computes the desired
state — running if and only if previews are enabled **and** alerts are enabled
**and** `gamelogs_dir` resolves to a real directory — and starts, stops or
repoints the tailer to match. It is called from every setting that can change
that answer:

- `start_previews_if_enabled` (`ui/api.py:1633-1648`)
- `set_preview_enabled` (`:1650-1686`)
- `shutdown_previews` (`:1689-1701`)
- `set_alert_enabled` (new)
- `set_folder` when `which == "gamelogs"` (`:1527-1549`)

That last one is the important one and the repository already carries the scar.
`set_folder`'s own comment records that the gamelogs branch "drives no watcher",
and the docstring above it describes the bug that made the endpoint necessary:
a folder that persisted and a window that "looked healthy" while nothing ever
started polling. Wiring alerts to preview enablement alone would reproduce that
exactly — change the Gamelogs folder mid-session and the tailer keeps reading
the old path until restart, with the card cheerfully reporting a folder it is
not watching.

Driving on alert enablement as well as preview enablement also settles a
resource question: alerts default off, so a user with previews on and alerts off
gets no polling thread at all.

The service is built in `__main__.py` alongside `build_preview_host`
(`:321-397`), which is the model, and its thread is non-daemon with an explicit
stop signal so exit does not kill it mid-read holding open handles.

**Health is readable state, not an event.** The service records and exposes for
polling: whether the thread is alive, the timestamp of the last successful poll,
the last error if any, and the set of characters currently watched. The polling
loop is guarded so one exception cannot kill the thread, and a terminal exit is
recorded rather than swallowed.

This is not optional decoration. The design's own position is that silence is
the worst failure mode here, and a dead tailer is indistinguishable from a quiet
system unless something says so. The preview host already surfaces its startup
and hook failures rather than swallowing them (`preview/host.py:219-225`,
`:329-333`); the tailer gets the same treatment, and the UI renders it beside
the character count.

### `preview/host.py` — modified

`_install_hook` (`:310-333`) registers an inner `on_event` callback (`:314`)
which currently discards its `hwnd` argument and only calls `request_sweep()`
(`:315-316`). It starts carrying it. The callback arrives on an arbitrary thread
and must not touch a preview inline, so it posts.

**Selection resolves on the 80 ms tick, not on the posted message.** The
foreground hwnd is resolved against `self._clients`, which is only refreshed
inside `_sweep` (`:343`). Resolving inline would race: two messages are now
posted per foreground change and their processing order would decide whether a
just-launched client's first focus resolves at all. Deferring to the tick makes
the order irrelevant.

A second `SetTimer` with its own id, distinct from the 700 ms sweep
(`SWEEP_TIMER_ID = 1`, `host.py:25`, armed `:232-234`), ticks at 80 ms. It runs
while any alert is live *or* a selection change is pending, and stops otherwise.
Each tick expires what is due, acknowledges, resolves pending selection, and
invalidates only previews that changed this tick.

**Teardown while armed.** `_sweep` does `self._windows.pop(key).close()`
(`:347`) when a client quits. That path must free the alert frame cache and
clear the alert's contribution to the timer's bookkeeping, or the timer runs for
the rest of the session and the DIBs leak.

**One preview per character.** `discovery.py:71` derives `stable_key` as
`character or f"hwnd:0x{hwnd:x}"`, and `host.py:336` builds `_clients` as a dict
comprehension keyed on it, so a duplicate key silently drops a client. Two
previews for one character is structurally impossible today. Alert state
therefore lives on the single matching preview, and the phrase "every preview
showing that character" would be misleading.

### `preview/window.py`, `preview/chrome.py` — modified

`selected` is assigned `False` once at `window.py:261` and never set true by any
code path. It is already in `_chrome_key()` (`:330`) and already reaches
`chrome.render()` (`:351`), so the ring costs one assignment and a redraw on
change.

`chrome.py:79` changes from `width = border * 2 if selected else border` to
painting the ring only when selected.

**`BORDER` drops from 5 to 2, and that is a visible change to every existing
preview**, not only to the ring. `BORDER` (`window.py:30`) feeds
`thumbnail_rect` (`:321`, `:375`) and `chrome.render(border=BORDER)` (`:349`),
where it also positions the label band and its text
(`chrome.py:82-88`, `band_bottom = border + label_h`). Every preview's video
area grows 3 px on each side and its label shifts. Expected, and worth stating
so the hand pass is not surprised by it.

**The thumbnail inset is conditional after all, changing on arm and clear.**
Two different things clip a ring drawn wider than `border`, and between them
they cover all four sides:

- On the **left, right and bottom**, the DWM thumbnail. It composites *over* the
  window and contributes nothing to its alpha (`chrome.py:22-30`), and its rect
  starts at `x = border`, `y = border + label_h` (`geometry.py:78-89`).
- Across the **top**, the label band. `chrome.py:84` fills
  `[border, border, w - border - 1, band_bottom]` with `LABEL_BG` *after* the
  ring is drawn, overpainting exactly the part of a wide top ring that the
  thumbnail does not reach.

So a 6 px ring inside a 2 px inset does not render as a 6 px ring anywhere along
an edge. What survives is four 6 px corner blocks — at `x < border` and
`x > w - border - 1`, outside the label band's span — joined by 2 px edges. That
reads as corner brackets, not as a thicker border, and it would be a worse
signal than the 2 px selection ring it is meant to outrank.

The inset therefore goes to 6 px while alerting and back to 2 px on clear. This
costs two `DwmUpdateThumbnailProperties` calls per alert lifecycle — on arm and
on clear — not one per tick. An earlier draft ruled this out on churn grounds
using the per-tick figure, which was wrong by the whole pulse rate and would
have shipped a feature whose central visual signal did not render. The cost that
remains is real and visible: the game video shrinks 4 px a side for the duration
of an alert.

### The alert render path

`SetLayeredWindowAttributes` is rejected as the vehicle, despite
`eve-preview-design.md:468-471` naming it and `preview/win32.py:292-297` binding
it for the purpose with no call site anywhere.

The two APIs are not flatly incompatible, and an earlier draft overstated that.
Calling `SetLayeredWindowAttributes` blocks subsequent `UpdateLayeredWindow`
calls until `WS_EX_LAYERED` is cleared and restored, so it *can* be made to
operate over an existing ULW surface at the cost of a style reset and a repush.

It is rejected on what it can express, not on whether it can be called: it sets
one constant alpha for the whole window. It cannot tint, and it cannot pulse the
ring alone — it would fade the entire preview, chrome and label together, in a
colour it has no way to choose. Per-pixel alpha is also load-bearing rather than
cosmetic here (`chrome.py:22-30`). **The probe below should still settle the
interaction** rather than leave the parent design's stated vehicle contradicted
by prose alone.

Dirty-rect narrowing via `UpdateLayeredWindowIndirect` was considered and
rejected: `prcDirty` is a single rect and an alert ring is hollow, so its
bounding box is the whole window.

So: **a per-window pre-rendered frame cache.** Not a shared or module-level
cache — it is owned by the `PreviewWindow`, allocated on arm and freed on clear,
so the "zero cost when not alerting" property actually holds. Its key is
`(w, h, selected, event, color)`; `label` is not needed because the cache cannot
outlive the window it belongs to. **`color` is in the key deliberately** — the
service reads settings live at event time and the UI can change an event's
colour while a persistent alert is still armed, so a cache keyed on `event`
alone would keep pulsing the old colour indefinitely.

On arm, render six alpha steps of chrome-plus-ring into six DIBs and hold one
memory DC. The per-tick work is `SelectObject` of the next DIB plus
`UpdateLayeredWindow` — no Pillow render, no `CreateDIBSection`, no `tobytes`.
Six steps is past what the eye resolves in a 1200 ms pulse.

This is a genuinely new code path, not a loop around `layered.push`, which
creates and destroys its DC and DIB per call (`layered.py:26-68`). Its cleanup
must restore the DC's original object before deleting ours or the DIBs leak for
the life of the process — the trap is written down at `layered.py:63-67`.

**A size ceiling, because preview size is unbounded.** `resize_result`
(`window.py:48-58`) floors at `MIN_SIZE` and has no maximum, and
`validated_preview` clamps `width`/`height` with `max()` only
(`settings.py:152-155`). Six frames at 320x210 is ~1.6 MB; at 1920x1080 it is
~50 MB, held indefinitely under persistence, and a fleet-wide aggression arms
every preview at once. **Above 640x480 the cache falls back to a two-frame
blink at ~400 ms** — two DIBs instead of six, a blink instead of a pulse. Large
previews are the ones you are most likely to be watching anyway.

**Arming is a synchronous hitch.** Six `chrome.render` calls happen inside the
alert handler on the preview thread; one render-and-push was measured at ~1.8 ms
during drag tuning (`window.py:194-201`), so arming is on the order of 10 ms,
multiplied by the number of previews arming in the same fight, on the thread
that also services drags and the sweep. The two-frame path above is also the
mitigation here.

**Restoring base chrome needs a forced redraw.** `redraw()` early-returns when
`_chrome_key()` matches the cached key (`window.py:341-343`), and pushing alert
frames does not change that key — so "push the base frame on clear" is a no-op
as written and the last alert frame would stay on screen. Clearing forces it.
The mirror hazard is that any unrelated `redraw()` during a live alert paints
base chrome over the alert without clearing alert state; the redraw path checks
for a live alert and repaints the current phase instead.

Pure movement is unaffected: `move()` already does `SetWindowPos` alone and the
layered surface survives (`window.py:356-375`), so dragging an alerting preview
stays on the existing fast path.

**Selection repaint is on the hottest path.** Today a foreground change costs one
posted sweep. After this it costs a sweep plus two chrome re-renders and two
full-window pushes — deselect the old, select the new. Multiboxing *is*
alt-tabbing between clients, and the preview hotkeys feature exists to make that
faster, so this is a regression on the interaction the subsystem is for. It is
two renders and not N, and the smoke pass should judge whether it is felt.

**Deviation: selection resolves in `_sweep`, not on the 80 ms alert tick.**
`_sweep` is the only place `_clients` is refreshed, and the foreground hook
already posts a sweep on every focus change, so resolving there is one message
rather than two whose relative order would decide whether a just-launched
client's first focus resolves at all. It also keeps selection working while
the alert timer is stopped.

## Settings

Nested under `preview`, because the border is the primary channel and cannot
exist without a preview to draw on. Nesting also keeps the tailer's existence
tied to previews being on — through the `reconcile()` path above, which gates on
alerts being enabled as well — matching the reasoning already in
`_preview_defaults`'s docstring (`settings.py:22-24`) for why previews default
off: it costs a thread, a 700 ms sweep and a foreground hook.

`gamelogs_dir` is **not** duplicated. Alerts read the top-level key the uploader
already reads.

```python
"alerts": {
    "enabled": False,
    "pve_filter": True,
    "persist_until_selected": True,
    "defaults_version": 1,
    "events": {
        "combat": {
            "enabled": True, "cooldown_s": 1, "color": "#ff4d4d",
            "sound": "chime", "duration_ms": 1200, "pulses": 3,
        },
        "warp_scramble": {
            "enabled": True, "cooldown_s": 8, "color": "#ffd24d",
            "sound": "bell", "duration_ms": 1200, "pulses": 3,
        },
        "decloak": {
            "enabled": True, "cooldown_s": 8, "color": "#4dd2ff",
            "sound": "chime", "duration_ms": 1200, "pulses": 3,
        },
    },
}
```

**`validated_preview` must gain an explicit copy branch for `alerts`, or the
subtree silently resets on the next write by any writer.** This is the sharpest
trap in the change. `validated_preview` rebuilds the section from
`_preview_defaults()` at `settings.py:145` and then copies across only the keys
it explicitly handles; `_normalize` calls it on every `update()`
(`settings.py:302`, `:387`). So adding `alerts` to the defaults without adding
the copy branch means a user's colours revert within one second of them dragging
a preview, via `LayoutStore`'s debounce — no crash, no log line.

`LayoutStore._write` itself is clean: it does `live.setdefault("preview", {})`
inside the block and assigns only `layouts` and `seen` (`store.py:84-96`). The
hazard is in the validator, not the store.

Validation otherwise follows `validated_preview`'s discipline
(`settings.py:142-188`), including the two-tier fallback stated in its own
docstring (`:143-144`) unchanged: a malformed `alerts` section falls back
**whole**, a malformed single event falls back **alone**. Clamps: `cooldown_s`
0-120, `duration_ms` 250-15000, `pulses` 1-16, `color` must match
`^#[0-9a-fA-F]{6}$`, `sound` must be a known id or becomes `"none"`. Unknown
event keys are dropped and missing ones filled from defaults, so a hand-edited
file cannot produce an event the renderer does not know.

`tests/test_settings.py:9` asserts `settings.DEFAULTS` as a literal, so the
defaults are pinned in two places and any `defaults_version` migration has to
keep both in step.

**There is no volume setting.** TriffView has `MasterVolume` because WPF's
`MediaPlayer` exposes one; `winsound.PlaySound` does not, and adding volume
means adding an audio dependency the plan's global constraints forbid. Volume is
the Windows per-application mixer. The UI should not imply otherwise. If it
matters, shipping the same sounds at two amplitudes is the no-dependency
workaround.

**`defaults_version` needs a mechanism, not just an intent.** The only
normalization point is `validated_preview`, called from `_normalize` on both
`update()` and `load()` — and `load()` normalizes without saving, so a migration
there rewrites in memory and relies on a later write to persist. It also needs a
retained table of *old* defaults to compare against, since the rule is to rewrite
only values that still equal the previous default. That turns a pure validator
into something carrying version history, which is a real cost. It is carried
anyway on TriffView's evidence: it needed exactly this migration, from thin long
flashes to thick short ones, and the timings, colours and persistence default
here were all picked by reasoning rather than use.

## UI

A third card in Settings > Previews, below the two at `index.html:335-383`.

```
Alerts
  [ ] Alert on EVE log events
  [x] Ignore NPC attacks
  [x] Keep alerting until you switch to that client

  [x] Combat          [swatch]  [chime  v]  Test
  [x] Warp scramble   [swatch]  [bell   v]  Test
  [x] Decloak         [swatch]  [chime  v]  Test
```

Colour and sound only. Cooldown, duration and pulse count stay defaults,
reachable by hand-editing — safe because validation clamps every one. Colour and
sound are how you tell *which* alert fired without reading anything; cooldown is
tuning nobody does twice. TriffView's full matrix is ten fields per event and
would make this card larger than the rest of the section combined, against
PRODUCT.md's reading of Previews as configuration visited twice ever.

**The bridge is per-field, not a document save.** `ui/api.py:1386-1401` explains
at length why a whole-document `save_settings` was rejected for the Settings
route, and this card must not reintroduce it: a `set_preview_alerts(section)`
taking a page snapshot would be a stale-snapshot write against a subtree a
`defaults_version` migration may have rewritten underneath it. So:
`set_alert_enabled`, `set_alert_pve_filter`, `set_alert_persist`,
`set_alert_event_enabled(event, on)`, `set_alert_event_color(event, hex)`,
`set_alert_event_sound(event, id)`, `test_alert(event)` — each writing one field
inside `settings.update()`.

**Test.** Bypasses the cooldown, as TriffView's does. Without it the only way to
learn whether sound works is to get shot, and every failure mode is silent. A
test alert is **never persistent**: the user is looking at Wingman, so no preview
is selected and nothing would acknowledge it — a persistent test would pulse
until they alt-tabbed to that client. If previews are off or no client is
running, Test plays the sound and says it could not show the ring, rather than
appearing to do nothing.

**Three states the card must say out loud**, following the parent design's rule
that registration status is *readable state, not an event*
(`eve-preview-design.md:434`). These are **reads**, not pushes:
`get_preview_hotkey_state` (`ui/api.py:1755-1780`) exists precisely because
previews start before the webview does and a push at that moment is swallowed,
and every one of these has the same property.

- **Previews off.** Alerts cannot draw. Reuse the `#preview-binds-off` banner
  pattern (`index.html:375`) rather than inventing a second idiom.
- **No Gamelogs folder.** The important one: without it alerts silently do
  nothing, which is indistinguishable from nothing happening in game. Point at
  the existing setting, which already has a picker and auto-detect
  (`ui/api.py:1322-1366`).
- **Characters watched.** A count — "watching 4 characters" — so a working setup
  looks obviously working.

That third one introduces a **third character namespace**, and the card should
not pretend the three agree. `host.characters()` comes from window titles,
`preview.seen` is the persisted MRU roster, and the tailer's set comes from
`Listener:` headers. A client at character-select is in none of them; one that
just relogged is in the first two but not the third. The count reported is the
tailer's, because that is the set that can actually produce an alert.

The count is **paired with the tailer's health**, never shown alone. A count on
its own is worse than no indicator: it would keep reporting "watching 4
characters" after the thread had died, putting a healthy-looking card above a
feature that had silently stopped alerting. So the card renders the service's
health state — thread alive, last successful poll, last error — alongside it.

Tone per PRODUCT.md: "Your EVE Gamelogs folder is not set. Alerts cannot run
without it." Not "Configuration incomplete."

A colour swatch is the first colour input in the app. `previews.js`'s `.dim`
(`style.css:749`, `:757`), `.unknown` (`:766`) and `.clash` (`:882`) are the
only place preview colour appears today, so this needs a style decision rather
than a borrowed one. If a native `<input type="color">` reads wrong against the
dark theme, three fixed swatches per event do the job.

`_settings_payload` ships the whole `preview` subtree to the page on every
`get_settings` (`ui/api.py:1286`, a shallow `dict(cfg)`), so the per-event table
joins `layouts` in that payload. Harmless at this size, worth knowing.

## Testing

`alerts/patterns.py` is pure and carries the weight: every matcher, both
extraction regexes, `strip_markup`, and `is_likely_npc`.

**A committed fixture corpus is a prerequisite, not a nicety.** Real gamelog
excerpts covering player attacks, player drone damage, misses, Sleeper fire,
Sleeper and Drifter scrambles, player scrambles and decloaks, checked into
`tests/`. It has to answer three questions the design cannot: whether
`is_likely_npc` ever misclassifies a real player, whether a scramble line yields
a source through the `<font>` path at all, and whether any decloak line carries
a source. The heuristic gates whether a persistent alert fires, and a false
negative means silence while a player opens fire.

`alerts/tailer.py` is testable on Linux against temporary files: open-at-EOF,
partial-line buffering, rotation reset, the 12 h cutoff, `Listener: EVE`
rejection, newest-session-wins, and the cap's ordering and post-filter
application.

`alerts/service.py`: cooldown suppression per `(character, event)`, filter scope
across the three events, unknown sound id normalisation, that config is read
live rather than captured, and that `reconcile()` is idempotent and reaches the
right state for each combination of preview-enabled, alert-enabled and
folder-resolves. Health state — thread death recorded, last-poll timestamp
advancing — is testable on Linux with a stubbed clock. Sound playback is mocked.

Alert state — arm, all three severity directions including equal rank, expiry,
acknowledgement by selection and by click — is pure and belongs in its own
tests, following `preview/geometry.py`'s precedent of keeping decisions out of
the Win32 module.

Settings: defaults, every clamp, both fallback tiers, and specifically a
regression test that a `LayoutStore` write does not reset the alerts subtree.

### What CI cannot tell us

CI is `ubuntu-latest`. It cannot tell us whether the frame cache holds 80 ms
without stutter, whether the inset swap on arm reads as a deliberate change or
as a glitch, whether an unselected preview's dark frame is acceptable over bright
game content, whether the selection repaint makes alt-tab feel slower, whether
`winsound` fires from a background thread in the frozen build, or whether the
`.wav` files survive PyInstaller. All of that is a hand pass, and
`docs/smoke-checklist.md` gains items for each of the three UI states, the Test
buttons, an alt-tab feel check, and a real alert observed on a real client.

## Risks and open questions

**The `SetLayeredWindowAttributes` interaction is unprobed.** The design rejects
it on expressiveness — one constant alpha for the whole window, no colour, no
way to pulse the ring alone — which does not depend on hardware. What is
unprobed is the interaction itself: whether it can operate over an existing
`UpdateLayeredWindow` surface with a `WS_EX_LAYERED` reset, and what that does
to the per-pixel alpha the hit region depends on. The parent design names it as
the intended vehicle and binds it at `win32.py:292-297` for that purpose, so the
record should be settled rather than left contradicting itself. A throwaway
probe, matching the five that preceded the parent design, and the same probe
should confirm the ring-occlusion geometry above — that a ring wider than the
inset renders as corner brackets rather than a thicker edge.

**The frame cache may still be too expensive.** The parent design warns against
putting a ~67k-pixel push on a timer because that is "the cost that made
dragging stutter" (`eve-preview-design.md:468-471`). The mitigation is that drag
fires at 320 events/s against a ~1.8 ms handler while this fires at 12.5/s, and
that the per-tick Pillow work is gone. If measurement disagrees, the two-frame
blink already specified for large previews becomes the path for all of them — a
constant change, not a rewrite. A second escape hatch exists: a separate
colour-keyed overlay window per preview pulsed with `LWA_COLORKEY | LWA_ALPHA`,
which is the cheapest possible tick and also sidesteps the occlusion problem
entirely, but adds an HWND per client to the most carefully tuned code in the
feature and would need `LWA_COLORKEY` bound — `win32.py:58` defines `LWA_ALPHA`
only.

**The NPC heuristic is the largest correctness risk.** See Testing.

**Persistence may be wrong by default.** It is the setting most likely to want
flipping after a week, which is what `defaults_version` is for.

**DPI: the ring widths are physical pixels, and that is a decision by
omission.** The preview thread sets `PER_MONITOR_AWARE_V2` thread-locally
(`host.py:209-214`), so every rect and bitmap dimension it handles is raw
physical pixels. A 2 px selection ring on a 200% display is one logical pixel;
a 6 px alert ring is three. Nothing scales chrome by monitor DPI and there is no
`WM_DPICHANGED` handling, so a preview dragged between monitors keeps its
physical size — which is pre-existing behaviour, not something this change
introduces. Whether the alert channel specifically should be DPI-scaled is left
open deliberately, and the hand pass on a mixed-scale setup should answer it.

**No alert can reach a client at the character-select screen**, because matching
is by `Listener:` name and there is no character yet. TriffView has the same
limitation.

**`chrome.py`'s font path is probably broken in the frozen build.** Discovered
while establishing the asset precedent for sounds. Out of scope here, worth its
own fix.

## Not in this slice

Label customisation (item 8), switching behaviour (item 10) beyond the selection
tracking the border needs, profiles (item 12), EVE-O / EVE-X import (item 13).
The wormhole-splash audio detector is out permanently on the no-dependency
constraint: it is per-process WASAPI capture with FFT band correlation against
eleven committed templates, and nothing in it is portable without an audio
stack. `system_change`, `fleet_invite` and `convo_request` are out by the
decisions above. The dead `opacity` setting stays dead — it wants
`SetLayeredWindowAttributes`, which this design has ruled out for these windows,
and that is its own problem.
