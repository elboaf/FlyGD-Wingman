# Incoming DPS display

## Summary

FlyGD Wingman's local Fleet Bar will calculate incoming damage per second and show it beside outgoing damage in one compact, bidirectional Damage region:

```text
Character | OUT  │  IN | EWAR
```

Outgoing sits toward the character. Incoming sits toward EWAR so the two signals about what is happening to a pilot remain adjacent. Each side combines an exact whole-number value with a slim directional rail. The rails answer separate fleet-awareness questions rather than presenting a net exchange: outgoing highlights which visible pilot is applying the most damage, while incoming highlights which visible pilot is receiving the most.

This release is deliberately local-only. The existing authGD protocol remains version 1 and its strict `{character_id, dps, ewar}` schema does not change. Shared incoming DPS follows after the unmerged shared-fleet receive/display work lands and authGD can evolve that schema compatibly. This design does not claim to repair the pre-existing adapter mismatch between local `SCRAM`/`POINT` tags and protocol v1's combined `SCRAM/POINT` value; that defect is recorded under the sharing boundary and remains outside this change.

## Goals

- Show exact outgoing and incoming DPS for every visible local Fleet Bar row.
- Make the highest outgoing and highest incoming pilots apparent in peripheral vision.
- Keep one stable alphabetical row per running, logged-in client.
- Use one consistent OUT-left, IN-right arrangement suitable for future local and remote rows.
- Preserve the distinction between observed zero and unavailable log data.
- Preserve Alerts, EWAR, source-generation, replay-prevention, and outgoing-DPS behavior.
- Keep the Fleet Bar at its existing 420 CSS-pixel width.

## Non-goals

- Net DPS, damage balance, tank pressure, effective hit points, repair received, fleet totals, rankings, or history.
- Sorting or moving rows by either damage value.
- User-configurable colors, scaling modes, thresholds, or rolling windows.
- Widening the Fleet Bar or adding a fourth table column.
- Publishing incoming DPS to authGD in protocol version 1.
- Implementing shared-fleet reads, remote-row merging, authGD migrations, or authGD deployment in this repository.
- Changing which events refresh the 30-second observed-EWAR activity window.

## User experience

### Row structure

The Fleet Bar remains a three-region table:

1. **Character** — the stable, ellipsized character name.
2. **Damage** — one cell containing an outgoing value and rail on the left, a fixed center axis, and an incoming value and rail on the right.
3. **EWAR** — current `SCRAM`, `POINT`, and `NEUT` state.

The header changes from `CHARACTER | DPS | INCOMING` to `CHARACTER | DAMAGE | EWAR`. Inside the Damage header, visible `OUT` and `IN` sublabels align with their halves. The order never changes between quiet and active rows and must also be retained by a future shared-row implementation.

The exact values use the existing 12px tabular monospace treatment. The unit is established by the `DAMAGE` heading and Wingman's existing Fleet Bar context, so the narrow cell shows bare whole numbers rather than repeating `dps` twice per row.

The 420px grid allocates 160px to Damage and 148px to EWAR, leaving 92px for Character after the existing 20px horizontal row padding. A 160px Damage track accommodates two values through `10,000,000`, the protocol's existing maximum, plus the center axis and gaps at the existing monospace size. Values from `0` through `10,000,000` render in full. A defensive value above that supported visual bound renders as `>10m`, while its full exact value remains in the cell's accessible description and `title`; the page must not widen, overlap EWAR, or silently ellipsize a number. Geometry verification uses simultaneous `10,000,000` values, `SCRAM · POINT · NEUT`, and a long character name.

The center axis and directional fills make the relationship spatial:

```text
outgoing fill grows left from center  ◀━━ │ ━━▶  incoming fill grows right from center
```

Outgoing uses the quiet neutral text/rail vocabulary. Positive incoming values and fills use the same warm `--warn` family as active EWAR, grouping received damage with received effects without using the error or destructive-action colors. An incoming zero uses the neutral quiet treatment and an empty rail, so warm color always means active received damage. Labels, position, numbers, and direction carry meaning independently of color.

### Relative signal

Rail length is relative within each direction, not across the center axis.

For every rendered snapshot:

- `max_outgoing` is the highest numeric outgoing DPS among rows the page receives.
- `max_incoming` is the highest numeric incoming DPS among rows the page receives.
- A numeric value's fill ratio is `value / corresponding_max`.
- When the corresponding maximum is zero, every ratio on that side is zero.
- Unavailable values do not participate in a maximum and have no fill.
- A hidden character cannot affect normalization because Python filters hidden rows before constructing the page payload.

The two maxima are independent. Equal rail lengths on opposite sides do not claim equal DPS. Exact numbers carry magnitude; each rail only answers “who is highest in this direction among the pilots currently shown?”

Rows remain case-insensitively alphabetical. Hiding, restoring, joining, leaving, or changing a directional leader may rescale rails, but never reorders rows.

Rail fills update immediately with each one-second snapshot. The current renderer replaces rows rather than preserving keyed fill elements, and adding a second rendering path solely for animation would add lifecycle complexity without improving metric truth. No transition or decorative motion ships in this stage.

### Quiet, unavailable, and degraded states

- **Observed quiet:** show `0` for both directions and empty rails.
- **One direction quiet:** show that direction's `0` and empty rail while the other remains live.
- **No attributable live log:** show one `NO LOG` state spanning the Damage region; neither directional rail renders a value. EWAR remains an em dash. The row must not repeat `NO LOG` once per direction.
- **Global stream problem:** retain the existing roster, health label, and diagnostic note behavior. The last accepted snapshot remains subject to the existing stream-health semantics.
- **All characters hidden or no active clients:** preserve the existing empty-state behavior.

A zero is measured data. `NO LOG` is unavailable data. They must remain visually and programmatically distinct.

### Accessibility

The Damage region is one table cell with an accessible description containing both named values, for example `Outgoing 1306 DPS, incoming 842 DPS`. `NO LOG` is exposed as unavailable damage data. The visible OUT/IN labels, fixed geometry, and exact values ensure color is never the only cue.

The full bar remains a drag region and display-only. No new focus targets, row actions, tooltips, or pointer behavior are introduced.

## Metric semantics

Incoming DPS uses the same event-time calculation as outgoing DPS:

```text
sum(incoming damage with timestamp in (now - 10 seconds, now]) / 10
```

The denominator is always ten seconds and the result rounds half-up to a whole number. Incoming and outgoing damage keep separate bounded deques per character and prune independently on ingestion and every one-second snapshot. Both directions use the existing two-second future-timestamp clamp, reject timestamps further in the future, ignore values at or before the ten-second boundary, and clear on source retirement, source replacement, relog, or roster removal.

`incoming_damage` already carries a parsed amount through `ParsedFact` and `CombatFact`. Metric-grade parsing accepts either ungrouped ASCII digits (`1234`) or conventional comma grouping (`1,234`, `12,345`, `1,234,567`). Invalid grouping such as `1,,299`, `12,34`, a commas-only value, or an absent amount must never raise from `parse_line()`. It still emits the recognized `incoming_damage` fact and source for existing Alert policy, but sets `amount=None` so Fleet Metrics contributes no incoming damage. Fixtures and tests pin these outcomes rather than assuming alert-level event recognition proves numeric fidelity.

Incoming damage does **not** refresh the observed-EWAR activity deadline. Existing product behavior names outgoing damage and newly observed EWAR as the refresh signals; this change must not alter that policy accidentally through a shared ingestion helper.

The accepted-fact sequence floor remains common to all combat facts for a character. Interleaved incoming and outgoing facts must therefore retain the existing stale/duplicate rejection behavior. A rejected future fact must not consume its sequence, regardless of direction.

## Data model and flow

### Local telemetry model

`FleetRow.dps` remains the outgoing value for compatibility with the existing strict fleet-sharing projection and the many positional constructors that already consume it. Add `incoming_dps: int | None` as a trailing field:

```python
@dataclass(frozen=True)
class FleetRow:
    character: str
    dps: int | None
    ewar: tuple[str, ...] = ()
    log_status: str | None = None
    incoming_dps: int | None = None
```

For a bound local row, both `dps` and `incoming_dps` are numeric, including zero. For an unbound row, both are `None` and `log_status == "NO LOG"`.

The internal `_CharacterState` holds separate outgoing and incoming damage deques. Direction-aware helpers may share timestamp validation, pruning, and rounding, but EWAR-activity refresh remains explicitly outgoing-only.

### Page payload

The Python-to-page payload stops exposing the ambiguous local key `dps` and names both display fields explicitly:

```json
{
  "character": "Aiga Otsolen",
  "outgoing_dps": 1306,
  "incoming_dps": 842,
  "ewar": ["SCRAM"],
  "log_status": null
}
```

This payload is internal to the bundled auxiliary page, not the authGD wire contract. The page computes maxima and fill ratios after receiving the already-filtered visible rows. Python remains responsible for metric truth, stable row order, and visibility; JavaScript is responsible only for presentation normalization.

### Sharing boundary

Protocol version 1 remains byte-for-byte compatible:

- `PublishRow` remains `{character_id, dps, ewar}`.
- `project_snapshot()` continues using `FleetRow.dps` and current sparse inclusion rules.
- `FleetRelayClient.publish_snapshot()` sends no `incoming_dps` property.
- Existing validation bounds and privacy promises remain unchanged.

There is a pre-existing adapter mismatch at this boundary: local Fleet Metrics emits separate `SCRAM` and `POINT` tags, while protocol v1's projection allowlist accepts only the combined literal `SCRAM/POINT`. Existing projection tests manufacture that combined value rather than passing real metric output through the adapter. This design neither relies on that path being functional nor fixes it opportunistically. Existing protocol-shape tests remain unchanged; no new test freezes the defective adapter behavior. Correction belongs to separately scoped fleet-sharing work.

This stage does not claim that shared participants can see incoming DPS. The UI geometry and future-facing page field name establish a consistent presentation vocabulary, but remote transport requires a separate protocol design covering:

- authGD schema and database migration;
- version or capability negotiation;
- older publishers for which incoming DPS is unavailable, not zero;
- incoming-only sparse row inclusion;
- consent and privacy copy naming incoming combat telemetry;
- stale-row participation in visual normalization;
- compatibility with the remote presentation work currently isolated on `feature/shared-boss-roster`.

## Error handling and lifecycle

Incoming metric errors use direction-specific diagnostic text so a rejected timestamp identifies whether incoming or outgoing data failed. Tests pin that an accepted incoming, outgoing, or EWAR fact clears a prior directional diagnostic under the existing shared-diagnostic policy, while a rejected incoming fact does not advance the common fact-sequence floor.

No new thread or worker is introduced. Parsing remains in the gamelog stream, aggregation remains in the serialized `FleetMetrics` consumer, the coordinator continues publishing complete immutable snapshots once per second, the presentation worker remains the only owner of WebView I/O, and the page remains presentation-only.

Source and session lifecycle handling applies to both directional deques in the same critical paths. Any clear that currently prevents outgoing replay must clear incoming state too.

## Testing and verification

### Pure telemetry tests

Cover:

- incoming amount parsing from verified direct and NPC log fixtures, including comma separators;
- malformed or missing incoming amounts;
- half-up rounding and fixed ten-second denominator;
- exact window boundaries, decay, future clamp, and direction-specific future rejection;
- accepted incoming, outgoing, and EWAR facts clearing a prior directional diagnostic;
- rejected incoming facts leaving the common sequence floor unchanged;
- independent incoming and outgoing accumulation;
- observed zeros versus both values unavailable;
- source retirement, replacement, relog, and roster removal clearing both deques;
- interleaved fact sequencing and duplicate rejection;
- incoming damage not refreshing EWAR activity.

### Bridge and page tests

Cover:

- explicit `outgoing_dps` and `incoming_dps` payload fields;
- no change to `PublishRow` or protocol-v1 JSON;
- independent visible-row maxima;
- zero maxima without division by zero;
- unavailable rows excluded from maxima;
- exact accessible Damage-cell descriptions;
- `NO LOG` rendered once across Damage;
- OUT-left and IN-right DOM order;
- EWAR header copy;
- simultaneous `10,000,000` values, full EWAR text, defensive `>10m`, and long-name geometry;
- immediate rail updates with no transition.

Because existing Fleet Bar tests are mostly lexical and top-level JavaScript smoke does not execute handler bodies, add a focused Node DOM harness that renders representative payloads and asserts labels, text, ratios, classes, and unavailable states.

### Visual and native verification

At 420 CSS pixels, verify one through ten rows with:

- zero, low, and roster-leading values in each direction;
- long character names;
- simultaneous incoming DPS and multiple EWAR tags;
- `NO LOG`, hidden/restored characters, and a changing directional leader;
- 100%, 125%, 150%, and 200% Windows display scaling.

Browser geometry checks establish CSS fit only. The existing Windows/WebView2 smoke checklist remains the acceptance authority for native sizing, drag behavior, monitor clamping, first reveal, and ten-row fit.

## Documentation updates

Update `PRODUCT.md` so the local Fleet combat bar explicitly names recent outgoing and incoming DPS. Do not change its fleet-sharing privacy statement, which continues to describe protocol v1. Update the Fleet Bar section of `docs/smoke-checklist.md` with incoming metric semantics and split-rail visual checks.

The completed implementation may move this design to `docs/history/` only according to the repository's established completed-design workflow; historical documents are not rewritten afterward.

## Acceptance criteria

1. Every bound local row reports independently calculated whole-number outgoing and incoming DPS over `(now - 10 seconds, now]` with a fixed denominator of ten.
2. Every unbound row reports both directions as unavailable and renders one `NO LOG` state, never fabricated zeros.
3. The 420px Fleet Bar renders Character, one split Damage region, and EWAR without a fourth column or row reordering.
4. OUT is always left of the center axis; IN is always right and adjacent to EWAR.
5. Each rail independently normalizes against the highest numeric value among the page's visible rows; values through `10,000,000` remain fully visible, while larger defensive values use `>10m` visually and preserve the exact value accessibly.
6. Labels, geometry, and accessible text communicate direction without relying on color.
7. Incoming damage does not refresh EWAR lifetime or change Alert behavior.
8. Source/session resets and fact-ordering guards apply equally to both directional metrics.
9. Fleet-sharing protocol version 1, its sparse projection, serialized body, and privacy boundary remain unchanged.
10. Focused Python, bridge, executable JavaScript, browser geometry, and Windows/WebView2 smoke verification cover the new behavior at the supported display scales.
