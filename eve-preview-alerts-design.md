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
the frame cache mid-pulse. Ranks are `warp_scramble` 3, `combat` 2, `decloak` 1.

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

**Cooldowns** are keyed `(character, event)`. A suppressed event is invisible
everywhere — no state change, no sound, no history. The cooldown is stamped when
an alert is actually **dispatched**, not when a line matches: an event that
fires while the host is stopped or a preview is being recreated must not burn
the window and silence the follow-up a second later.

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

Dispatch is `PostMessageW` to the existing `HWND_MESSAGE` host window
(`preview/host.py:242-287`), which exists precisely so there is always a valid
target.

**Lifecycle.** Built in `__main__.py` alongside `build_preview_host`
(`:321-397`), which is the model. It must be startable and stoppable from the
same three places the host is: `start_previews_if_enabled`
(`ui/api.py:1633-1648`), `set_preview_enabled` (`:1650-1686`) and
`shutdown_previews` (`:1689-1701`). None of those currently touch it, and
without that wiring the design's claim that the tailer only runs when previews
are enabled has no code behind it — turning previews off would leave it polling
and `winsound` firing with nothing on screen to explain it. `host.start()` is
idempotent and the service must be too. The thread is non-daemon with an
explicit stop signal, so exit does not kill it mid-read holding open handles.

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
The thumbnail composites *over* the window and contributes nothing to its alpha
(`chrome.py:22-30`), and its rect is inset by the border width
(`geometry.py:76-87`) — so **the visible ring width is capped at the inset**.
A 6 px alert ring inside a 2 px inset renders as 2 px, indistinguishable from
the selection ring it must be told apart from.

So the inset is 6 px while alerting and 2 px otherwise. This costs two
`DwmUpdateThumbnailProperties` calls per alert lifecycle — on arm and on clear —
not one per tick. An earlier draft ruled this out on churn grounds using the
per-tick figure, which was wrong by the whole pulse rate and would have shipped
a feature whose central visual signal did not render. The cost that remains is
real and visible: the game video shrinks 4 px a side for the duration of an
alert.

### The alert render path

`SetLayeredWindowAttributes` cannot be the vehicle, despite
`eve-preview-design.md:468-471` naming it and `preview/win32.py:292-297` binding
it for the purpose with no call site anywhere. It and `UpdateLayeredWindow` are
documented as mutually exclusive modes, and per-pixel alpha is load-bearing
rather than cosmetic (`chrome.py:22-30`). It also cannot express colour, only
opacity. **Probe this before building on it** — see Risks.

Dirty-rect narrowing via `UpdateLayeredWindowIndirect` was considered and
rejected: `prcDirty` is a single rect and an alert ring is hollow, so its
bounding box is the whole window.

So: **a per-window pre-rendered frame cache.** Not a shared or module-level
cache — it is owned by the `PreviewWindow`, allocated on arm and freed on clear,
so the "zero cost when not alerting" property actually holds. Its key is
`(w, h, selected, event)`; `label` is not needed because the cache cannot
outlive the window it belongs to.

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

## Settings

Nested under `preview`, because the border is the primary channel and cannot
exist without a preview to draw on. Nesting also means the tailer runs only when
previews are enabled — given the lifecycle wiring above — which matches the
reasoning already in `_preview_defaults`'s docstring (`settings.py:22-24`) for
why previews default off: it costs a thread, a 700 ms sweep and a foreground
hook.

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

`alerts/service.py`: cooldown suppression per `(character, event)`, cooldown
*not* burned when dispatch is impossible, filter scope across the three events,
unknown sound id normalisation, and that config is read live rather than
captured. Sound playback is mocked.

Alert state — arm, both severity directions, expiry, acknowledgement by
selection and by click — is pure and belongs in its own tests, following
`preview/geometry.py`'s precedent of keeping decisions out of the Win32 module.

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

**The `SetLayeredWindowAttributes` question is unprobed.** The claim that it and
`UpdateLayeredWindow` are mutually exclusive is from documentation, not from
this hardware. The design does not depend on it working — the frame cache is the
plan precisely because it does not — but the parent design names it as the
intended vehicle and binds it at `win32.py:292-297` for that purpose, so the
record should be settled rather than left contradicting itself. A throwaway
probe, matching the five that preceded the parent design, and the same probe
should confirm the ring-occlusion geometry above.

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
