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

The width values in this document always mean **WebView content width in logical CSS pixels**, which is also the `.fleet-shell` border-box width. They do not mean native outer-form width.

- Default preferred content width: 500px, subject to rendered measurement.
- Minimum preferred content width: 420px.
- Maximum preferred content width: 720px.
- Native outer width equals content width plus the measured left and right resize insets. DPI conversion follows the existing logical-to-native path and tolerates the established one-pixel rounding difference.
- Runtime content width may be temporarily clamped to the current monitor without overwriting the saved preferred content width.
- Only horizontal user resizing is allowed.
- Height remains content-driven and capped by available monitor height.

Python validates and persists the preferred content width. On creation, it derives the native outer width by adding both resize insets. The page reports settled content width, never outer width. A left-edge resize also reports and persists the changed window `x`; a right-edge resize preserves `x`. Temporary monitor clamping changes only applied width and position, not the preferred width.

If native resize chrome cannot attach, Fleet Bar remains usable at the clamped preferred width with resizing unavailable. The failure is logged, the page omits the resize affordance, and telemetry, dragging, Hide, and Reset width continue to work. Reset still applies the default through programmatic fitting.

The exact default and maximum may move slightly after rendered measurement. The 420px minimum content width is fixed unless testing proves the existing exact-value contract cannot be preserved.

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

The sharing protocol cannot distinguish remote SCRAM from POINT. A remote tackle observation therefore renders `SCRAM/POINT`, never a fabricated local-style distinction. Its accessible label says “Remote tackle: scram or point.” Remote NEUT remains distinct when supplied by the protocol.

A stale remote row shows REMOTE · STALE, loses active and threat emphasis, and does not participate in relative rail maxima. Its exact last value may remain in subdued text under the existing stale-data contract, but every stale rail uses a zero fill ratio. A stale value can neither set the live scale nor appear tied with a current leader.

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
- A debounced page `resize` listener owns resize settlement. It sends the token-bound content width and current `screenX` only after browser resize events settle.
- Python clamps and persists the preferred content width. It persists `x` from a left-edge resize and leaves `x` unchanged after a right-edge resize.
- Automatic telemetry rendering never writes or snaps width.
- Height fitting uses a height-only token-bound endpoint that reads and preserves the current native outer width. Delayed retries may change height only.
- Height fitting pauses while resize events are arriving and resumes after settlement.
- Moving and resizing remain clamped to the current monitor.

The implementation reuses the proven native hit-testing mechanics in `wingman/ui/chrome.py` through a Fleet-specific horizontal configuration. It does not apply the main window's all-edge behavior unchanged. The inset is accounted for exactly once when converting between content and outer widths, preventing a measurement feedback loop.

### Header actions

On header hover or explicit focus, reveal Reset width and Hide. Their space is reserved so labels and window height do not jump. Actions may replace the health label in the same reserved end region while being used.

Merely showing Fleet Bar retains `WS_EX_NOACTIVATE` and uses the existing no-activate reveal path. A pointer click on a header action starts an explicit activation session through a dedicated token-bound native endpoint: it records the current foreground HWND, temporarily removes `WS_EX_NOACTIVATE`, activates Fleet Bar, and returns focus to the clicked action. Failure restores no-activate styling immediately and leaves the equivalent main-window controls available.

The activation session ends on Escape, Hide, or loss of Fleet Bar focus. Ending it restores `WS_EX_NOACTIVATE` before attempting to return focus to the recorded HWND. Focus returns only when that HWND still exists and is still an eligible EVE or Wingman window; otherwise no foreground change is attempted. Reset width alone does not end the session, so Tab can still move between the two actions. Every passive reveal reasserts no-activate styling defensively.

### Hide

Hide persistently turns Fleet Bar Off. Settings and status-strip controls update, fleet sharing remains unaffected, and the native window stays eligible for the existing fast hidden-window lifecycle.

Hide uses a dedicated page-token-bound endpoint rather than an endpoint whose first parameter has a different meaning. It returns the standard `{applied, persisted, error}` result and publishes one authoritative state to both main-window controls.

The endpoint first persists Off. If persistence fails, the bar remains visible and enabled. If persistence succeeds but native hiding fails, runtime state rolls back to enabled and attempts to persist that rollback. A successful rollback returns a refusal. If rollback persistence also fails, the bar remains visibly enabled for the session and returns `applied: true, persisted: false` with a restart warning. Main-window controls reflect the visible runtime state in every branch.

### Reset width

Reset width applies the measured default content width, re-clamps position if the wider bar would cross the monitor edge, and leaves height and row state unchanged. It returns `{applied, persisted, error}`. If persistence fails after the native resize succeeds, the session keeps the applied default and reports that it will not survive restart; it never claims the reset was saved.

### Keyboard and accessibility

The main Wingman window retains equivalent controls when the no-activate overlay is not keyboard-reachable.

During an explicit activation session, Tab reaches Reset width and Hide, focus appearance is visible, and tab order follows visual order. Escape ends the activation session without hiding the bar and follows the guarded focus-return contract above.

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

- Persist preferred **content** width through the complete settings validation and normalization chain.
- Convert between content and outer width through one named inset boundary.
- Keep monitor-clamped applied width and position separate from preferred width.
- Separate user-owned width from page-owned automatic height fitting.
- Preserve page-token lifecycle admission for resize, activation, deactivation, reset, and hide callbacks.
- Exclude stale remote values from rail maxima and force their own rail ratios to zero.
- Preserve the remote protocol's combined SCRAM/POINT truth.
- Do not attach ordinary Python pywebview resize-event handlers.
- Do not move or resize any EVE client window.
- Reserve header action geometry rather than adding it only on hover.
- Preserve display-only telemetry behavior and sharing independence.

## Verification

### Node and Python behavior

Automated behavior coverage must include:

- Settings defaults, validation, normalization, and migration from documents without preferred content width.
- Page-token admission for resize, activation, deactivation, reset, and hide.
- Hide and Reset width results for success, persistence failure, native failure, and rollback-persistence failure.
- Separation of preferred content width from runtime monitor clamp.
- Content-to-outer inset conversion without feedback.
- Horizontal-only native hit testing and resize-chrome attachment failure.
- Height-only fitting that never resets user width.
- Stable row order under metric updates.
- Relative rail scaling with stale rows excluded and stale self-ratios fixed at zero.
- Truthful combined remote SCRAM/POINT wording and accessibility.
- Activation-session entry, exit, no-activate restoration, and guarded foreground return.
- Updated bridge and top-level JavaScript smoke contracts.

These tests establish state, token, bridge, and pure native-message behavior. They make no rendered layout, DPI, or real focus claim.

### Rendered browser measurements

A browser harness must separately measure minimum, default, and maximum content widths. It verifies column geometry, exact large values, long names, combined local and remote EWAR, threat tinting, reserved header-action geometry, sticky headers, scrolling, empty states, missing logs, and absence of horizontal overflow.

Browser evidence proves CSS layout only. It does not prove WinForms insets, native hit testing, DPI conversion, activation, foreground restoration, or WebView2 focus.

### Installed Windows/WebView2 acceptance

Installed smoke must verify:

- Content width versus outer width with both native resize insets.
- Left and right resize hit targets.
- No vertical resize.
- DPI behavior at 100%, 125%, 150%, and 200%.
- Persistence of content width and left-edge `x` after resizing.
- Preferred-width retention across temporary monitor clamps.
- Height-only fitting during and after resizing, with no width snapback.
- Fixed-width fallback when resize chrome cannot attach.
- No focus theft when the bar appears.
- Explicit activation, Escape, loss-of-focus cleanup, guarded foreground return, and no-activate restoration.
- Hide and Reset width success and visible failure feedback.
- Dragging, scrolling, and monitor-edge recovery.

## Resolved decisions

- Rows stay stable and preserve existing local-first ordering.
- The minimum width is 420px and exact DPS values remain visible.
- Width is freely resizable within bounded limits and persists.
- Hide persistently turns Fleet Bar Off.
- Header controls may activate the bar only through explicit interaction.
- Relative rails communicate rank and activity, not a shared absolute scale.
