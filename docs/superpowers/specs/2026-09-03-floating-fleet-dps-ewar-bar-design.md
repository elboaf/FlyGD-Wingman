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

The page measures its laid-out dimensions and asks Python to fit the native window, following the signature bar's safe resize pattern. Python obtains the nearest monitor with `MonitorFromRect` and its physical work area with `GetMonitorInfoW.rcWork`, then converts that rectangle to the logical units pywebview uses with the process's system scale.

On every fit, Wingman derives horizontal and vertical anchors from whichever work-area edges are nearest to the window's pre-fit rectangle. It preserves those edge distances while applying the new dimensions, then clamps the complete rectangle inside the work area. Deriving the anchor again from persisted `x` and `y` on restore avoids another persisted setting. If content ever exceeds a work area, the window is capped to that work area, placed at its top-left, and the page permits vertical wheel scrolling as a defensive fallback; the supported one-to-ten-client layout must fit without scrolling at the smallest work area covered by the smoke pass. After monitor removal, the nearest remaining work area is selected and at least a 32 by 32 logical-pixel drag region remains visible even if native geometry prevents a full clamp.

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

The extra 44-pixel button is not assumed to fit mechanically. Implementation must measure the status strip at both known 839/840 CSS-pixel floors with both quick buttons, the full EVE segment, maximum representative status text, a visible percentage, and active upload progress. Upload status and progress have priority, followed by the two quick controls. The EVE readout is the first segment that yields, matching its existing priority; if flex shrink would clip it into misleading partial values, a measured reachable rule hides the complete EVE readout for that stressed state instead. The verification records the chosen breakpoint and resulting progress-track width.

No additional user-facing preferences ship in the first release.

## Architecture

### Shared client discovery

Client discovery becomes reusable infrastructure rather than an inseparable part of preview rendering.

A client-discovery service owns read-only EVE-window enumeration and publishes immutable roster snapshots containing a monotonically increasing generation plus each client's HWND, PID, and title-derived logged-in character name. It preserves the repository's existing window acceptance and identity rules. A client session is identified by `(HWND, PID, character, first_seen_generation)`, where `first_seen_generation` remains stable while that tuple remains continuously present. A changed HWND/PID or a name disappearing and returning creates a new session for Fleet Metrics; an ordinary unchanged scan does not.

The service runs its scans on one owned execution context. Its ordinary cadence remains no slower than the current 700 milliseconds while Previews is enabled. The Preview foreground hook requests an immediate shared discovery sweep rather than directly reconciling windows, preserving the current low-latency foreground behavior.

Consumers include:

- Preview rendering, only when Previews is enabled.
- Alert focus and roster behavior where currently required.
- Fleet Metrics, whenever the fleet bar is enabled.

A Preview adapter posts each discovery snapshot onto `PreviewHost`'s Win32 message pump. Preview reconciliation, identity continuity, selection, EVE show-state calls, and preview-HWND mutation continue only on that pump. The adapter records the latest applied generation and rejects stale or duplicate snapshots, so a delayed ordinary scan cannot overwrite a newer foreground-triggered scan. Consumer callbacks never reconcile Preview state directly on the discovery execution context.

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

Selection or retirement of a source emits an immutable lifecycle snapshot before any facts for the corresponding generation. It contains the stream generation, character, normalized path/file identity, UTC session start, availability, and active/retired state. Every semantic fact carries that same source generation and file identity. Source lifecycle snapshots and facts travel through one serialized dispatcher, preserving their order. Facts buffered from a retired or superseded generation are discarded.

The coordinator stamps roster snapshots, source lifecycle snapshots, and facts with one monotonically increasing telemetry sequence before serialized consumer delivery. When a newly identified client session arrives, it requests a fresh publication of that character's current source lifecycle state, including an unavailable state when no source exists. Fleet Metrics binds the client only to a source lifecycle envelope sequenced after that session's first roster envelope. This establishes ordering across the otherwise independent roster and stream generations without treating every roster scan as a new session.

The stream's runtime predicate is exactly:

```text
fleet_bar.enabled || (preview.enabled && preview.alerts.enabled)
```

A valid Gamelogs folder is still required before the worker polls. The first term permits fleet-only telemetry. Only the second term makes Alert policy eligible, preserving the existing rule that Alerts are inert when Previews is disabled. Enabling one consumer does not alter the other's setting or policy.

The stream emits timestamped facts rather than alert decisions. Existing incoming damage, miss, tackle, and decloak facts continue feeding Alert policy without changing their behavior. The additional facts needed by this feature are:

```text
outgoing_damage(character, source_generation, source_id, occurred_at, amount)
incoming_tackle(character, source_generation, source_id, occurred_at)
incoming_jam(character, source_generation, source_id, occurred_at)
```

Alert policy remains responsible for cooldowns, sounds, flashes, persistence, foreground suppression, and PvE filtering. Fleet Metrics does not consume post-policy alert events because disabled alerts and cooldowns must not suppress combat state.

Parsers are pure and fixture-driven. Existing incoming-alert behavior remains covered while outgoing damage support is added for verified direct and drone damage shapes. Numeric parsing, markup stripping, target ownership, and malformed lines are tested independently from I/O.

### Fleet Metrics

Fleet Metrics is a pure, clock-injected state component. It consumes roster snapshots and semantic gamelog facts, then publishes complete fleet snapshots on a one-second cadence.

For each character, it owns:

- A bounded deque of recent outgoing damage facts.
- Monotonic EWAR expiry deadlines.
- The active client-session identity and latest roster generation.
- The active log-source generation, file identity, UTC session start, and availability.

A row enters observed state only after the current client session receives an active log-source lifecycle envelope whose telemetry sequence follows that session's first roster envelope. Until then it reports `NO LOG`. A changed client-session identity or log-source generation clears the deque and EWAR deadlines before accepting new facts. A fact is accepted only when its source generation and identity equal the row's current active source and its telemetry sequence is newer than that source's lifecycle envelope; delayed facts from retired sources are ignored. Older roster, source, or fact envelopes cannot roll either side of the join backward.

It joins state against the current named-client roster and emits case-insensitively alphabetized rows. Removing a client immediately removes its row and clears that session's accumulated metrics. A rapid relog begins cleanly and remains `NO LOG` until the stream publishes its matching active source.

### Fleet-bar controller and WebView

A fleet-bar controller owns the auxiliary window reference, restore/toggle behavior, targeted bridge pushes, fitting, work-area clamping, and position persistence.

The window follows the established signature-bar constraints:

- Lazy pywebview import.
- Underscore-prefixed references on `Api`.
- `frameless=True`, `on_top=True`, `easy_drag=False`.
- Explicit minimum native size.
- Hidden creation followed by a page-driven readiness handshake.
- No pywebview `shown` or `moved` handlers.
- Position saved from page `mouseup`, not native move events.

The hidden page waits for `pywebviewready` and `document.fonts.ready`, then calls a fleet-bar readiness endpoint and receives the current complete snapshot as its response. After rendering, it sends its measured dimensions with a boot token to the fit endpoint. Python resizes the native client area, applies work-area anchoring/clamping, and reveals the window only after those operations succeed. A native-not-ready response leaves the window hidden and causes bounded page-side fit retries; no arbitrary reveal timer is used. Subsequent pushes begin only after the controller marks that boot token ready, so an early dropped global-handler push cannot create an empty first frame.

Fleet updates are sent only to the fleet window. They are not added to the main page or signature bar's generic push fan-out. The standalone page registers plain global handlers and does not load the main page shell.

## Metric semantics

### Outgoing DPS

DPS is:

```text
sum(outgoing damage with timestamp in (now - 10 seconds, now]) / 10
```

The denominator is always ten seconds. Quiet time is part of the window. This prevents the first volley from being presented as an inflated one-second rate and makes values comparable across characters.

The parser accepts the EVE line prefix exactly as `[ YYYY.MM.DD HH:MM:SS ]`, with flexible surrounding whitespace but fixed numeric field widths and separators, and constructs a timezone-aware UTC `datetime`. Reading time is not used because filesystem buffering can deliver several older lines in one batch and create a false spike.

Fleet Metrics receives an injected UTC wall clock as well as its monotonic clock. At ingestion, damage older than ten seconds is ignored. A timestamp up to two seconds ahead of the injected UTC clock is clamped to `now` to tolerate one-second log precision and polling boundaries; a timestamp further in the future is rejected and recorded in fleet telemetry health. A malformed or missing timestamp suppresses only the metric fact: body parsing still feeds the existing Alert policy using observed ingestion time, so a timestamp defect cannot silence an alert. Source generation/session checks apply before this horizon check.

Snapshots continue every second without new lines so values decay and reach zero. Values display as rounded whole numbers. Outgoing player and NPC damage are both included; the Alerts PvE filter does not affect Fleet Metrics.

### Incoming tackle

An attributable `Warp scramble attempt` or `Warp disruption attempt` emits an `occurred_at` from the parsed UTC line timestamp. On ingestion, Fleet Metrics computes `remaining = occurred_at + 8 seconds - utc_now`. A non-positive remainder is ignored; a positive remainder is capped at eight seconds and converted to `monotonic_now + remaining`. A delayed filesystem read therefore cannot grant an old tackle event a fresh lifetime.

The combined `SCRAM/POINT` state expires at that monotonic deadline and refreshes only from a newer accepted fact for the active source generation. The tag reports the best state the gamelog supports, not confirmed server-side application. Existing fleet-broadcast ownership checks remain mandatory so one pilot's tackle does not appear on every row.

### Successful ECM jam

A verified successful-jam fact carries its parsed UTC `occurred_at`. Fleet Metrics converts the unexpired portion of `occurred_at + 22 seconds` to a capped monotonic deadline using the same injected-clock rule as tackle; delayed or already-expired jam lines do not create a fresh state. `JAM` expires at that deadline.

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

- Client discovery runs when `preview.enabled || fleet_bar.enabled`.
- Gamelog streaming runs when `fleet_bar.enabled || (preview.enabled && preview.alerts.enabled)`, provided the configured folder resolves.
- Alert dispatch runs only when `preview.enabled && preview.alerts.enabled`.
- Consumers attach and detach independently.
- Infrastructure starts once on the first consumer and stops after the final consumer detaches.

An enabled-but-inert Alerts preference therefore starts no work and plays no sound while Previews is disabled. Fleet-only mode starts the shared discovery and stream but never attaches Alert policy or Preview rendering.

Published roster, source-lifecycle, fact, and metric snapshots are immutable and generation-bearing. Callbacks crossing from discovery or gamelog threads must catch consumer exceptions so one failed UI push cannot terminate a polling or Win32 message thread. Each consumer processes its inputs on one serialized context; the Preview adapter additionally posts onto the existing Win32 pump.

At application startup, persisted runtime consumers are reconciled before auxiliary windows need their first state. Auxiliary WebViews are created only after pywebview's main loop is running. The fleet bar is restored hidden and uses the page-driven snapshot/render/fit/reveal handshake defined above.

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
- Exact `[ YYYY.MM.DD HH:MM:SS ]` UTC parsing, whitespace, invalid dates, future skew, delayed ingestion, and horizon rejection.
- Amount parsing, separators, markup, malformed and partial lines.
- Existing tackle ownership, including third-party fleet-broadcast copies.
- Successful ECM parsing and attribution only if the real fixture gate is met.
- Fixed ten-second denominator and exact boundary inclusion.
- Event timestamps rather than ingestion timestamps.
- One-second idle decay to zero.
- Tackle refresh and eight-second expiry.
- Jam refresh and 22-second expiry if enabled.
- Roster/source generation ordering, stale snapshot rejection, case-insensitive ordering, preview-excluded inclusion, `NO LOG` transitions, and relog clearing.
- NPC and player damage/EWAR inclusion.

### Shared infrastructure

- One discovery scan fans out to independent consumers.
- Ordinary 700-millisecond and foreground-triggered discovery paths carry ordered generations.
- Preview reconciliation is posted to its Win32 pump; stale discovery callbacks cannot mutate it.
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
- A measured 839/840 CSS-pixel status-strip case with both quick buttons, full EVE readout, maximum representative status text, percentage, and active progress; the documented yield order produces no partial values or clipped controls.
- EVE-tools visibility guard.
- Targeted fleet pushes do not fan out to unrelated pages.
- Standalone handler names and packaged web assets.
- Page readiness, snapshot response, fit retry, reveal token, and no-empty-first-frame behavior.
- Physical work-area conversion, derived edge anchoring, full clamp, monitor removal, minimum visible drag region, and oversized fallback.
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
2. Each logged-in EVE client produces one alphabetically stable row, including clients excluded from preview thumbnails; stale roster or source generations cannot repopulate a retired session.
3. Verified outgoing damage from the active log-source generation appears as a fixed-window ten-second DPS value based on its parsed UTC line timestamp and decays to zero within the defined cadence.
4. An attributable tackle event displays `SCRAM/POINT` only on the affected character and only for the unexpired portion of its eight-second event-time lifetime.
5. JAM appears only if the successful-event fixture gate is met; unsupported EWAR never produces guessed labels.
6. Missing per-character logs and global reader failures are visually distinct from healthy zero DPS.
7. The fleet and signature bars can be enabled, positioned, hidden, restored, and shut down independently.
8. Removing and restoring a log folder or rapidly relogging cannot replay historical combat into the DPS window.
9. Quitting with both auxiliary bars visible exits cleanly with the required window and worker shutdown order.
10. Automated checks pass, and the completed Windows smoke checklist records the visual/runtime pass that pytest cannot provide.
