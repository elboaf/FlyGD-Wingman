# Combat-triggered Discord Go Live: automatic stream start on combat

Status: proposed, **revision 2** — revision 1 assumed Discord's stream
source could follow the focused EVE client. Field testing found it cannot:
source selection pins per game entry. Revision 2 changes the mechanism
(Wingman presents the streamable window) but keeps revision 1's consent
design, guard stack and SendInput chord mechanism unchanged.

## The request

"Whenever the combat log detects combat, Discord automatically starts
streaming your screen (if you're in a voice channel)."

The audience reads this as fleet logistics, not content creation: the
fleet can see what you see at the moment contact happens, without you
finding the Go Live button while taking damage. The ask is latency
(`stream up before the first volley finishes`) and zero attention cost,
which is the same argument PRODUCT.md records for alerts interrupting at
all.

## What testing found (the constraint revision 1 missed)

Multiboxing breaks Discord's game capture in two independent ways:

1. **Detection is per executable.** Discord streams a game it recognizes;
   an unrecognized window offers only screen/window capture. EVE Online is
   recognized (it ships in Discord's game list), so `eve.exe` qualifies.
2. **The pinned window never follows focus.** With several `eve.exe`
   processes, Discord's game capture binds to **one** top-level window per
   game entry — empirically the first-launched client — and keeps it for
   the life of the stream. Streaming "whoever is in trouble" is therefore
   impossible with stock detection: the fleet watches a pilot who may not
   be fighting.

The inversion that fixes both at once: **make Wingman the registered
game.** Discord then pins one window forever — a window Wingman owns,
whose *content* follows focus. Discord never has to switch anything;
the fleet always sees the pilot who is flying.

## Why Discord cannot be told to start a stream

Unchanged from revision 1, still true:

- Discord's documented local API — RPC over a named pipe
  (`\\.\pipe\discord-ipc-{0..9}`) — has no command that starts Go Live;
  the community protocol reference (discord-userdoccers) lists none
  among the undocumented commands either. Deep links go to channels,
  never into a stream.
- The user-facing surface that starts one is the **user-configured global
  keybind**: User Settings → Keybinds → **Toggle Screen Share**. Global
  keybinds are system-wide; they fire with any window focused, including
  EVE. Automating it from a third-party process is an unofficial
  integration surface and could change in any client update.
- "If you're in a voice channel" self-resolves: the keybind no-ops when
  no stream is possible. Detection would need the RPC app-approval dance;
  out of scope.

So the start mechanism stays: Wingman synthesizes the user's own Discord
keybind chord with `SendInput` (pure `ctypes`, house Win32 style, no new
dependency). Discord does the streaming; Wingman only presses a key the
user mapped.

## The mechanism, revision 2

Two independent parts; either is valuable alone, the feature needs both.

### Part II — the streamable window: a focus-following mirror

A single Wingman-owned top-level window that presents, via a DWM
thumbnail, **the currently focused EVE client**:

- **The mirror window is Wingman's own window** — headless in purpose,
  but a real top-level window so Discord can register and capture it.
  No Wingman chrome beyond a minimal caption (a captionless window may
  be harder for Discord's picker to treat as a game window; confirm in
  the probe).
- **Content:** one `DwmRegisterThumbnail` binding, re-targeted when focus
  changes. All the parts exist in the house style: `preview/thumbnail.py`
  wraps register/update/release; `preview/host.py:3297` already runs an
  `EVENT_SYSTEM_FOREGROUND` hook on a real message-pump thread; focused-
  client identification exists (`evewindows.py:list_eve_windows`,
  `focused_eve_title`).
- **Rebind semantics:** on foreground change to an admitted EVE client,
  unregister + re-register the thumbnail at the new `hwnd` (DWM has no
  retarget call). On desktop/browser focus: keep the last client — never
  blank the fleet's view, and never mirror non-EVE content (privacy and
  the product line: Wingman mirrors EVE clients, nothing else).
- **Independence:** the mirror follows focus regardless of the alert
  feature; it is useful by itself (fleet sees whoever is flying). The
  Go Live automation is one consumer of it, not its reason to exist.
- **Not a preview:** none of the preview window behaviors (click-through,
  crop, hide-on-focus-loss, companion rules) apply. One fixed window,
  no placement logic beyond first-run default. PRODUCT.md's no-EVE-geometry
  line is untouched: DWM thumbnails read pixels and modify nothing about
  the source — previews already prove this daily.

### Part I — starting the stream: the recorded chord (unchanged from rev 1)

On the gated combat alert (see guards), one `SendInput` of the user's
recorded Toggle-Screen-Share chord. Discord goes live capturing the
registered "game" — the mirror — which is showing the focused client,
i.e. the client in combat if the user was flying it.

### Setup ceremony (one-time, per install)

1. User adds Wingman's installed exe to Discord's Registered Game list
   (Settings → Registered Games; the manual "Add it" path with the
   installer's exe path — registration data is user-scope registry +
   Discord settings, not admin).
2. User starts the mirror from Settings → Alerts ("Start stream mirror"),
   picks it in Discord's stream source picker once, manually — after
   which Discord pins the mirror permanently.
3. User maps Toggle Screen Share to a chord in Discord, then records the
   same chord in Wingman (this recording is the consent gate, below).
4. Done. In combat: chord fires, Discord starts the mirror, mirror shows
   the fighting pilot.

## Capture-visibility gate (resolve before any other work)

**The one unknown revision 2 rests on:** whether Discord's game capture
path sees DWM-composited thumbnail content, or reads the window's own
pixels via `Windows.Graphics.Capture`/ DXGI and gets a black/empty mirror.

A 5-minute manual probe decides it, before writing any feature code:
spare Python process registers a DWM thumbnail of Notepad into a plain
top-level window; add that process to Registered Games; start streaming
it; look. **Run each of the three visibility states once — front,
covered, back; add minimized only to confirm the known failure.**

Visibility states and their expectations (user-side visibility of the
mirror window, per Windows capture behavior):

- **Front (focused, nothing over it):** trivially works.
- **Covered:** the compositor still composites occluded windows;
  screen-region capture shows the mirror wherever it sits in the z-order.
  Expected to work; the probe confirms for Discord specifically.
- **Back / off-screen (on another monitor, or parked off the desktop
  edge):** the mirror window is composed and its thumbnail is live; WGC
  maintains per-window surfaces for occluded top-level windows. OBS
  window capture of background windows is established practice; the
  probe confirms Discord's game capture path agrees. No user-visible
  screen area is required.
- **Minimized:** fails by design — Windows stops compositing a
  minimized window's surface (documented OBS behavior across capture
  methods). The mirror must never minimize. Enforce in the mirror
  window: strip `WS_MINIMIZEBOX` and ignore `SC_MINIMIZE` in
  `WM_SYSCOMMAND`, mirroring how the preview host already pins its own
  window states. A "minimize to nothing" desire is satisfied by
  off-screen parking instead.

So the answer to "must the user see it": **on one monitor, yes, it will
occupy screen area that can be covered but not closed; with two or more
monitors, the mirror parks off-screen or on the secondary and the user
never looks at it.** Never minimized.

- **Tier A — thumbnail visible to Discord:** build as specified.
- **Tier B — black capture, but screen/window capture of the mirror
  works:** ship with documented Tier-B setup (user picks the mirror via
  screen capture instead of game capture; detection's per-process pin
  problem then has a stable single source, which is the part that
  matters).
- **Tier C — neither:** abandon; revision 1 is unshippable for
  multiboxers (its pinned-source flaw), so the feature waits for a
  Discord-side change. Document in the issue; no code lands.

The feature is not started until the probe reports A or B.

## The hard lines it touches (unchanged resolution, one addition)

PRODUCT.md's "What it must not become" lines, quoted in revision 1:

1. *"It must not upload anything the user did not select. Nothing leaves
   the machine without an explicit action."*
2. *"It must not automate gameplay. It sends keystrokes the user pressed,
   to a window the user is looking at. It does not act for them."*

The resolution is revision 1's, verbatim: **the user pressed that chord —
once, in advance — and selected the stream source once, in advance.**
Wingman adds only *when*. Counterfactual test: close Wingman mid-combat
and nothing happens that the user did not already configure.

Three rules keep the letter of line 2, unchanged:

- **The chord is the user's own Discord keybind**, recorded by the user;
  Wingman never invents one.
- **A capture, not a broadcast:** the chord goes to the focused window
  exactly like a user keypress; no window routing, no Discord activation.
- **Never stop a stream:** the bind toggles; V1 has no auto-stop and no
  second chord while armed (guards below make the first chord the only
  one per fight).

Addition for the mirror, line 3 of "must not become" (EVE geometry):
untouched — the mirror is Wingman's window; DWM thumbnails modify nothing
on the source. The mirror never sends input to EVE and never changes a
client's position, size, or z-order.

## Guard design (carried from revision 1, unchanged)

1. **Consent gate.** Enabling = recording the Discord keybind chord in
   Wingman's settings (layout-aware capture machinery, ADR 0002). No
   chord recorded = inert. No separate on/off checkbox; presence of the
   chord *is* the enabled state; clearing it is the explicit off.
2. **Episode latch + process-wide arm/disarm.** Fires only on the first
   gated combat alert after a quiet period (default 300s per character).
   The first fired chord disarms **all** characters until every latch has
   expired — the spec's most important behavioral sentence: **one stream
   per fight, Wingman presses once.** A second chord while live is the
   toggle that ends the fleet's feed; the guards exist to make it
   unreachable from Wingman.
3. **Confirmation.** Focus gate (no chord while the user is typing into
   a text field is unknowable; but no chord while Discord itself is
   foreground) + a visible state row in Settings → Alerts: armed
   characters, chord, last-fired time and character. "An alert you
   configured and cannot tell is running is the failure mode" applies
   verbatim to a background key-presser. Trigger is the gated combat
   alert only (`AlertPolicy.handle` funnel — PvE filter inherited); NPC
   fire never reaches it.

## Settings surface

Settings → Alerts, one card (name pending decision):

```
Stream coupling
  Stream mirror: [Not running — Start mirror]   (Wingman-owned window Discord pins)
  Keybind: [Ctrl+Alt+D] (capture button)        ← recording = consent
  Quiet period before re-arm: [300] seconds
  ──────────────────────────────────────────────
  Armed for: Kuan Dai, xX_Sigma_Xx
  Last fired: 12:41 · Kuan Dai
```

Keys under `preview.alerts.stream_coupling`: `chord` (AHK-style, `^!d`),
`quiet_s` (60–900, default 300), `mirror_on` (the one toggle that is not
consent — the mirror alone is useful). The Go Live automation remains
chord-derived.

## Architecture

- **Mirror:** new `wingman/streaming/mirror.py` (if the capture probe
  requires sharing the preview host's pump thread, `preview/host.py`
  gains a second hook consumer instead — decide at implementation, the
  host already owns the only legal thread shape). Rebind = unregister +
  register via `preview/thumbnail.py` wrappers. Consumes foreground
  events only; no polling loop beyond the existing shared scan fallback.
- **Controller:** `wingman/alerts/streamcoupling.py` behind the
  controller/ports template (`AlertsPorts` gains one port or a sibling
  ports object): owns latches, reads chord/quiet settings live, owns the
  send. Imports nothing from `ui`; the send and the thumbnail calls are
  injected seams (Linux-unit-testable like every other subsystem); sends
  happen on the controller's own worker thread, never the telemetry
  dispatcher thread.
- **Bridge:** semantic pushes only (`stream_coupling_state`,
  `stream_coupling_fired`), mirrored to the floating sig bar per the
  standing rule; `test_bridge_contract.py` must see every
  `_push("literal")`.
- **Wire-in:** `__main__.py:build_alert_policy` (dispatch into the
  alert chain), `ui/api.py:_build_alerts_controller`, settings defaults +
  validator in `settings.py`.

## Failure modes

- **Capture probe fails (Tier C):** feature does not start; documented.
- **Discord stops seeing the registered game** (exe moved, Discord
  settings reset): stream start silently no-ops; armed row stays armed —
  the row must say armed, never live. Setup ceremony in the card's
  helper text is the diagnostic.
- **Mirror source dies** (client closes): thumbnail release is routine
  (`thumbnail.py` already treats it so); rebind waits for the next
  foreground client. Fleet sees a frozen last frame until then — same
  behavior as a streamer going static, acceptable.
- **Chord collision with EVE/Windows binds:** warn at capture time (one
  line: "This chord also fires in EVE while EVE is focused"); never
  prevent.
- **Text field focused at fire time:** chord lands there like a user
  keypress. Accepted risk, same warning line.
- **User already streaming when combat starts:** the process-wide latch
  cannot know; the user pressed Go Live themselves, and the fight's chord
  is suppressed only by the latch, not by stream state. V1 accepts this
  (documented); phase 2's RPC state query is the real fix.

## Verification plan

1. **Probe first:** the DWM-capture test above; result recorded in #312.
   No implementation work before A/B.
2. Unit (Linux): controller tests with injected send — consent refusal,
   once-per-episode, process-wide disarm, quiet-period re-arm, focus-gate
   refusal, armed-row payload updates.
3. Unit (Linux): mirror logic with injected thumbnail libs — rebind on
   foreground change, sticky last client on non-EVE focus, release on
   source death. Shape follows `preview/`'s existing fake-lib tests.
4. Native seam test (Windows-only, skippable like existing seams):
   SendInput round-trip; thumbnail register/release round-trip.
5. Hand pass against `docs/smoke-checklist.md`: card states, mirror
   start/stop, capture flow, armed row.

## Phase 2 candidates (unchanged)

- Local-RPC stream/voice state detection (app-approval modal): safe
  re-arm mid-fight, "only fire when actually not streaming", in-voice
  preconditioning.
- Auto-stop after quiet period (toggle-off risk; needs the same query).
- Fleet coordination ("who streams") — belongs to fleet sharing, not
  local keybinds.

## Open questions for the human (revised)

1. ~~Name~~ — pending: "Stream coupling" vs "Combat → Go Live".
2. Quiet-period default 300s — pending.
3. ~~Single-monitor users see the mirror on their only monitor (covered
   is fine, minimized is not — see visibility states above). Is that
   acceptable for V1, or does the mirror need a hide-theater mode?~~
   Partially dissolved by the visibility states: covered works. Single-
   monitor is now a UX preference, not a feasibility question.
4. ~~Alerts vs Uploading placement~~ — pending, spec assumes Alerts.
5. **New:** should the mirror be always-available (a small always-on
   Wingman window, like the Fleet Bar) or launched on demand from
   Settings? Spec assumes on-demand + "keep running" sticky.
6. **New:** when no EVE client is focused at chord time, the mirror
   shows the last client, which may not be the one in combat (user was
   alt-tabbed into a browser). Acceptable, or hold the chord until an
   EVE client is focused again (fires late, potentially minutes)?
