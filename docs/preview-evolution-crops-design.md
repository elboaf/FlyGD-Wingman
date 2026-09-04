# Preview evolution and cropped-region previews

**Status:** Draft for review
**Date:** 2026-09-04
**Wingman baseline:** `c3ee6fecdab98d0c4b13413908a89537954d7e02`
**Reference reviewed:** CJKondur/EVE-MultiPreview at
`2e35b325ae2ee44abf7816e6babc004048b3e76c` (`v2.3.29`)

## Intended outcome

Evolve Wingman's EVE client previews through independent, reviewable slices.
The first major initiative is an independently positioned live crop of one
region of an EVE client. The crop is a Wingman-owned preview window: it never
moves, resizes, positions, or maximizes the real EVE client.

This document does two jobs:

1. It records which ideas found in EVE-MultiPreview fit Wingman, which are
   already present, and which are rejected.
2. It defines the architecture and prototype gates for cropped-region
   previews in enough detail to write a separate implementation plan.

This is not one large implementation commitment. Each roadmap phase must ship
as an independently useful vertical slice. Later experiments remain subject to
separate design approval and measured evidence.

## Product boundaries

The following constraints outrank the feature list.

- Wingman must never move, resize, reposition, or maximize a real EVE client.
  The only permitted client show-state operations remain restore during
  activation and opt-in minimize-inactive. See `PRODUCT.md` under "What it
  must not become."
- A crop mirrors pixels through DWM. It does not read game memory, send input,
  or automate gameplay.
- Clicking a crop may activate its one owning EVE client through Wingman's
  existing activation path. No input is broadcast or synthesized.
- Preview and crop HWND work remains on `PreviewHost`'s pump thread. A WinEvent
  callback, page call, worker, or settings callback may request work but may
  not manipulate those HWNDs directly.
- Alerts remain conservative. New parsable log lines are not automatically new
  alert types; an event must change what the pilot does in the next few
  seconds.
- Uploading must remain independent of all EVE tooling.
- Every settings change uses the repository's transactional settings boundary.
  Crop components do not write the settings document directly.
- The normal app remains useful when previews and crops are disabled; users
  who do not enable them pay no thread, hook, or polling cost beyond what
  previews already require.

## Reference and licensing posture

EVE-MultiPreview's README labels the project MIT but links to a `LICENSE` file
that is absent at the reviewed commit. GitHub reports no detected repository
license. The repository also contains no automated test project.

Therefore its source is reference material, not a copy source:

- Reimplement every adopted idea against Wingman's Python/ctypes architecture.
- Do not copy C#, WPF markup, alert-pattern data, or localization strings.
- Independently establish and test required EVE log phrases.
- Preserve source links in design notes so provenance and differences remain
  reviewable.
- Revisit direct reuse only if upstream publishes a complete license grant and
  any copied material's provenance is clear.

Reference entry points:

- Discovery wakeups:
  [`Services/WindowDiscoveryService.cs`](https://github.com/CJKondur/EVE-MultiPreview/blob/2e35b325ae2ee44abf7816e6babc004048b3e76c/Services/WindowDiscoveryService.cs)
- Window hooks:
  [`Services/WinEventHookService.cs`](https://github.com/CJKondur/EVE-MultiPreview/blob/2e35b325ae2ee44abf7816e6babc004048b3e76c/Services/WinEventHookService.cs)
- Portable layouts:
  [`Models/LayoutPreset.cs`](https://github.com/CJKondur/EVE-MultiPreview/blob/2e35b325ae2ee44abf7816e6babc004048b3e76c/Models/LayoutPreset.cs)
- Layout application:
  [`Services/ThumbnailManager.cs`](https://github.com/CJKondur/EVE-MultiPreview/blob/2e35b325ae2ee44abf7816e6babc004048b3e76c/Services/ThumbnailManager.cs)
- Cropped DWM source rectangles:
  [`Views/CropWindow.xaml.cs`](https://github.com/CJKondur/EVE-MultiPreview/blob/2e35b325ae2ee44abf7816e6babc004048b3e76c/Views/CropWindow.xaml.cs)
- Crop definitions:
  [`Models/AppSettings.cs`](https://github.com/CJKondur/EVE-MultiPreview/blob/2e35b325ae2ee44abf7816e6babc004048b3e76c/Models/AppSettings.cs)
- Localized alerts:
  [`Services/AlertPatterns.cs`](https://github.com/CJKondur/EVE-MultiPreview/blob/2e35b325ae2ee44abf7816e6babc004048b3e76c/Services/AlertPatterns.cs)
- Character-select cycling:
  [`Services/ThumbnailManager.cs#L2858-L2919`](https://github.com/CJKondur/EVE-MultiPreview/blob/2e35b325ae2ee44abf7816e6babc004048b3e76c/Services/ThumbnailManager.cs#L2858-L2919)

## Current Wingman baseline

Wingman already has the important preview foundation:

- DWM thumbnail registration and updates in `wingman/preview/thumbnail.py`.
- A dedicated Win32 message pump in `wingman/preview/host.py`.
- Stable character identity, ephemeral character-select identity, and strict
  process-image verification in `wingman/preview/discovery.py`.
- Physical-pixel, monitor-safe placement in `wingman/preview/geometry.py` and
  `PreviewHost._monitors()`.
- Always-on-top layered windows, owned click-through labels, activation,
  dragging, resizing, aspect locking, and selection rings in
  `wingman/preview/window.py`.
- Transactional, debounced geometry persistence in `wingman/preview/store.py`.
- Direct character hotkeys, all-client cycling, named cycle groups, collision
  reporting, and queued-hotkey folding.
- Per-character exclusion, locking, size, copy, and never-minimize settings.
- Hide-on-lost-focus and opt-in minimize-inactive behavior.
- Combat, warp-scramble, and decloak alerts with PvE filtering, cooldowns,
  sounds, foreground sound suppression, pulses, and acknowledgement.

These are not reimplemented as part of this roadmap. New work extends their
existing ownership boundaries.

## Decision summary for cropped previews

The approved product decisions are:

- A crop is an independent Wingman-owned live window alongside the primary
  preview. It does not replace or alter the primary preview.
- The first production release supports zero or one crop per character and a
  fixed global live-crop cap. That cap is the highest simultaneous count that
  passes the prototype gates, never a count the prototype did not exercise.
- Enabling a crop at the cap is rejected with actionable status. If a
  hand-edited or future settings file contains more enabled definitions than
  the cap, reconciliation opens the case-insensitively sorted first entries,
  reports the rest as cap-suppressed, and keeps every definition editable.
- The schema and component boundaries must permit multiple named crops later,
  but that later feature is not implemented speculatively.
- The prototype uses client-relative pixel coordinates and does not persist
  them as production settings.
- Production persistence uses normalized client-area coordinates as authority,
  retaining original client dimensions and pixel coordinates as diagnostics.
- The user selects a source region in a dedicated, enlarged DWM crop picker,
  not by drawing over the real EVE window.
- Definitions belong to stable character names. Live DWM relationships bind to
  replaceable client HWNDs.
- A crop closes while its character is logged out, at character select, or not
  running. Its enabled definition remains and the crop reopens automatically
  when that character returns.
- Crop windows do not render or duplicate alerts in the first production
  version.
- Clicking a crop activates its owning client through the existing
  asynchronous activation path.
- Crop movement, resizing, lock state, and hide-on-lost-focus behavior follow
  the primary preview contract where applicable.
- `preview.enabled` remains the sole runtime master. Turning it off closes the
  host and every crop while retaining each crop's individual enabled state;
  turning it on starts the host and reconciles enabled crops. Crops never start
  the preview host independently.

## Why a prototype is mandatory

Wingman has measured only a small number of simultaneous DWM thumbnails;
`docs/preview-roadmap.md` records 10–30 as the unmeasured user range. A crop
adds a new top-level HWND and a second DWM relationship for a client. Source
rectangle behavior, mixed-DPI mapping, minimized-client output, z-order, stale
registration recovery, and compositor cost cannot be established by Linux CI.

Persisted UI and settings work begins only after an intentionally disposable
Windows prototype proves those assumptions. The prototype is not a rushed
first production implementation: it has no migration promise and must be easy
to remove if DWM or performance behavior is unsuitable.

## Crop architecture

### Chosen structure

Use a shared low-level DWM primitive with separate primary-preview and crop
controllers.

Do not add a broad `is_crop` mode to `PreviewWindow`. That would entangle crop
behavior with labels, alert frame caches, primary selection rings, and the
current one-window-per-stable-key registry. Do not create a second crop host
thread either; it would duplicate discovery, foreground observation,
activation, visibility, DPI scope, and teardown.

`PreviewHost` remains the one coordinator and one pump-thread owner.

### `wingman/preview/thumbnail.py`

Extend the low-level thumbnail relationship to accept an optional
client-relative source rectangle when updating properties.

- Without a source rectangle, preserve today's full-client behavior exactly.
- With one, set `DWM_TNP_RECTSOURCE` and populate `rcSource`.
- Continue setting `DWM_TNP_SOURCECLIENTAREAONLY`; crop coordinates are relative
  to the EVE client area, not outer-window chrome.
- Surface the HRESULT from registration and update operations rather than
  discarding it.
- Keep policy out of this module. It does not clamp crop coordinates, retry,
  log character names, or decide whether a relationship should exist.

Existing callers must remain source-compatible or be mechanically updated to
pass no source rectangle.

### `wingman/preview/crops.py`

Create a pure, Linux-testable crop-domain module. It owns values and decisions,
not HWNDs.

Responsibilities:

- Prototype pixel rectangle validation.
- Normalized source rectangle validation.
- Pixel-to-normalized and normalized-to-pixel conversion.
- Clamping against current client-area dimensions.
- Minimum useful source dimensions.
- Destination aspect calculation from the selected source region.
- Production schema serialization and validation.
- Future one-to-many schema migration.
- Effective crop state from `enabled`, character availability, and source
  validity.
- Resource-limit policy, including deterministic cap suppression.
- DWM update/recovery state transitions where they can be expressed without
  native calls.

Use named records rather than unstructured tuples at module boundaries. Keep
rounding rules explicit and test exact boundary behavior.

### `wingman/preview/cropwindow.py`

Create one controller for one live crop HWND and its DWM relationship.

Responsibilities:

- Register and destroy the crop window class and HWND.
- Own one `Thumbnail` whose source is the selected client-area rectangle.
- Create, close, show, hide, move, and resize the crop.
- Click to request activation of the owning EVE client.
- Preserve the selected source region's aspect ratio by default.
- Apply resolved lock state.
- Report destination geometry changes to the host.
- Expose enough DWM update context for bounded health recovery.

First-version exclusions:

- No label overlay.
- No alert ring, pulse, badge, or sound ownership.
- No independent hotkey.
- No crop-specific opacity or click-through control.
- No direct settings writes.
- No client discovery.

The crop can reuse small pure geometry and activation helpers, but it must not
inherit a branch-heavy `PreviewWindow` implementation merely to avoid a new
class.

### `wingman/preview/croppicker.py`

The picker is a temporary Wingman-owned window showing an enlarged DWM mirror
of one client. It must not overlay, resize, or otherwise manipulate the real
client.

Flow:

1. The user requests crop selection for a currently available named
   character.
2. The host creates the picker against that character's current HWND.
3. The picker reads the current client-area dimensions.
4. The user drags a rectangle over the displayed mirror.
5. The picker maps the displayed selection into client-area pixels.
6. Cancel closes the picker and returns no proposal.
7. Confirm returns a validated pixel proposal to the host.

Coordinate mapping must account for:

- DWM destination inset within picker chrome.
- Scaling between destination and client-area dimensions.
- The picker's per-monitor DPI scope.
- Negative virtual-desktop coordinates for the destination HWND.
- Integer rounding at all four source edges.
- Picker resize while selecting.
- A client resize or disappearance while the picker is open.

The prototype may use minimal native chrome and diagnostics. Production UI
must provide clear select, reset, confirm, and cancel states without
`window.confirm`, `window.prompt`, or `window.alert`.

### `wingman/preview/host.py`

`PreviewHost` owns crop coordination because it already owns current clients,
foreground state, activation, monitors, the pump mailbox, and shutdown order.

The host must:

- Resolve stable character names to current client records.
- Reject picker requests for anonymous character-select entries.
- Permit only one active picker.
- Close or supersede a picker deterministically.
- Receive a confirmed pixel proposal on its own pump thread.
- For first creation, create a live crop before asking settings to persist it.
- For reselection, keep the old crop authoritative and visible while the picker
  is open. Confirm creates a hidden candidate against the current client HWND,
  using the old destination geometry. After candidate DWM setup succeeds,
  persist the new source while retaining the old definition as rollback state.
  Only then replace the registry entry, show the candidate, and close the old
  crop in one pump turn. Candidate or persistence failure destroys the
  candidate and leaves the old live crop and definition untouched.
- Close a newly created crop if persistence fails, so runtime and disk cannot
  disagree.
- Reconcile live crops after every refreshed client registry and after master
  preview enablement changes.
- Destroy a live crop when its character becomes unavailable while retaining
  the definition.
- Rebind and recreate an enabled crop when the named character returns on a new
  HWND.
- Apply activation, lock, visibility, monitor rescue, and teardown policy.
- Bound DWM recovery attempts.
- Publish semantic status to the UI through the existing callback/API path.

The primary preview registry and crop registry remain separate. The first crop
registry can be keyed by character name. A later multi-crop migration can key
by `(character, crop_id)` without changing primary preview identity.

### API and web layer

The page sends semantic requests such as selecting, enabling, disabling, or
removing a character's crop. It never sends HWNDs or manipulates crop windows.
The exact endpoint names belong in the implementation plan after existing API
patterns are rechecked.

The first production UI should fit the existing Previews character table:

- Characters with no crop: a compact action to select one.
- Available enabled crop: an edit/reselect action and an on/off control.
- Saved but unavailable character: retain configuration and explain that it
  will reopen when the character returns.
- Failed or invalid crop: show actionable status and offer reselection.

Row composition must include every character named by `preview.crops`, in
addition to running, seen, hotkey, and group sources. Crop-definition owners
are protected references for roster pruning, so an unavailable configured crop
cannot age out of the table and become invisible or unremovable. Cap-suppressed
entries remain visible with the reason they did not open.

When the preview master is off, crop controls follow the existing inert
Previews-section treatment. Their definitions and individual enabled states
remain visible but no action may start the host independently.

Do not create a new top-level destination. Crops configure windows that appear
on the desktop, so they remain Settings material under the product's
configuration-versus-destination rule.

## Prototype scope

The prototype is a Windows-only engineering probe on the feature branch.
Whether it is committed, retained under an explicit experimental flag, or
removed after recording results is decided in its implementation plan. It
must never silently become user-facing production behavior.

The prototype supports:

- One temporary picker at a time.
- An interactive path for selecting one named, currently running character.
- A load-test path that instantiates simultaneous ephemeral crops for distinct
  running characters at staged counts of 1, 2, 4, and 8, stopping when a stage
  fails or the machine has fewer clients.
- A hard prototype ceiling of eight live crops. This is a probe guard, not the
  production cap.
- Client-relative pixel source coordinates.
- In-memory destination geometry.
- Click activation.
- Move and aspect-preserving resize.
- Explicit DWM registration and update diagnostics.
- Clean close and shutdown.

It does not support:

- Settings persistence or migration.
- Automatic restart restoration.
- Multiple crops for one character or persisted crop management; simultaneous
  ephemeral crops exist only in the staged load-test path.
- Alerts, labels, custom styles, opacity, or click-through.
- Import/export or profiles.
- Frozen frames.

## Production persistence

### Version 1 shape

The initial persisted shape stores zero or one crop per character while making
its future migration explicit:

```json
{
  "preview": {
    "crops": {
      "Character Name": {
        "version": 1,
        "enabled": true,
        "source": {
          "x": 0.62,
          "y": 0.05,
          "w": 0.34,
          "h": 0.55,
          "original_client_w": 2560,
          "original_client_h": 1440,
          "original_px": [1587, 72, 870, 792]
        },
        "window": {
          "x": 1200,
          "y": 100,
          "w": 420,
          "h": 382
        }
      }
    }
  }
}
```

The field names are illustrative until the implementation plan checks all
settings conventions. The semantics are fixed:

- `source.x/y/w/h` are fractions of the source client area and authoritative.
- Fractions are finite and clamped to `[0, 1]`; width and height must remain
  positive and the rectangle may not extend beyond the unit square after
  validation.
- Original dimensions and pixel rectangle are diagnostic metadata, not a
  second authority.
- Destination geometry remains physical virtual-desktop pixels, matching
  primary preview persistence.
- An absent crop means never configured.
- `enabled: false` retains the definition without creating a live window.
- The live-crop cap is a product constant derived from recorded prototype
  results, not a user-tunable setting. Production must not ship until that
  constant has a measured value.
- Invalid entries are dropped or disabled according to the same forgiving
  posture as other settings: one bad crop must not prevent app startup.

### Future multiple-crop migration

The later schema replaces each character's single object with a list of named
objects carrying stable crop IDs. Migration wraps the existing object as the
first item and assigns a deterministic or newly generated ID once. Normalized
source and destination semantics do not change.

Do not ship a list in version 1 merely to claim future-proofing. The pure
validator must, however, keep the single-object ownership localized so the
future migration does not spread across the host, API, and page.

## Lifecycle

A crop definition belongs to a named character. A live crop belongs to the
current `(character, HWND, PID)` client instance.

Expected transitions:

| Previous state | Event | Result |
| --- | --- | --- |
| No definition | User confirms picker | Create live crop, then persist enabled definition |
| Enabled, available | Character logs out/title becomes anonymous | Close live crop; retain definition |
| Enabled, unavailable | Character returns on any HWND | Validate source; recreate automatically |
| Enabled, available | Client exits | Close live crop; retain definition |
| Enabled, available | User reselects and cancels | Keep old crop and definition unchanged |
| Enabled, available | User confirms valid reselection | Validate hidden candidate, persist replacement, then swap live crop |
| Enabled, available | Reselection candidate or persistence fails | Destroy candidate; keep old crop and definition unchanged |
| Enabled, available | User disables | Cancel pending geometry, persist disabled state, then reconcile closed |
| Disabled | User enables while available and below cap | Create live crop, then persist enabled state |
| Disabled | User enables while unavailable and below cap | Persist enabled; create when character returns |
| Disabled | User enables at live-crop cap | Reject; retain disabled state |
| Any saved state | User removes | Tombstone/cancel pending geometry, persist removal, then reconcile closed |
| Preview master on | User turns master off | Stop host and close all live crops; retain definitions and per-crop enabled states |
| Preview master off | User turns master on | Start host and reconcile enabled crops up to the measured cap |
| Picker open | Client disappears or identity changes | Cancel picker with status; persist nothing |
| Live crop | App shuts down | Cancel or flush current geometry, then destroy DWM relationship and HWND before host teardown |

A definition never follows the process into character select. An anonymous
client has no stable character ownership and cannot borrow the prior
character's crop.

## Interaction and visibility

- A click uses the same click-versus-drag threshold and asynchronous activation
  coordinator as a primary preview.
- Activation targets the crop's current client binding, not a stale HWND saved
  when the crop was selected.
- Moving and resizing affect only the crop HWND.
- Crop resizing preserves source aspect by default. It does not modify the
  source rectangle.
- The existing preview lock policy also locks crop destination geometry for
  that character in version 1. A future crop-specific lock is unnecessary
  until multiple crops make the distinction useful.
- Hide-on-lost-focus applies to crops through the same resolved foreground
  decision as primary previews.
- A future global hide-all applies to both primary previews and crops.
- The crop does not disappear merely because its primary preview is excluded;
  crop enablement is explicit. The production UI must make that independence
  understandable. If user testing finds it confusing, coupling the states is
  a product decision, not an implementation shortcut.
- The preview master does suppress every crop because it owns the host
  lifecycle. Suppression does not rewrite per-crop enabled state.
- Closing the crop through its own close affordance requests the same
  transactional disable operation as Settings. On persistence success,
  reconciliation closes it and retains the definition. On persistence failure,
  it remains visible and reports the failure. Removing it is a separate
  Settings action.

## Failure behavior

### Selection and client changes

- Empty or too-small selection: reject and keep the picker open with an inline
  explanation.
- Partially out-of-bounds selection: clamp to the current source client area;
  reject if the remaining region is below the minimum.
- Client resized while picker is open: recompute mapping against current client
  dimensions before confirm or require reselection if the captured mapping is
  no longer trustworthy.
- Client disappears, logs out, or changes identity: cancel without persistence.

### DWM creation and updates

- Registration failure: destroy the incomplete crop and persist nothing.
- Initial property update failure: unregister, destroy, and persist nothing.
- Later update failure: log the operation, HRESULT, character, current HWND,
  source rectangle, and destination rectangle.
- Attempt at most one unregister/register recovery for a failure episode.
- Recovery success resumes normal operation and clears the episode.
- Recovery failure closes the live crop but retains its enabled definition and
  reports degraded status. Reconciliation must not retry every 700 ms; retry
  requires a meaningful lifecycle event or explicit user action.

### Persistence

- For first creation or enabling while available, create the live crop before
  persistence so DWM failure cannot leave a saved feature that never worked.
- If that settings write then fails, close the new crop and return an error.
- Disable and removal go in the other safe order: persist the new source of
  truth first, then let host reconciliation close the live crop. A failed write
  therefore leaves the still-enabled crop visible rather than making runtime
  disagree with disk.
- Crop geometry persistence gets its own lock-serialized pending-delta state,
  following `preview/store.py` rather than sharing that store's primary-layout
  dictionary. Every scheduled write captures the crop's current in-memory
  generation and may apply only if the definition still exists at that
  generation.
- Disable and removal acquire the same lock, cancel the pending timer, discard
  that crop's pending geometry, and record a tombstone/new generation before
  updating settings. A callback that already woke must recheck the generation
  under the lock and no-op. This prevents a move immediately followed by
  removal from recreating the definition.
- Reselection invalidates pending geometry for the old generation only after
  the replacement settings write succeeds; the candidate inherits the latest
  resolved destination geometry used for that write.
- A failed geometry save leaves the last persisted geometry intact and reports
  the failure without killing the host.
- Shutdown marks the crop store closing under the same lock, then flushes only
  current non-tombstoned deltas. No late callback may recreate, re-enable, or
  retry a crop after teardown begins.

### Geometry and displays

- Normalize source geometry only against client-area dimensions.
- Clamp destination windows to actual attached monitor rectangles, not merely
  the virtual desktop bounding rectangle.
- Rescue a wholly off-screen crop but preserve deliberately partial off-screen
  placement, matching primary preview behavior.
- A source rectangle that becomes invalid under a changed client resolution is
  disabled live and requires reselection. Do not guess a semantically similar
  game UI region.

## DWM observability and recovery foundation

Before the crop prototype, make DWM results observable without changing normal
behavior.

- Registration and update wrappers expose HRESULTs.
- Primary preview callers log non-zero failures with source and destination
  identity.
- Normal successful updates remain silent.
- Do not add unconditional periodic re-registration.
- Add bounded recovery to primary previews only after a reproducible stale
  registration demonstrates that recovery is safe and useful.

This foundation is a prerequisite because crops add a second relationship and
would otherwise multiply silent failure modes.

## Prototype verification gates

Production persistence work must not begin until the prototype records a pass
or an explicitly reviewed exception for every applicable gate.

### Functional gates

- The picker maps selection to the expected source region at 100%, 125%, 150%,
  and 200% display scaling.
- Mapping remains correct when the picker is on a monitor with negative virtual
  coordinates.
- Picker resize before and during selection has defined, correct behavior.
- Crop output scales to destination size without changing the source region.
- No crop action changes the real EVE client's position, size, resolution, or
  maximized state.
- Click activation takes the existing non-blocking direct-first/fallback path.
- Dragging does not activate after crossing the click threshold.
- Closing the source client destroys the live crop and DWM relationship.
- Logout to character select never leaves the crop bound to an anonymous
  client.
- A returning named character can be rebound on a new HWND.
- Reselection leaves the old crop visible until candidate setup and persistence
  succeed, preserves destination geometry, and rolls back without a live or
  persisted change on either failure.
- Picker cancel and client-loss cancellation leave no live residue.
- Crop shutdown leaves no orphan HWND or callback.
- Lock and hide-on-lost-focus match their primary-preview truth tables.
- A wholly off-screen crop is rescued.

### DWM and compositor gates

Exercise:

- Source EVE client foreground and background.
- Source client minimized and restored.
- Crop fully visible, partially occluded, and fully occluded.
- Primary preview and crop visible simultaneously.
- Alert pulses on primary previews while the crop is moved and resized.
- DWM composition temporarily disabled/restarted where a safe test environment
  permits it.

Record whether minimized clients produce live, frozen, black, or stale crop
content. The first crop release need not solve minimized content, but its
behavior must be stated in UI/help and must not trigger an unbounded recovery
loop.

### Performance gates

Measure a baseline with primary previews only. Then measure simultaneous crop
counts of 1, 2, 4, and 8 alongside 2, 5, 10, and 20 running clients where the
client count permits. Stop increasing crops after the first failed stage, but
record the failure rather than omitting it. Exercise both crops from distinct
clients and, where useful to isolate compositor cost, repeated source
relationships against one client. Record:

- Hardware, Windows build, monitor topology, scaling, and client resolutions.
- Wingman CPU and working set.
- GPU utilization and relevant per-engine observations.
- DWM utilization if available through the chosen measurement tool.
- Preview-host responsiveness and hotkey switching latency.
- Largest observed gap while dragging a primary preview and the crop.
- Behavior while alerts pulse.
- Idle behavior when crop and source are fully occluded.

The implementation plan must choose concrete acceptance thresholds before the
probe is run. Thresholds are not invented in this design because they need a
measured current baseline and representative hardware. At minimum, one crop
must not produce a user-visible regression in switching or primary-preview
dragging. The first production global cap is the greatest staged simultaneous
crop count that passes every applicable gate; it may be lower than the number
of configured characters and may not exceed eight without a new measured
probe.

A failed gate produces one of three explicit outcomes:

1. Fix the prototype and rerun.
2. Narrow the production design with an evidence-backed limitation.
3. Stop the crop initiative and retain only the findings.

## Automated verification for production

Linux CI can and must cover all pure decisions even though it cannot render a
DWM pixel.

### Pure crop model

- Pixel rectangle validation.
- Normalized rectangle validation, including NaN and infinity rejection.
- Exact rounding at source edges.
- Pixel-to-normalized-to-pixel tolerances.
- Clamp and minimum-size behavior.
- Source aspect calculation.
- Version 1 serialization and forgiving invalid-entry handling.
- Future single-object-to-list migration fixture.
- Defaults are fixed points of their validator.

### Host lifecycle

Using injected clients, windows, and settings collaborators:

- Named availability creates enabled crops.
- Anonymous title transition closes without deleting.
- Return on a new HWND rebinds.
- Disabled definitions do not create.
- One picker supersession/cancellation policy.
- Client loss during picker confirmation.
- Create-before-persist ordering.
- Persistence failure closes the just-created crop.
- Reselection candidate-and-swap ordering, destination preservation, and
  rollback on candidate or persistence failure.
- Crop-geometry generation checks, tombstones, disable/removal cancellation,
  and shutdown flush ordering.
- Preview master off/on closes and later recreates individually enabled crops
  without rewriting their definitions.
- Cap enforcement, deterministic suppression of excess hand-edited entries,
  and rejection of an enable request at the cap.
- Teardown destroys crop relationships before the message-only host.
- DWM recovery is bounded and does not retry on every sweep.

### Geometry and interaction

- Picker destination-to-source coordinate conversion.
- Negative destination coordinates.
- Aspect-preserving crop resize.
- Click-versus-drag activation threshold.
- Monitor rescue behavior.
- Shared lock and visibility policy.

### Contracts

- API methods and page handlers agree.
- Every public non-method `Api` attribute remains underscore-prefixed.
- New web controls follow `DESIGN.md` conventions.
- Settings fields commit through per-field endpoints and never on blur.
- Crop-definition keys participate in character-row composition and protect
  their owners from seen-roster pruning.
- New package/module files are present in frozen-build packaging where
  applicable.
- No new client-targeted move, resize, or maximize API enters the preview
  Win32 surface.

## Manual smoke coverage

`docs/smoke-checklist.md` gains a cropped-preview section before production can
ship. It covers the functional, mixed-DPI, DWM, z-order, source-lifecycle, and
performance gates above.

The checklist must distinguish:

- Prototype-only checks, which prove feasibility.
- Production checks, which include restart restoration and Settings UI.
- Hardware/topology-specific checks, which record the machine used.

CI success is never described as proof that a crop rendered correctly.

## Master roadmap

Each phase below gets its own reviewed implementation plan. Phase ordering
expresses dependencies and current priority, not permission to implement every
phase without another review.

### Phase 0 — Crop feasibility and DWM observability

1. Surface DWM registration/update failures without changing successful paths.
2. Build the ephemeral picker and crop window prototype, including the staged
   1/2/4/8 simultaneous-crop load path.
3. Run Windows, real-EVE, mixed-DPI, lifecycle, and performance gates, then set
   the first production live-crop cap from the greatest passing stage.
4. Record measurements and a go/no-go decision.

### Phase 1 — Production cropped previews

1. Add the pure normalized crop model and versioned settings validation.
2. Build the production picker.
3. Build the independent crop window controller.
4. Add host reconciliation, character rebinding, measured cap enforcement,
   candidate-and-swap reselection, bounded recovery, and teardown.
5. Add transactional settings, generation-guarded crop geometry persistence,
   tombstoned removal, and semantic API methods.
6. Add the compact Previews-settings controls, crop-owner row retention, and
   preview-master suppression behavior.
7. Add automated tests, packaging checks, help text, and mandatory smoke
   coverage.

### Phase 2 — Alert correctness and localization

Improve the existing three alerts without broadening their product role.

- Fix the disruption-bubble branch currently documented as unreachable in
  `wingman/alerts/patterns.py`.
- Independently derive and corpus-test localized warp disruption and decloak
  phrases.
- Support validated localized log headers, including punctuation variants.
- Preserve Wingman's target-direction logic so fleet broadcasts do not flash
  unrelated previews.
- Preserve conservative NPC filtering and the rule that false alerts cost more
  than missed alerts.

Do not copy upstream's pattern JSON or expand into fleet invite, conversation,
mining, system-change, or stat alerts as part of this phase.

### Phase 3 — Discovery responsiveness

Adopt event-driven wakeups without making hooks the source of truth.

- Listen for object create, destroy, and name-change events.
- Record callbacks and post an immediate sweep; never touch preview HWNDs from
  the callback.
- Keep a periodic safety sweep.
- Measure whether the safety interval can be lengthened without harming
  recovery.
- Evaluate one-preview-per-PID filtering against real EVE windows before
  enabling it. A PID guard must not hide a legitimate client.
- Add discovery latency and idle-cost diagnostics.

### Phase 4 — Character-select support

- Give anonymous EVE clients a clear "Character select" treatment.
- Keep their identity ephemeral and HWND-scoped.
- Add an optional dedicated character-select cycle action.
- Reuse the existing activation path.
- Do not persist anonymous identity, forward held keys, or synthesize input.

### Phase 5 — Portable layouts and named preview profiles

- Define named preview profiles as complete preview configuration snapshots.
- Define monitor-relative, portable layout presets at import/export boundaries.
- Keep physical absolute pixels as the runtime geometry authority.
- Match characters by exact stable name first, with an explicit user-reviewed
  remapping path rather than silent guesses.
- Permit offline-character pre-positioning.
- Version optional visibility state so a position-only preset never
  unexpectedly hides previews.
- Implement EVE-O/EVE-X import through independently written, fixture-tested
  parsers.
- Do not identify monitors only by enumeration index; choose and document a
  more stable mapping/fallback policy.

### Phase 6 — Label customization

Extend Wingman's owned click-through label overlay rather than adopting WPF
techniques.

- Global text colour, size, and placement first.
- Optional per-character aliases second.
- Keep geometry stable where possible.
- Invalidate any baked visual caches when style changes require it.
- Maintain contrast, focus, and small-thumbnail legibility.
- Avoid dynamic label height until its effect on crop/thumbnail aspect and
  alerts is explicitly designed.

### Phase 7 — Temporary visibility modes

- Hide-active-preview mode.
- Hide/show-all action with visible state and guaranteed tray/hotkey recovery.
- Click-through mode with the same recovery guarantee.
- Apply global visibility consistently to primary previews and crops.
- Make temporary state converge correctly when clients appear while hidden.
- Avoid consuming default global keybindings; all new bindings are opt-in.

### Later experiment — multiple named crops

After one production crop is stable and measured:

- Migrate to stable crop IDs and per-character lists.
- Add names only when more than one crop exists.
- Re-measure and revise the existing global cap before allowing more live
  relationships per character.
- Decide whether lock, visibility, opacity, and hotkeys become per crop.
- Keep alerts on primary previews unless a separate product decision changes
  that attention model.

### Later experiment — secondary full-client PiP

A second full-client preview has weaker differentiation than a crop while
adding similar HWND and DWM costs. Consider it only after crop lifecycle and
resource limits are proven. Reuse crop registry primitives where they fit;
do not force crops and full previews into one controller if their visual state
differs.

### Later experiment — frozen and static frames

Investigate only after measurements or user reports establish a real problem
with blank minimized previews or compositor cost.

- Prefer event-triggered capture around minimization over default periodic
  `PrintWindow` work.
- Cap capture resolution and memory explicitly.
- Treat black or stale Direct3D captures as normal failure modes.
- Do not introduce periodic full-resolution capture by default.
- Record allocation, GC, CPU, and latency effects on multi-client setups.

## Permanent exclusions

The roadmap does not include:

- Saving, restoring, centering, arranging, resizing, or otherwise writing real
  EVE client geometry.
- Maximizing a client during activation.
- Synthetic held-key forwarding or activation-key injection.
- Input broadcasting or background-client input.
- `SetLayeredWindowAttributes` opacity on Wingman's layered preview windows;
  the measured interaction with `UpdateLayeredWindow` remains unsafe.
- A broad alert hub, stat overlays, or every log event upstream can parse.
- A large NPC-name database that weakens Wingman's conservative false-negative
  posture.
- Direct source or localization-data copying from EVE-MultiPreview under its
  current incomplete licensing state.

## Dependencies and ordering notes

- DWM error observability precedes crops because otherwise a second thumbnail
  relationship doubles a silent failure mode.
- The crop prototype precedes persistence because mixed-DPI mapping and DWM
  cost are external-system claims.
- Production crops precede multiple crops and PiP because they establish the
  necessary registry and resource evidence.
- Discovery wakeups can be implemented independently after crop work; crops
  consume the reconciled registry rather than depending directly on hook
  events.
- Profiles must define whether crop definitions are profile-scoped when that
  phase is designed. Version 1 crops live under the current implicit preview
  profile and must be migratable without losing definitions.
- Label customization and alert expansion are deliberately separate from crop
  rendering. A crop's first value is the selected game region, not duplicated
  chrome.

## Open implementation-plan decisions

These are intentionally deferred until the relevant phase because they depend
on repository inspection or probe results, not product preference:

- Exact Win32 crop and picker class styles.
- Exact host mailbox message identifiers and API method names.
- Prototype retention strategy after the probe.
- Concrete performance thresholds after a current baseline is measured.
- Minimum selectable source size.
- Picker default size and monitor placement.
- Whether a client resize during selection remaps or forces reselection.
- Production crop close affordance and its accessible representation.
- Stable monitor identity for portable layout presets.
- Named-profile migration shape and whether crops are included by default.

None of these may be resolved by copying upstream behavior without validating
it against Wingman's architecture and product constraints.

## Definition of success

This design succeeds when:

- A reviewer can distinguish existing capability, planned work, experiments,
  and exclusions without reading the external repository.
- The crop prototype can be planned as a disposable feasibility slice with
  objective gates.
- A failed prototype leaves no production schema or partial user-facing
  feature behind.
- A successful prototype leads to a production crop whose stable owner is a
  character and whose live owner is a replaceable HWND.
- Production concurrency is bounded by the greatest staged simultaneous-crop
  count that passed the prototype gates.
- Reselection either swaps a fully validated and persisted candidate into place
  or leaves the old live and persisted crop unchanged.
- Configured crop owners remain visible and removable regardless of roster age
  or preview-master state.
- No roadmap item weakens the prohibition on changing real EVE client
  geometry.
- Each subsequent phase can receive its own bounded design or implementation
  plan instead of turning this roadmap into a big-bang branch.
