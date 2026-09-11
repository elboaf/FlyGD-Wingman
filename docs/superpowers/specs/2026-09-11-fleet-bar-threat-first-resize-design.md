# Fleet Bar Threat-First Resize Design

## Summary

Fleet Bar is a passive, always-on-top combat instrument for experienced EVE multiboxers. It must let the pilot identify which character is threatened, recognize active EWAR, and understand relative incoming and outgoing activity without leaving EVE.

The redesign preserves the existing data honesty and low visual noise while fixing identity truncation, ambiguous rail semantics, naming drift, and fixed-width limitations.

## Primary user action

At a glance, identify:

1. Which character is under threat.
2. Whether that threat is SCRAM, POINT, or NEUT.
3. How that character's incoming activity ranks against the other visible characters.

No interaction is required to obtain this information.

## Design direction

The surface uses a restrained color strategy. Tinted dark neutrals remain dominant. Amber is reserved for active incoming threat, and EWAR receives stronger emphasis than ordinary incoming DPS.

Physical scene: a multiboxing pilot glances at Fleet Bar on a secondary monitor during a fight in a dim room, while most attention remains on EVE and a mistake could cost a ship.

Anchor references:

- EVE Online Watch List for stable pilot positions and compact combat awareness.
- Windows Task Manager for restrained relative activity visualization supported by exact values.
- Professional audio mixer meters for per-channel activity without level-based reordering.

The result is a quiet instrument, not a dashboard or gamer HUD.

## Scope

- Fidelity: production-ready.
- Breadth: Fleet Bar, native window behavior, related Settings and status-strip terminology, persistence, tests, and smoke documentation.
- Interactivity: shipped-quality resizing, dragging, scrolling, hiding, and width reset.
- Platform: Windows WebView2 at 100%, 125%, 150%, and 200% display scaling.

## Layout

### Width

- Default preferred width: 500 logical pixels, subject to rendered measurement.
- Minimum preferred width: 420 logical pixels.
- Maximum preferred width: 720 logical pixels.
- Runtime width may be temporarily clamped to the current monitor without overwriting the saved preference.
- Only horizontal user resizing is allowed.
- Height remains content-driven and capped by available monitor height.

The exact default and maximum may move slightly after rendered measurement. The 420px minimum is fixed unless testing proves the existing exact-value contract cannot be preserved.

### Columns

Use an adaptive three-column structure:

1. Character: protected flexible track and visually primary.
2. DPS · 10s: compact OUT and IN values with short relative rails.
3. EWAR: content-aware track that expands for active labels rather than permanently reserving 148px.

At 420px:

- Exact DPS values remain visible.
- Rails shrink before identity does.
- EWAR labels remain readable.
- Character names receive materially more width than today.
- Exceptionally long names may ellipsize, with the full name exposed accessibly.

At wider widths, character identity receives the majority of additional space, rails grow to improve relative comparison, and inactive EWAR does not consume blank width merely because space is available.

### Threat hierarchy

An active threat row receives a subtle full-row amber surface tint. No side stripe is used.

Within a threatened row:

1. Character name remains the strongest text.
2. EWAR receives strong amber emphasis.
3. Incoming DPS receives restrained amber emphasis.
4. Outgoing DPS remains neutral.
5. Remote and stale qualifiers remain secondary but readable.

Rows never reorder in response to threat or DPS.

### Ordering

Preserve the existing local-first ordering contract. Metric changes never reorder unchanged identities. Remote arrivals, removals, and verified-local takeover may change membership, but existing rows do not move unnecessarily.

## States

### Healthy, no activity

Neutral rows show exact zero values, empty rails, subdued EWAR dashes, and LOCAL LIVE. The surface feels quiet and ready.

### Outgoing activity

Exact outgoing DPS remains visible. A neutral rail shows relative rank among current, non-stale outgoing values. No amber treatment appears.

### Incoming damage

Exact incoming DPS remains visible. The incoming rail shows relative rank among current, non-stale incoming values. The incoming value and rail receive restrained amber, and the row receives a subtle threat tint.

### Active EWAR

SCRAM, POINT, and NEUT retain their fixed semantic order. EWAR is the strongest amber element, while character identity remains visually dominant. Combined EWAR remains readable at minimum width. The threat tint persists while EWAR is active.

### Incoming damage plus EWAR

EWAR wins the emphasis hierarchy. Incoming DPS remains visible but does not compete with the EWAR label.

### Remote live and stale

A live remote row shows REMOTE. Incoming DPS remains unavailable rather than zero. Remote outgoing activity participates in ranking while current.

A stale remote row shows REMOTE · STALE, loses active and threat emphasis, and does not participate in relative rail maxima.

### Missing log

Directional damage is replaced by the existing specific missing-log state. Empty rails are not drawn because they would imply measured zero. A concise recovery instruction appears when Wingman configuration can resolve the condition.

### Stream waiting, stale, or error

The health label remains visible. A concise diagnostic note identifies the condition and recovery location. No state fabricates activity.

### Empty and long rosters

The empty state distinguishes waiting for EVE clients from all running characters being hidden.

For long rosters, the header remains fixed, the column header stays sticky, and the roster scrolls within the monitor-height cap.

### Long names and combined EWAR

Identity ellipsizes only after rails reach their compact floor. The full name remains available to assistive technology and pointer hover. EWAR never overlaps or silently loses an active effect.

## Interaction model

### Dragging

The header contains sibling regions: a dedicated drag surface and a status/action region. Buttons are never descendants of `.pywebview-drag-region`, so interacting with them cannot initiate a native drag.

### Resizing

- Left and right native edges expose horizontal resize hit targets.
- Top, bottom, and corners do not enable vertical resizing.
- Pointer feedback uses the standard horizontal resize cursor.
- Width updates continuously during drag.
- Width persistence is debounced until resizing settles.
- Automatic telemetry rendering never writes or snaps width.
- Height fitting resumes after horizontal resizing settles.
- Moving and resizing remain clamped to the current monitor.

The implementation reuses the proven native hit-testing mechanics in `wingman/ui/chrome.py` through a Fleet-specific horizontal configuration. It does not apply the main window's all-edge behavior unchanged.

### Header actions

On header hover or explicit focus, reveal Reset width and Hide. Their space is reserved so labels and window height do not jump. Actions may replace the health label in the same reserved end region while being used.

Clicking a header control may explicitly activate the window. Merely showing Fleet Bar never steals focus from EVE.

### Hide

Hide persistently turns Fleet Bar Off. Settings and status-strip controls update, fleet sharing remains unaffected, and the native window stays eligible for the existing fast hidden-window lifecycle.

Hide uses a dedicated page-token-bound endpoint rather than an endpoint whose first parameter has a different meaning.

### Reset width

Reset width applies and persists the measured default width, re-clamps position if the wider bar would cross the monitor edge, and leaves height and row state unchanged. A persistence failure does not pretend the reset was saved.

### Keyboard and accessibility

The main Wingman window retains equivalent controls when the no-activate overlay is not keyboard-reachable.

After a pointer click explicitly activates the bar, Tab can reach Reset width and Hide, focus appearance is visible, Escape returns focus without hiding the bar, and tab order follows visual order.

## Content

Use Fleet Bar consistently in Settings, the status-strip tooltip and accessible name, the native window title, the bar header, and recovery messages.

Replace DAMAGE with DPS · 10s and retain OUT and IN beneath it.

Accessible damage descriptions remain explicit, such as “Outgoing 420 DPS,” “Incoming 86 DPS,” and “Incoming unavailable.”

Header health states remain concise:

- LOCAL LIVE
- LOCAL WAITING
- LOCAL STALE
- NO LOG FOLDER
- ERROR

The local label describes the local telemetry source even when remote rows are present.

Controls use the accessible names Reset Fleet Bar width and Hide Fleet Bar.

Recovery copy is short and specific. Final wording must name only verified recovery paths.

## Architecture constraints

- Persist preferred width through the complete settings validation and normalization chain.
- Keep monitor-clamped applied width separate from preferred width.
- Separate user-owned width from page-owned automatic height fitting.
- Preserve page-token lifecycle admission for resize, reset, and hide callbacks.
- Exclude stale remote values from rail maxima.
- Do not attach ordinary Python pywebview resize-event handlers.
- Do not move or resize any EVE client window.
- Reserve header action geometry rather than adding it only on hover.
- Preserve display-only telemetry behavior and sharing independence.

## Verification

Automated coverage must include:

- Settings defaults, validation, normalization, and migration from documents without width.
- Page-token admission for resize, reset, and hide.
- Separation of preferred width from runtime monitor clamp.
- Horizontal-only native hit testing.
- Height fitting that never resets user width.
- Stable row order under metric updates.
- Relative rail scaling with stale rows excluded.
- Minimum, default, and maximum layout widths.
- Long names, combined EWAR, large exact values, missing logs, empty rosters, and long rosters.
- Updated bridge and top-level JavaScript smoke contracts.

Installed Windows/WebView2 smoke must verify:

- Left and right resize hit targets.
- No vertical resize.
- DPI behavior at 100%, 125%, 150%, and 200%.
- Persistence after resizing.
- Preferred-width retention across temporary monitor clamps.
- Height fitting during and after resizing.
- No focus theft when the bar appears.
- Intentional activation when a header control is clicked.
- Dragging, scrolling, Hide, Reset width, and monitor-edge recovery.

## Resolved decisions

- Rows stay stable and preserve existing local-first ordering.
- The minimum width is 420px and exact DPS values remain visible.
- Width is freely resizable within bounded limits and persists.
- Hide persistently turns Fleet Bar Off.
- Header controls may activate the bar only through explicit interaction.
- Relative rails communicate rank and activity, not a shared absolute scale.
