# Implemented on spec/combat-golive

> **Branch state: `spec/combat-golive` @ `0092e48` already contains the full #316 mirror implementation** (harvest + review fixes; see the #316 comments). Everything below remains the binding spec for #317-#321. **All work on this feature stays on the `spec/combat-golive` branch** - `main` does not receive any of it until a real test-build of the packaged app confirms the feature works end to end (human-run, per the 2026-10-05 decision). Do not open PRs into `main` and do not merge anything to `main` from this feature.

---

# Combat-triggered Discord Go Live: automatic stream start on combat

Status: proposed, **revision 3** — revision 1 assumed Discord's stream
source could follow the focused EVE client (it cannot: source pins per
game entry). Revision 2 made Wingman the registered game presenting a
focus-following DWM mirror. Revision 3 moves the mirror into its own
single-window process (`wingman-mirror.exe`) registered as the game, so
Discord's per-process pin has exactly one window to choose — by
construction, not by hoping its heuristic skips Wingman's other
windows. Consent design, guard stack and SendInput chord mechanism are
unchanged since revision 1.

Decisions recorded 2026-10-05 (#312 review): split naming (card titled
for streaming, "Combat auto-start" as the section inside); quiet period
default 300 s; placement in a new top-level Streaming section (the
trigger remains fed by the alert chain); sticky on-demand mirror
lifecycle (`mirror_on` persists, restored at launch, default off); chord
fires even when no EVE client is focused (mirror shows the last client;
hold-until-focus rejected). The open-questions section below is retired
into that record.

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

- **The mirror lives in its own short, single-window process**
  (`wingman-mirror.exe`, packaged by the same installer). Revision 3
  change: revision 2 trusted Discord's window heuristic to skip the
  main process's WebView2 host, sig bar, previews and crop windows —
  a hope, not a guarantee. A dedicated process makes "exactly one
  game-like top-level window" true **by construction**: whatever rule
  the pin applies — first window, largest window, only window,
  focused-at-registration — it lands on the mirror, because there is
  nothing else in the process for it to land on. The registered game
  is the mirror exe; never the main `wingman.exe`. Wingman supervises
  the process exactly like the AutoHotkey engine (spawn + kernel Job
  object + status file + orphan recovery, the `HotkeyEngine` pattern);
  the mirror reads its source-client instructions from the same kind
  of status/INI file channel the engine uses, not a new IPC design.
- **Placement: bottom of the z-order, on the desktop.** Created at the
  bottom (`SetWindowPos` with `HWND_BOTTOM` before first show, or
  created hidden and shown with `SWP_NOACTIVATE | SWP_NOZORDER` after
  a `HWND_BOTTOM` position), parked **on** the desktop -- behind
  everything, or on a secondary monitor's visible area. Revision 3
  assumed off-desktop-edge parking kept the window composed; the probe
  run falsified that (field evidence below), so the design parks
  on-desktop: covered is proven to stream. It must never take focus (the mirror has no
  interaction; a `WM_MOUSEACTIVATE` returning `MA_NOACTIVATE` plus
  no click-through keeps it from stealing the pilot's focus mid-fight)
  and never minimize (visibility states below). The user's exposure to
  it: one window in Alt-Tab, nothing on the desktop unless they look
  for it. If Alt-Tab presence is unacceptable, the documented
  `WS_EX_TOOLWINDOW` trade-off (invisible to capture enumerators) is
  exactly the risk the probe's step 3 rules in or out.
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

1. User adds the **mirror exe** to Discord's Registered Game list
   (Settings → Registered Games; the manual "Add it" path with the
   installed `wingman-mirror.exe` path — registration data is
   user-scope registry + Discord settings, not admin). Never the main
   `wingman.exe`: registering it would put every Wingman-owned window
   — WebView2 host, sig bar, previews — inside Discord's heuristic.
2. User starts the mirror from Settings → Alerts ("Start stream
   mirror"), picks it in Discord's stream source picker once, manually
   — after which Discord pins the mirror permanently.
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
- **Covered (on-desktop, behind other windows):** the compositor keeps
  compositing occluded top-level windows; the probe run confirmed
  Discord's capture reads them. This is the shipping park.
- **Off-desktop-edge (beyond the virtual screen):** **falsified by the
  probe run** -- the composed surface stops updating the moment the
  window leaves the desktop, and the stream froze on the last frame.
  The design no longer parks there; the probe build keeps the `3`
  command only as a reproducible demonstration.
- **Secondary monitor (visible area):** expected to behave like
  covered -- composed, streamed; on-desktop parking with the advantage
  that nothing sits under the pilot's windows. Confirm on the
  two-monitor box before relying on it.
- **Minimized:** fails by design — Windows stops compositing a
  minimized window's surface (documented OBS behavior across capture
  methods). The mirror must never minimize. Enforce in the mirror
  window: strip `WS_MINIMIZEBOX` and ignore `SC_MINIMIZE` in
  `WM_SYSCOMMAND`, mirroring how the preview host already pins its own
  window states. A "minimize to nothing" desire is satisfied by covered
  on-desktop parking instead.

So the answer to "must the user see it": **on one monitor, yes, it will
occupy screen area that can be covered but not closed (never minimized,
never off the desktop edge).** With two or more monitors, the mirror
parks on the secondary's visible area and the user never looks at it.
Never minimized.

Field evidence already narrows this probe. Tested against real
`eve.exe` clients: Discord streams the **covered** window (its capture
path reads occluded window content — the occlusion worry is dead), and
it picks **one window per registered process by its own heuristic**,
with no per-window choice offered at stream start. What the probe still
must answer:

1. **Tier:** does DWM-composited thumbnail content survive Discord's
   game capture at all (vs black)?
2. **Pinning heuristic:** with exactly one streamable window in the
   registered process, does the pin land on the mirror — including
   when the mirror was created *after* the game was registered, sits
   at the bottom of the z-order, and was never focused?
3. **Style sweep:** if step 2 fails for a normal window, does window
   styling (caption strip, toolwindow flag) change the outcome — i.e.
   what does Discord's enumerator prefer or skip? This step rules
   styles in or out; it does not license shipping them by default.

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
   per fight.** A second chord while live is the toggle that ends the
   fleet's feed; no start can fire while an episode is open, so that
   toggle-off is unreachable from Wingman.
   *(Decided 2026-10-06, field finding: the presses ALTERNATE — the
   chord is a toggle, so when every latch has expired the worker presses
   the same chord once more to END the stream; without the stop press the
   stream runs forever and the next fight's start press toggles it off
   mid-fight. An episode opened by Wingman and closed only by the stop
   press, a chord cleared mid-episode, a mirror death, or a failed
   send — the stop's gates mirror the start's. Manual chord presses
   mid-episode can still desync the alternation; the collision warning
   on the card covers it.)*
3. **Confirmation.** Focus gate (no chord while the user is typing into
   a text field is unknowable; but no chord while Discord itself is
   foreground) + a visible state row in the card (Streaming section): armed
   characters, chord, last-fired time and character. "An alert you
   configured and cannot tell is running is the failure mode" applies
   verbatim to a background key-presser. Trigger is the gated combat
   alert only (`AlertPolicy.handle` funnel — PvE filter inherited); NPC
   fire never reaches it.
   *(Decided 2026-10-06: the Discord-foreground gate is REMOVED — the
   chord is the user's own Discord bind, so firing with Discord focused
   equals the user pressing their own keybind. The gate's read also
   never worked: it looked `QueryFullProcessImageNameW` up on user32
   (kernel32 owns it) and called `GetForegroundWindow` unpinned, which
   truncates the 64-bit HWND — 30/30 live reads returned None on the
   field box. The state row and the funnel above are unchanged.)*

## Settings surface

New top-level **Streaming** section (decision, 2026-10-05: a dedicated
section rather than Settings -> Alerts, which earlier revisions assumed;
the combat trigger remains fed by the alert chain regardless). One card,
split-named per the same decision:

```
Discord streaming
  Stream mirror: [Not running - Start mirror]   (wingman-mirror.exe; what Discord pins)
  Keybind: [Ctrl+Alt+D] (capture button)        <- recording = consent
  -- Combat auto-start --------------------------------------
  After-combat delay: [300] seconds
  -----------------------------------------------------------
  Armed for: Kuan Dai, xX_Sigma_Xx
  Last fired: 12:41 . Kuan Dai
```

Keys under `preview.alerts.stream_coupling`: `chord` (AHK-style, `^!d`),
`quiet_s` (60-900, default **300**), `mirror_on` (the one toggle that is
not consent - the mirror alone is useful; per the lifecycle decision it
**persists and is restored at Wingman launch**, shipped default off).
The Go Live automation remains chord-derived.

## Architecture

- **Mirror process:** new `wingman/streaming/mirror.py` — module used
  both as the mirror exe's `__main__` and (its logic half) as the
  unit-tested seam: window creation at `HWND_BOTTOM`, no-activate,
  never-minimize; thumbnail rebind via the `preview/thumbnail.py`
  wrappers; foreground consumption via the same
  `EVENT_SYSTEM_FOREGROUND` shape `preview/host.py:3297` runs (own
  message-pump thread — the host already proves the only legal thread
  shape). Source-client instructions via status/INI file, engine-style.
- **Supervision:** `HotkeyEngine`'s job-object pattern: spawn, bind to
  kernel Job object (dies with Wingman, no orphans), status-file
  handshake, orphan recovery on restart. New `wingman/streaming/
  mirrorsupervisor.py`, or an extension of `hotkeys.py`'s generic
  pieces — decide at implementation.
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
- **Mirror process fails or never starts** (missing exe, DLL error):
  supervisor restarts it like the engine (bounded retries, then shows
  the error in the mirror card row); feature stays inert without a
  mirror window to pin.
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

## Decisions (2026-10-05, #312 review)

1. **Name — split.** The card is "Discord streaming" (mirror as the
   card's subject) with a "Combat auto-start" section inside. "Stream
   coupling" remains the settings-key namespace and internal name.
2. **Quiet-period default: 300 s** (range 60-900 unchanged). The
   asymmetry decided it: too short risks the mid-fight toggle-off that
   ends the fleet's feed; too long only misses a second fight the user
   can start by hand.
3. **Placement: new top-level Streaming section**, not Settings ->
   Alerts. The card hosts the mirror as its subject; the combat trigger
   keeps its alert-chain feeding and armed-row language regardless.
4. **Mirror lifecycle: sticky on-demand.** `mirror_on` persists; when
   Wingman launches it restores the mirror if it was on. Shipped default
   off. Closes the reboot trap (configured user, mirror not running,
   chord fires into nothing) without an always-on helper process for
   installs that never use Discord.
5. **Chord with no EVE client focused: fire anyway.** The mirror shows
   the last client; the fleet sees something at contact, which is the
   ask's core. Hold-until-focus was rejected: it needs
   hold-without-consuming-latch machinery (a hold that consumes the
   episode latch is just a silent skip) and can leave the fleet with
   nothing for a whole fight - the failure the feature exists to
   prevent. The armed row is the user's visibility into what the mirror
   would show.

(Also resolved by the visibility states, recorded earlier: single-
monitor users see a mirror they can cover but not minimize - a UX
preference, not a feasibility question.)

## Probe harness

`scripts/capture_visibility_probe.py` + `docs/combat-golive-probe.md`
implement the capture-visibility gate's manual probe: the throwaway
process builds the rev-3 mirror faithfully (top-level, captioned,
HWND_BOTTOM at creation, never activated, never minimized) and walks the
tier leg, the pin leg, the style sweep and the minimize confirmation.
Result template lives in the runbook; the tier result is recorded in
#312 and gates all feature work.
