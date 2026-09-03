# Floating fleet DPS and EWAR bar

## Summary

FlyGD Wingman will add a second floating desktop bar for monitoring a multibox fleet during combat. The bar is independent of the floating signature bar and preview thumbnails. It shows one stable row per currently running, logged-in EVE client:

```text
Character name | outgoing DPS | incoming EWAR
```

The first release guarantees outgoing DPS and incoming warp tackle. Successful ECM jams are included only if implementation is backed by a real gamelog fixture that proves successful-jam detection and target attribution. Unsupported EWAR is omitted rather than inferred.

The linked EVE MultiPreview implementation is a behavioral reference for gamelog-derived combat statistics, not code to copy. Wingman will use its own architecture, visual system, and test corpus.

## Goals

- Show every active multibox character in one compact, always-on-top view.
- Make inactive or poorly applying damage characters apparent during short fights.
- Identify which character is receiving detectable incoming EWAR.
- Operate when preview thumbnails are disabled.
- Reuse one authoritative client-discovery path and one authoritative gamelog reader across features.
- Remain truthful when logs, attribution, or an EWAR signal are unavailable.
- Preserve Wingman's existing alert behavior and keep Alerts, Previews, and the fleet bar independently switchable.

## Non-goals

- Aggregate fleet totals or DPS rankings.
- Incoming DPS.
- Per-character configuration, custom ordering, or row actions.
- Color, opacity, font, timeout, or rolling-window preferences.
- CSV or historical statistics.
- Reading game memory, inspecting the EVE UI, or automating gameplay.
- Moving or resizing real EVE client windows.
- Detecting web, sensor damp, tracking or missile disruption, target paint, neut, or nos without verified attributable gamelog evidence.
- Distinguishing warp scram from warp disrupt when the available semantic model cannot do so reliably.

## User experience

### Window and rows

The fleet bar is a separate frameless, always-on-top window. It is independently enabled, positioned, restored, and hidden from the existing signature bar.

The bar uses a fixed-width, single-column list supporting up to ten simultaneous logged-in clients without scrolling. Rows are approximately 32 to 34 CSS pixels high and remain in case-insensitive alphabetical order. Every active character remains visible even when quiet, so row positions do not jump as damage or EWAR expires.

Each row has three aligned columns:

1. Character name
2. Whole-number outgoing DPS followed by `dps`
3. Incoming EWAR state

Character names truncate with an ellipsis. DPS uses tabular monospace figures. Healthy rows with no current EWAR show an em-dash in the EWAR column. Live tackle shows one compact `SCRAM/POINT` tag. A verified successful ECM event shows `JAM`.

The full surface is a drag region. The bar is display-only: it does not activate clients, clear effects, or expose row actions. Text selection is disabled so dragging remains predictable.

The page measures its laid-out dimensions and asks Python to fit the native window, following the signature bar's safe resize pattern. Dynamic height changes retain the user's chosen anchor as far as possible while clamping Wingman's own window into the nearest monitor work area. A disconnected monitor must not strand the bar off-screen.

### Empty and degraded states

The bar distinguishes these states:

- **Healthy, quiet character:** `0 dps` and an em-dash.
- **Live EWAR:** the corresponding compact tag.
- **No attributable live log for one character:** an em-dash for DPS and muted `NO LOG` in the EWAR column.
- **Gamelog folder or reader unavailable:** one compact global status row, with the active character roster retained beneath it.
- **No active clients:** one `No active clients` row. The enabled window remains visible and draggable.
- **Window creation or show failure:** both controls revert to off and report the failure instead of claiming the window is visible.

A zero is a real observed value. An em-dash means Wingman cannot currently calculate the value. These states must not look interchangeable.

### Controls

Configuration lives in **Settings > Previews** because the output is a floating client surface, while the underlying setting remains independent of preview thumbnails.

The section contains one wrapped checkbox using the standard `.check` and `.box` markup. Its nearby status text reports whether the bar is visible and whether the Gamelogs dependency is available. Missing Gamelogs configuration is explained with the existing folder terminology.

A quick show/hide button sits in the main status strip beside the signature-bar button. The Settings checkbox and quick button reflect the same persisted state and update together. Enabling the fleet bar does not enable preview thumbnails, alerts, sounds, or alert flashes.

No additional user-facing preferences ship in the first release.

## Architecture

### Shared client discovery

Client discovery becomes reusable infrastructure rather than an inseparable part of preview rendering.

A client-discovery service owns the periodic Windows scan and publishes immutable roster snapshots containing the identity needed by consumers, including HWND, PID, and the title-derived logged-in character name. It preserves the repository's existing EVE window acceptance and identity rules.

Consumers include:

- Preview rendering, only when Previews is enabled.
- Alert focus and roster behavior where currently required.
- Fleet Metrics, whenever the fleet bar is enabled.

Starting discovery for the fleet bar must not create preview windows, register preview-only behavior, or make Alerts eligible. Generic character-selection titles remain unnamed and do not produce fleet rows. Characters excluded from preview thumbnails still appear in fleet snapshots when their logged-in clients are running.

### Shared gamelog stream

One generalized gamelog stream owns:

- Folder discovery and health.
- One active session file per character.
- File positions and partial-line buffering.
- Initial EOF baselining.
- Rotation and relog handling.
- Replay prevention when folders or files disappear and return.
- Timestamp parsing and semantic fact publication.

The stream runs whenever Alerts or Fleet Bar needs it. Enabling one consumer does not alter the other's setting or policy.

The stream emits timestamped facts rather than alert decisions. Existing incoming damage, miss, tackle, and decloak facts continue feeding Alert policy without changing their behavior. The additional facts needed by this feature are:

```text
outgoing_damage(character, occurred_at, amount)
incoming_tackle(character, observed_at)
incoming_jam(character, observed_at)
```

Alert policy remains responsible for cooldowns, sounds, flashes, persistence, foreground suppression, and PvE filtering. Fleet Metrics does not consume post-policy alert events because disabled alerts and cooldowns must not suppress combat state.

Parsers are pure and fixture-driven. Existing incoming-alert behavior remains covered while outgoing damage support is added for verified direct and drone damage shapes. Numeric parsing, markup stripping, target ownership, and malformed lines are tested independently from I/O.

### Fleet Metrics

Fleet Metrics is a pure, clock-injected state component. It consumes roster snapshots and semantic gamelog facts, then publishes complete fleet snapshots on a one-second cadence.

For each character, it owns:

- A bounded deque of recent outgoing damage facts.
- Monotonic EWAR expiry deadlines.
- Whether an attributable current gamelog is available.
- The current client session identity needed to prevent relog carry-over.

It joins state against the current named-client roster and emits case-insensitively alphabetized rows. Removing a client immediately removes its row and clears that session's accumulated metrics. A rapid relog begins cleanly.

### Fleet-bar controller and WebView

A fleet-bar controller owns the auxiliary window reference, restore/toggle behavior, targeted bridge pushes, fitting, work-area clamping, and position persistence.

The window follows the established signature-bar constraints:

- Lazy pywebview import.
- Underscore-prefixed references on `Api`.
- `frameless=True`, `on_top=True`, `easy_drag=False`.
- Explicit minimum native size.
- Hidden creation followed by initial state, fit, and reveal.
- No pywebview `shown` or `moved` handlers.
- Position saved from page `mouseup`, not native move events.

Fleet updates are sent only to the fleet window. They are not added to the main page or signature bar's generic push fan-out. The standalone page registers plain global handlers and does not load the main page shell.

## Metric semantics

### Outgoing DPS

DPS is:

```text
sum(outgoing damage with timestamp in (now - 10 seconds, now]) / 10
```

The denominator is always ten seconds. Quiet time is part of the window. This prevents the first volley from being presented as an inflated one-second rate and makes values comparable across characters.

The EVE log timestamp places damage in the window. Reading time is not used because filesystem buffering can deliver several older lines in one batch and create a false spike. Events outside the valid current session or replay horizon are rejected.

Snapshots continue every second without new lines so values decay and reach zero. Values display as rounded whole numbers. Outgoing player and NPC damage are both included; the Alerts PvE filter does not affect Fleet Metrics.

### Incoming tackle

An attributable `Warp scramble attempt` or `Warp disruption attempt` refreshes one combined `SCRAM/POINT` state for that character. The state expires eight seconds after the latest matching event using a monotonic deadline.

The tag reports the best state the gamelog supports, not confirmed server-side application. Existing fleet-broadcast ownership checks remain mandatory so one pilot's tackle does not appear on every row.

### Successful ECM jam

`JAM` expires 22 seconds after the latest verified successful-jam event using a monotonic deadline.

JAM is a release-gated capability. It ships only when a real sample demonstrates all of the following:

- The message represents a successful jam rather than an attempt or failure.
- The affected character can be attributed safely.
- Third-party or fleet-broadcast copies do not create false rows.
- A pure parser fixture and ownership tests cover the real shape.

If those conditions are not met during implementation, the event type and UI tag are omitted from the release. The design does not authorize guessing a parser string.

### Unsupported EWAR

Webs, damps, weapon disruption, painters, neuts, and nos are not displayed. Current evidence does not establish reliable, attributable gamelog entries for them. The architecture may accept future verified facts without changing the row model, but no generic `EWAR` fallback is shown.

NPC-applied and player-applied tackle or verified jams are both shown. Tactical state is not filtered by the Alerts PvE preference.

## Persistence

A new top-level settings section keeps this feature independent of `preview` normalization:

```json
{
  "fleet_bar": {
    "enabled": false,
    "x": null,
    "y": null
  }
}
```

It defaults off because it starts shared background work and creates another WebView2 host. `null` coordinates use a measured default placement. Settings normalization rebuilds and validates this section on every load and save. Unknown or malformed values fall back safely.

The section is top-level even though its UI is under Settings > Previews. Configuration location describes where the user expects to find the control; schema ownership describes runtime independence.

The EVE-tools visibility guard treats an enabled fleet bar as active EVE functionality, so its only off switches cannot be hidden while it continues running.

## Lifecycle and concurrency

A coordinator reconciles infrastructure against active consumers:

- Client discovery is wanted by Preview rendering, Alerts where needed, or Fleet Bar.
- Gamelog streaming is wanted by Alerts or Fleet Bar.
- Consumers attach and detach independently.
- Infrastructure starts once on the first consumer and stops after the final consumer detaches.

Published roster, fact, and metric snapshots are immutable. Callbacks crossing from discovery or gamelog threads must catch consumer exceptions so one failed UI push cannot terminate a polling or Win32 message thread.

At application startup, persisted runtime consumers are reconciled before auxiliary windows need their first state. Auxiliary WebViews are created only after pywebview's main loop is running. The fleet bar is restored hidden, receives a complete snapshot, fits, and then appears.

On quit, the fleet bar and signature bar are destroyed before the main WebView. This ordering is mandatory because pywebview's WinForms loop remains alive while any auxiliary window survives. Shared workers stop and join after their consumers detach, preserving the existing non-daemon shutdown guarantees.

## Error handling and health

The shared gamelog stream exposes health that distinguishes:

- Disabled because no consumer needs it.
- Missing or invalid configured folder.
- Running and current.
- Character not matched to a current session file.
- Poll stale or worker stopped.
- Last read or parse error.

A successful poll clears a prior transient error. Folder existence is checked continuously enough that an unmounted or removed folder does not remain falsely healthy.

Malformed or unsupported log lines are ignored without stopping the stream. A per-file read failure costs that source's update, not every character's update. Useful exception context is retained in logs while the fleet page receives only concise semantic status.

Window creation, show, resize, move, and push failures are contained and logged. Toggle endpoints return the repository's standard applied/persisted/error result shape where applicable.

## Testing

### Pure behavior

- Real fixtures for outgoing direct and drone damage.
- Amount parsing, separators, markup, malformed and partial lines.
- Existing tackle ownership, including third-party fleet-broadcast copies.
- Successful ECM parsing and attribution only if the real fixture gate is met.
- Fixed ten-second denominator and exact boundary inclusion.
- Event timestamps rather than ingestion timestamps.
- One-second idle decay to zero.
- Tackle refresh and eight-second expiry.
- Jam refresh and 22-second expiry if enabled.
- Roster join, case-insensitive ordering, preview-excluded inclusion, and relog clearing.
- NPC and player damage/EWAR inclusion.

### Shared infrastructure

- One discovery scan fans out to independent consumers.
- Fleet-only mode creates no preview thumbnails and activates no alert policy.
- One gamelog cursor feeds Alerts and Fleet Metrics.
- First-scan EOF baseline prevents history replay.
- New live files are read from the correct initial position.
- Rotation, relog, folder loss/recovery, cap eviction, transient stat/header failure, and partial writes do not replay old combat.
- Consumer callback failures do not terminate shared workers.
- Start/stop reconciliation and final joins are idempotent.

### Settings, bridge, and windows

- Defaults, validation, normalization, round-trip persistence, and malformed data.
- Independent fleet and signature bar settings and positions.
- Synchronized Settings and status-strip toggles.
- EVE-tools visibility guard.
- Targeted fleet pushes do not fan out to unrelated pages.
- Standalone handler names and packaged web assets.
- Fit deduplication/retry behavior and work-area clamping.
- Empty and degraded states.
- Creation/show failures revert controls honestly.
- Restore after startup and auxiliary-before-main shutdown order.
- `Api` exposes no public non-method attributes.

### Manual Windows smoke pass

The smoke checklist will cover:

- 100%, 125%, 150%, and 200% display scaling.
- Both floating bars enabled together.
- Main Wingman window visible and hidden.
- Previews disabled while Fleet Bar remains active.
- Alerts disabled while Fleet Bar remains active.
- One through ten active logged-in clients.
- Client login, logout, relog, and character-selection transitions.
- Active DPS, idle decay, tackle refresh/expiry, and any verified jam event.
- Missing, removed, and restored Gamelogs folders.
- EVE and OBS foreground transitions.
- Drag persistence and monitor disconnect/reconnect.
- Application quit with all auxiliary windows visible.

The existing stale signature-bar smoke instructions for removed color and opacity controls should be corrected while this adjacent checklist is updated.

## Compatibility and packaging

- Existing settings files gain an off-by-default `fleet_bar` section through normalization; no existing behavior changes until enabled.
- Alerts retain their current settings, event policy, colors, sounds, cooldowns, and preview flashes.
- Preview exclusion continues to mean thumbnail exclusion only.
- The pinned `pywebview==6.2.1` version is unchanged.
- New web assets are included by the frozen build and asserted by packaging checks.
- If a new Python subpackage is introduced, it is added to the explicit setuptools package list and packaging completeness tests.
- No new runtime dependency is required.

## Acceptance criteria

1. Enabling Fleet Bar with Previews and Alerts disabled shows a draggable, topmost `No active clients` window and starts no preview or alert behavior.
2. Each logged-in EVE client produces one alphabetically stable row, including clients excluded from preview thumbnails.
3. Verified outgoing damage appears as a fixed-window ten-second DPS value and decays to zero within the defined cadence.
4. An attributable tackle event displays `SCRAM/POINT` only on the affected character and expires after eight seconds without refresh.
5. JAM appears only if the successful-event fixture gate is met; unsupported EWAR never produces guessed labels.
6. Missing per-character logs and global reader failures are visually distinct from healthy zero DPS.
7. The fleet and signature bars can be enabled, positioned, hidden, restored, and shut down independently.
8. Removing and restoring a log folder or rapidly relogging cannot replay historical combat into the DPS window.
9. Quitting with both auxiliary bars visible exits cleanly with the required window and worker shutdown order.
10. Automated checks pass, and the completed Windows smoke checklist records the visual/runtime pass that pytest cannot provide.
