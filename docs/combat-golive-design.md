# Combat-triggered Discord Go Live: automatic stream start on combat

Status: proposed — this is the spec the user asked for after feasibility
research; nothing is implemented. The verdict it records: **possible, one
good mechanism, several hard product constraints that shape it.**

## The request

"Whenever the combat log detects combat, Discord automatically starts
streaming your screen (if you're in a voice channel)."

The audience reads this as fleet logistics, not content creation: the
fleet can see what you see at the moment contact happens, without you
finding the Go Live button while taking damage. The ask is latency
(`stream up before the first volley finishes`) and zero attention cost,
which is the same argument PRODUCT.md records for alerts interrupting at
all.

## Why Discord cannot be told to start a stream

The research this spec rests on (checked 2026, current client):

- Discord's documented local API — RPC over a named pipe
  (`\\.\pipe\discord-ipc-{0..9}`), commands AUTHENTICATE, SELECT_VOICE_CHANNEL,
  GET_SELECTED_VOICE_CHANNEL, SET_VOICE_SETTINGS, SET_ACTIVITY — has no
  command that starts Go Live. The community-maintained protocol reference
  (discord-userdoccers), which documents even the undocumented commands, lists
  none either. Deep links go to channels, never into a stream.
- The user-facing surface that does start one is a **user-configured global
  keybind**: User Settings → Keybinds → **Toggle Screen Share**. Global
  keybinds are system-wide (RegisterHotKey); they fire with any window
  focused, including EVE. This is supported user configuration, not a
  hack — but automating it from a third-party process is an unofficial
  integration surface and could change in any client update.
- "If you're in a voice channel" self-resolves: the keybind no-ops when no
  stream is possible. Detection would need the RPC app-approval dance; it
  is deliberately out of scope.

So the only mechanism is: Wingman synthesizes the user's own Discord
keybind chord with `SendInput` (pure `ctypes`, the house Win32 style —
same lazy-bind approach as `preview/win32.py`, no new dependency). Discord
does the streaming; Wingman only presses a key the user mapped.

## The hard lines it touches, and how it stays inside them

PRODUCT.md's "What it must not become" contains the two lines this feature
collides with. Both are quoted there verbatim; this is the resolution the
implementation must satisfy, not a reinterpretation of the lines:

1. *"It must not upload anything the user did not select. Nothing leaves
   the machine without an explicit action."*
2. *"It must not automate gameplay. It sends keystrokes the user pressed,
   to a window the user is looking at. It does not act for them."*

The resolution: **the user pressed that chord — once, in advance — and
selected the stream source in Discord, once, in advance.** The feature is
a held-open gate on an explicit configuration, not an autonomous action.
The counterfactual test: if Wingman is closed mid-combat, nothing happens
that the user did not already configure; Discord and the keybind behave
exactly as before. What Wingman adds is only *when* the configured chord
is pressed.

Three rules keep the letter of line 2:

- **The chord is the user's own Discord keybind**, read from a Wingman
  setting, not a fixed one Wingman chose. Wingman never invents a chord;
  the user maps it in Discord first, then records it here.
- **A capture, not a broadcast:** the chord is sent to whatever window has
  focus exactly like a user keypress (no target-window routing, no
  activation of the Discord window). The focus rule of PRODUCT.md's
  automation line is preserved mechanically: if the user is looking at
  Wingman or a browser, that is where their keys land, which is also why
  the confirm-loop below exists.
- **Never stop a stream.** The bind is a toggle; a blind keypress when
  already live ends the fleet's feed. V1 has no auto-stop at all — the
  stream runs until the user stops it (phase 2 could consult local RPC for
  stream state, behind the same app-approval modal already out of scope).

## What the feature is

A per-character (per-client), gated, one-shot action on the existing
combat alert — not a new alerts event, not an automation system, and not a
fourth anything. Structurally it is to alerts what the combat-log webhook
is to the Uploader: a conditional leg on an existing trigger.

- **Trigger:** the existing, already-gated combat alert
  (`wingman/alerts/service.py:AlertPolicy.handle`, the single funnel at
  its `self._on_alert(...)` dispatch) — this inherits the PvE filter and
  per-event cooldown for free. It must be the gated alert, not the raw
  `AlertEvent` stream in `telemetry/coordinator.py`: an NPC shooting a
  sleeper site must never press keys.
- **Action:** one `SendInput` of the user's recorded chord, once per
  combat episode, per client (character).
- **Never targets EVE input:** the chord goes to the OS like any pressed
  key; EVE is not addressed, activated, or moved. (PRODUCT.md's no-EVE-input
  rule stands; the Fleet Bar's "never sends input to one" phrasing is the
  sibling of this.)

## Guard design: consent, episode-latch, confirmation

Three mechanisms, in the order the code should read them:

1. **Consent gate (the spec's load-bearing wall).** Enabling the feature
   is one explicit opt-in whose value is *not a checkbox* — it is the
   keybind itself. The user must first map Toggle Screen Share in Discord,
   then press-and-record that exact chord in Wingman's settings. Recording
   reuses the existing keybind-capture machinery (the layout-aware
   resolver from ADR 0002, `capture_bind` path). No chord recorded = no
   consent = feature inert. This is the shape PRODUCT.md requires for
   anything that leaves the machine: the explicit action is the recording
   of the chord, and it doubles as proof the user did their half of the
   Discord setup.
2. **Episode latch (the anti-thrash guard).** Combat alerts repeat every
   1s (`combat` cooldown is 1s). The action fires only on
   alert→combat **transition** per character: first gated combat alert
   after a quiet period (default 300s of no gated combat alert for that
   character). While latched, the character can take damage, alert, be
   shot at — no further chords. The latch releases on the quiet-period
   expiry, not on any "combat ended" signal (gamelogs have none that is
   dependable; PRODUCT.md already accepts this shape for EWAR expiry).
3. **Confirmation.** Two layers, both required before the chord is sent:
   - **Runtime gate:** the character's client must be an
     admitted, running preview client (the app already tracks admitted
     clients), and — since global keybinds land on whatever is focused —
     the chord is sent only if the user is not already interacting with
     Discord's window (focus check via existing `evewindows.py`-style
     enumeration; if Discord is foreground, the user is mid-Discord and a
     synthetic chord there is an input-desert event).
   - **A visible state row.** The Alerts settings card gains one row:
     stream coupling state, one sentence, e.g. "Combat → Go Live armed
     for Kuan Dai: chord Ctrl+Alt+D fires once per fight; last fired 12:41
     into X-702." It names the character, shows the chord, and carries the
     last-fired fact. PRODUCT.md's corollary — "an alert you configured
     and cannot tell is running is the failure mode" — applies verbatim to
     a background key-presser. A fired chord also raises the existing
     preview pulse on that client, so mid-fleet the user sees *something*
     happen.
     (DESIGN.md's "Only Live and Waiting for source use pills" — no pills
     here, a plain sentence row.)

## What it is not (non-goals)

- Not a new alert event, not a custom rule: it reuses the gated combat
  alert; no new `EVENTS` entry in `alerts/patterns.py`.
- Not a stream manager: no quality, no source picker, no
  channel selection, no auto-stop, no re-stream-on-disconnect.
- Not Discord rich presence. SET_ACTIVITY is explicitly out of scope.
- Not a Fleet Bar or telemetry feature; it reads nothing from fleet
  sharing.
- Not generalized hotkey injection: the injected send is one chord, from
  one recorded setting, behind one latch, and nothing else may reuse the
  primitive without revisiting this spec.

## Settings surface

Settings → Alerts gains one card (or card-section), per existing Alerts
settings shape (`preview.alerts.*`):

```
Stream coupling
  [x] Combat starts a Discord stream          (armed only when a keybind is recorded)
      Keybind: [Ctrl+Alt+D] (capture button)  ← consent: recording = enabling
      Quiet period before re-arm: [300] seconds
      ────────────────────────────────────────────
      Armed for: Kuan Dai, xX_Sigma_Xx        ← admitted preview clients
      Last fired: 12:41 Kuan Dai · in combat 12:41
```

Keys under `preview.alerts.stream_coupling`:
`enabled`(derived from chord presence — see below), `chord` (AHK-style
notation, same stored format as bookmark binds, `^!d`), `quiet_s` (60–900,
default 300).

Deliberate choice: **no separate enabled boolean.** Presence of a recorded
chord *is* the enabled state; this kills an entire class of "checkbox on,
chord empty" dead states and makes the consent story single-token. The
card's armed-row shows per-client armed state; disabling = clearing the
chord (an explicit action).

Settings keys are read live by `AlertPolicy` through its existing
callable-inputs pattern (see `set_alert_pve_filter`'s docstring) — no
restart, no reconcile for the chord value; the controller reads it per
alert.

## Architecture

Follows the controller/ports template (`evesettings/controller.py`,
PR #175; `AlertsPorts` today):

- New port on `AlertsPorts` (or a sibling `StreamCouplingPorts` if the
  alerts ports object should stay presentation-only — decide at
  implementation): `dispatch_combat_stream(character: str) -> None`,
  implemented by the new controller.
- New controller `wingman/alerts/streamcoupling.py` (name may change to
  match house naming at implementation): owns the episode latches
  (per-character), the quiet-period bookkeeping, the confirm gate, and
  the send. It imports nothing from `ui`, never holds the window, and is
  unit-testable on Linux with an injected send-callable — the send seam
  is a constructor parameter, like `discord.py`'s `transport=`. Tests
  inject a fake and assert chord, once-per-episode semantics, consent
  refusal, focus-gate refusal.
- The send itself: `SendInput` with `KEYEVENTF_` flags for the recorded
  chord, `ctypes` through an injected seam (no windll import at module
  top; matches `preview/win32.py` house style), called on a **worker
  thread** owned by the controller — never on the telemetry dispatcher
  thread (AGENTS.md: nothing slow runs there).
- Bridge visibility only: pushes are semantic events
  (`stream_coupling_state`, `stream_coupling_fired`), mirrored to the
  floating sig bar window per the standing push rule. Sort order, row
  focus and selection never cross.
- Wire-in points: `wingman/__main__.py:build_alert_policy` (pass the
  controller's dispatch into `AlertPolicy(on_alert=...)` chain),
  `ui/api.py:_build_alerts_controller`, settings defaults/validator in
  `wingman/settings.py` (`_alerts_defaults`, `validated_alerts`), bridge
  facades in `ui/api.py` (`set_stream_coupling_chord` capture flow, one
  line each, keeping every `_push("literal")` visible to
  `test_bridge_contract.py`).

## Failure modes and what the code must do about them

- **Discord not running / not in voice:** keybind no-ops downstream.
  Wingman cannot tell and does not try: the armed row says "armed", not
  "live". Wording must never claim the stream exists — PRODUCT.md tone:
  say what happened, not what was hoped.
- **Chord collides with an EVE or Windows binding:** the recorded chord
  is pressed exactly as a user chord; if the user mapped the same chord
  in EVE, both fire. Mitigation is user education in the capture
  flow (one-line warning after capture: "This chord also fires in EVE
  while EVE is focused"), not prevent-from-send logic — Wingman cannot
  enumerate Discord's registration, and guessing is worse than warning.
  Suggest-but-do-not-enforce a default of Ctrl+Alt+D in the capture UI's
  helper text.
- **Discord changes the keybind or its behavior:** the integration breaks
  quietly (no stream appears). Same answer as not-running: armed ≠ live;
  last-fired row is the diagnostic. This is accepted, documented risk of
  building on the only user-facing surface Discord exposes.
- **The user is typing / holding keys at fire time:** `SendInput` injects
  chord-down, chord-up with no dwell; modifiers held by the user at that
  instant are not part of the chord and do not corrupt it — but an EVE
  chat box focused at fire time receives the chord and may act on it.
  Accepted risk, listed in the one-line capture warning (same mitigation
  as collision: warn, don't prevent).
- **Rapid re-engagement:** latch + quiet period covers it; the latch is
  per character, so a two-client fight arms twice (each client's own
  first combat), which is correct: two previews, two clients, one stream
  (Discord dedupes; a second chord while live is the toggle hazard —
  see below).
- **Second chord while live (the toggle hazard):** real and harmful —
  it stops the fleet's feed. V1 accepts it: multi-client fights are
  exactly the multiboxing case, and V1's latch is per character. The
  episode latch therefore needs a **process-wide arm/disarm at the
  first fire** (single global latch overlaying the per-character ones):
  the first fired chord disarms every character until the quiet period
  expires **for all of them**. This is the spec's most important
  behavioral sentence: **one stream per fight, Wingman presses once.**
  (Phase 2, via local RPC + Discord application approval, could query
  live-state and re-arm safely; V1 does not.)

## Verification plan

- Unit (Linux, no Windows APIs imported): controller tests inject a fake
  send and assert — consent refusal with no chord; fire-once-per-episode;
  process-wide disarm after first fire; quiet-period re-arm; focus-gate
  refusal when the chord's target is foreground; live-update of armed
  row payload.
- Native seam test (Windows-only, skipped on Linux like other seams):
  `SendInput` round-trip via `GetAsyncKeyState` or a test AHK listener —
  the same kind of native seam test the repo already carries for hotkeys.
- Settings round-trip: chord round-trips through
  `settings.update()`/`validated_alerts`, capture flow validates against
  the layout-aware resolver (ADR 0002) and degrades with the same
  visible one-line warning shape.
- Hand pass against `docs/smoke-checklist.md` for the settings card:
  capture button, armed row, quiet-period control, and the "no chord =
  inert" state.

## Phase 2 candidates (not in V1, listed so V1 doesn't grow them)

- Local-RPC voice/stream-state detection (requires Discord application +
  one-time user approval modal): query `GET_SELECTED_VOICE_CHANNEL`,
  potentially a live-state query, enabling safe re-arm mid-fight and
  in-voice preconditioning ("armed only when in voice").
- Auto-stop after quiet period (toggle-off risk returns; needs the same
  RPC state query).
- Fleet-coordination semantics (who streams when three wingmen's Wingman
  installs all see the same fight — out of scope, probably belongs to
  fleet sharing, not local keybinds).

## Open questions for the human

1. Name: "Stream coupling" is this spec's working term (it couples the
   stream start to an alert event); "Combat → Go Live" reads plainer.
   Which do users call it?
2. Does the quiet period default of 300s match how often your fleet
   refights? 60–900s is the range.
3. Single-monitor setups: stream source is whatever Discord last used;
   if that was "Entire Screen" on a single-monitor box, the stream shows
   the desktop, not EVE. Is that acceptable for V1, or does the capture
   flow need a "check Discord's last source" checkbox step in setup?
4. Should the feature live in Settings → Alerts, or in Settings →
   Uploading beside Combat logs (it is stream-to-viewers, not alerting)?
   This spec assumes Alerts (the trigger is the alert funnel; the feature
   produces no screen of its own), but Uploading is arguable.
