# Fleet Bar character visibility

## Summary

FlyGD Wingman will let users persistently choose which known characters appear
in the floating Fleet Bar. Configuration lives in **Settings > Previews > Fleet
combat bar**. The floating bar remains a display-only, full-surface drag target
with no row actions or context menu.

The setting affects only Fleet Bar presentation. It does not exclude a
character from client discovery, gamelog reading, Fleet Metrics, previews,
alerts, or preview keybinds.

## Goals

- Let a user permanently omit scouts, utility alts, or other characters from
  the Fleet Bar.
- Keep every hidden character available in Settings so the choice can always
  be reversed, including while that character is offline.
- Apply a visibility change immediately without restarting Wingman or the
  Fleet Bar.
- Preserve the Fleet Bar's compact, display-only interaction model.
- Keep Fleet visibility independent from the existing Preview exclusion list.

## Non-goals

- Session-only hiding.
- Row actions, context menus, or interactive controls in the floating bar.
- Reusing Preview visibility as Fleet visibility.
- Custom ordering, filtering by role, search, bulk show/hide controls, or
  separate profiles.
- Reducing discovery, gamelog, or metric-computation work for hidden
  characters.
- Identifying characters by EVE character ID. This feature uses the canonical
  character names already supplied by EVE-window discovery.

## User experience

### Settings

The existing **Fleet combat bar** card gains a collapsed native `details`
disclosure named **Characters** beneath the enable control and placement hint.
Keeping it collapsed preserves the section's current scan shape for users who
never need per-character configuration.

When current Fleet telemetry exists, the disclosure shows:

1. **Running** characters, sorted case-insensitively by name.
2. **Offline** remembered characters, sorted the same way.

When the Fleet Bar is off, its telemetry consumer is inactive and Wingman has
no authoritative Fleet roster. The disclosure instead shows one **Known
characters** group without claiming that anyone is offline. It does not borrow
PreviewHost state: Previews may also be off, and Fleet visibility must not gain
a dependency on Preview runtime state. Enabling the Fleet Bar replaces the
unknown grouping with Running and Offline as soon as its first complete
snapshot arrives.

Each character has one standard `.check` / `.box` checkbox. Checked means the
character is shown. The visible label is the character name and the input's
accessible name is `Show <character> in Fleet Bar`. Positive wording avoids an
inverted exclusion control.

A running character appears only in the Running group, even if it was already
remembered. Hidden characters remain in one of the groups and render unticked;
hiding never removes the route that restores them. Group headings are omitted
when their group is empty.

Before Wingman has observed any named character, the disclosure says:

> Characters appear here after Wingman sees them running.

The list remains editable while the Fleet Bar is switched off. Wingman permits
users to configure a preference for later rather than disabling controls whose
runtime feature is currently off. The absence of live telemetry changes only
the group label, not whether known characters can be configured.

No bulk actions or search ship initially. The remembered roster is capped and
the expected fleet is small; those controls would add weight before there is
evidence that scanning the list is difficult.

### Floating bar

Visible rows retain their current alphabetical order and metric semantics. A
hidden character contributes no row and no indication, count, or badge. The
bar refits after a visibility change just as it does after a roster change.

The empty state distinguishes two truthful conditions:

- No running named clients: `Waiting for EVE clients…`
- Running named clients exist, but all are hidden: `All running characters are hidden.`

If at least one visible row remains, no empty-state message is shown.

## Persistence and validation

The independent top-level section grows in place:

```json
{
  "fleet_bar": {
    "enabled": false,
    "x": null,
    "y": null,
    "seen": [],
    "hidden": []
  }
}
```

`seen` is a recency-tiered list of valid character names, capped at 64.
Characters in the current complete roster form its newest tier, sorted
case-insensitively for deterministic writes; remembered names not currently
running retain their prior relative order behind that tier. `hidden` is a
deduplicated list of valid character names capped at 64. Both use the same name
constraints as `preview.seen`: non-empty strings only, with unstable `hwnd:`
identities rejected. Malformed individual entries are dropped; a malformed
list becomes empty. Existing settings files acquire both empty lists through
normal section validation, so no explicit migration is needed.

The 64-name hidden limit is a mutation limit, not an eviction policy. Hiding a
65th character is refused with an inline explanation; Wingman never silently
restores an older hidden character or reports success for a name normalization
would discard. Restoring a character is always allowed.

The Settings roster is the union of:

- names in the latest Fleet snapshot,
- persisted `fleet_bar.seen`, and
- persisted `fleet_bar.hidden`.

Taking the union with `hidden` guarantees that a hidden character cannot age
out of the restoration UI even if `seen` reaches its cap. Running/offline state comes only from the latest complete Fleet snapshot,
never from persisted data. When Fleet telemetry is inactive or has not yet
published its first current-generation snapshot, running state is `null`
(unknown), not `false`.

Name matching is exact after discovery has supplied the name. Sorting uses
`(name.casefold(), name)`, matching existing roster conventions. A later EVE
character rename is therefore a new name; the old remembered name can remain as
an offline entry. Wingman has no character ID in this subsystem with which to
prove the two names are the same.

## Data flow and ownership

### Fleet activation generation

Transport revisions order UI deliveries, but they cannot by themselves prove
that a late callback belongs to the current Fleet activation. The coordinator
therefore adds a monotonic `activation_generation` to `FleetSnapshot`.

`TelemetryCoordinator` increments the requested generation on every Fleet mode
transition and queues that generation with `_FleetMode`. The dispatcher stamps
every snapshot with the generation it actually activated. `reconcile()` returns
the currently requested Fleet generation (existing callers may ignore the
return).

Generation handoff in `Api` is explicitly closed to callbacks. Before changing
the Fleet setting or calling reconciliation, the toggle path acquires the Fleet
presentation lock, saves the prior accepted generation/snapshot/signature, sets
the accepted generation to a rejecting sentinel, and clears current state. Any
callback arriving during the settings/reconciliation phase is therefore
discarded regardless of its generation. After `reconcile()` returns, `Api`
installs the returned generation under the presentation lock. It then reads
`TelemetryCoordinator.snapshot()` and routes that latest value through the
ordinary generation check, recovering a current snapshot whose callback arrived
during the closed handoff; otherwise the next cadence publication fills it.

If the enabled-setting transaction fails before reconciliation, the toggle is
refused and the saved accepted generation/snapshot/signature are restored under
the presentation lock before callbacks are accepted again. The previous
coordinator mode never changed, so restoring that complete prior acceptance
state is the truthful rollback. A `try/finally`-shaped handoff guarantees that
no exception path can leave the rejecting sentinel installed permanently.

Startup uses the same handoff rather than treating it as a toggle-only rule:
`Api` begins with the rejecting sentinel, startup reconciliation returns the
persisted Fleet mode's requested generation, and only then does `Api` open
acceptance and sample the coordinator's latest snapshot. A reconcile caused
only by Preview, Alert, or folder settings does not close Fleet acceptance when
Fleet mode itself is unchanged.

`Api._receive_fleet_snapshot()` rejects a snapshot whose activation generation
does not equal the accepted generation before changing `_fleet_snapshot`, the
semantic roster signature, pending names, or presentation revision. Disabling
therefore retires the old generation before the coordinator can race the
transition. A rapid disable/re-enable cannot admit an old callback merely
because the enabled flag has become true again. This extends the existing rule
that re-enabling opens on WAITING rather than flashing rows cached from a prior
session.

The activation generation is runtime-only and is not written to settings or
shown to users.

### Remembering characters

`Api._receive_fleet_snapshot()` remains the coordinator's Fleet subscriber. It
compares the snapshot's running-name set with the prior snapshot before doing
any persistence or main-page work. On a semantic roster transition, it builds
a deterministic candidate `seen` list: all current names as the newest sorted
tier, followed by previously remembered non-current names in their existing
order. It writes only when that final candidate differs from persisted state.
Metric-only publications therefore do not touch settings or the main page.

Remembering names is independent of Preview runtime state. This is necessary
because Fleet-only mode deliberately runs discovery while previews and the
Preview host remain off.

If the background write fails, snapshot delivery continues. The candidate
names remain in a small in-memory pending set used by the Settings roster for
the rest of the session, and the exception is logged once for that semantic
roster transition. Wingman retries on the next running-roster transition, not
on every one-second metric publication. A pending name can therefore still be
configured in the current session without turning a disk failure into a write
and log loop.

### Settings payload

`fleet_bar_settings()` returns the persisted Fleet section plus a derived
`characters` array for the Settings page:

```json
{
  "enabled": true,
  "x": 24,
  "y": 48,
  "seen": ["Alice", "Bravo"],
  "hidden": ["Bravo"],
  "revision": 17,
  "characters": [
    {"name": "Alice", "running": true, "visible": true},
    {"name": "Bravo", "running": false, "visible": false}
  ]
}
```

`characters` is derived and never persisted. Each `running` value is `true` or
`false` only while a current-generation Fleet snapshot exists; it is `null`
while Fleet telemetry is inactive or still waiting for that first snapshot.
The page does not merge settings and telemetry itself.

The existing `onFleetBarState` event carries this complete semantic state to
the main page. Its handler remains registered before the larger Preview module
so an unrelated setup failure cannot leave Fleet controls inert. Snapshot
receipt pushes this event only when the semantic roster signature changes
(names or known running membership), never for a DPS/EWAR-only update. Toggling
Fleet, mutating visibility, and transitioning into or out of unknown runtime
state also push it.

### Visibility mutation

A dedicated bridge method accepts `(name, visible)` and returns Wingman's
standard result plus authoritative Fleet state. It validates the name, enforces
the hidden-name limit, then adds or removes it from `fleet_bar.hidden` in one
settings transaction. An unchanged request is a successful no-op and performs
no file write.

For this endpoint, a persistence failure is a refusal: `settings.update()`
rolls the live dictionary back when its save raises, so the visibility effect
did not apply in memory either. The endpoint returns `{applied: false,
persisted: false, error, state}` and the checkbox reverts. It does not claim the
separate “applied but not persisted” outcome used by settings whose runtime
effect survives a failed write.

After an applied mutation, Python:

1. allocates a new Fleet presentation revision;
2. pushes the complete Fleet settings state to the main page;
3. rebuilds and pushes the Fleet display payload to the auxiliary window; and
4. returns the authoritative state and revision in the bridge response.

The response is the reconciliation path even if a best-effort push silently
fails. The page never has to infer persisted state from its optimistic input.

Concurrent Fleet snapshots and visibility writes may arrive on different
threads. A dedicated Fleet presentation lock protects `_fleet_snapshot`, the expected
activation generation, the semantic roster signature, pending seen names, and
a monotonic presentation revision. A
producer captures a complete immutable settings or display payload and its
revision while holding that lock, then performs `settings.update()` and
`evaluate_js` only after releasing it. Settings mutation and presentation-state
mutation are separate phases; the settings save lock and Fleet presentation
lock are never nested. After a settings phase, the producer reacquires the
presentation lock, reads the complete replaced Fleet section, allocates the
next revision, and builds the payload. Both pages remember the greatest
revision they have rendered and ignore an older push or bridge response. This
prevents an older snapshot push from repainting a just-hidden row and prevents
overlapping requests from restoring stale checkbox state. No operation mutates
a `FleetSnapshot` or a `FleetRow`.

Each row allows at most one visibility request in flight. Its checkbox is
disabled until that response settles. Roster reconciliation is keyed by
character name and updates existing controls in place where possible. If a
running/offline transition must move the focused row between groups, focus is
restored to that character's recreated checkbox. Background state must not
collapse the disclosure, detach an unchanged focused control, or repeat a live
status announcement for an unchanged semantic roster.

### Display filtering

Filtering belongs in `Api._fleet_payload()`, at the Python-to-Fleet-window
presentation boundary. Client discovery and `FleetMetrics` continue to own the
complete active roster and compute all rows. This preserves subsystem
independence, avoids resetting metric state when visibility changes, and makes
restoration immediate.

The display payload adds `running_count`, the count of complete unfiltered
snapshot rows, plus the presentation `revision`. `rows` contains only rows
whose character is not hidden:

```json
{
  "rows": [],
  "running_count": 2,
  "revision": 17,
  "stream_health": {"state": "active", "detail": null},
  "metric_error": null
}
```

The standalone page rejects payloads older than its rendered revision, then
derives the all-hidden empty state from `rows.length === 0 && running_count >
0`. The default/no-snapshot payload has `running_count: 0`. Health and metric
diagnostics remain global and are not filtered with rows.

## Error handling and edge cases

- A malformed settings section falls back to the complete Fleet defaults.
- Malformed list members are discarded independently.
- A visibility request for an invalid or unknown name is refused. A known name
  is one present in the latest snapshot, persisted `seen`, persisted `hidden`,
  or the session's pending-seen set; this prevents a page or hand-built bridge
  call from filling settings with arbitrary names.
- Hiding a 65th character is refused without changing any existing choice;
  restoring a character remains available at the limit.
- Hiding the final visible running character leaves the enabled floating window
  open and draggable with the all-hidden message.
- Restoring a running character immediately restores its current accumulated
  DPS/EWAR row because metric collection never stopped.
- Restoring an offline character changes Settings only; its row appears the
  next time discovery reports it running.
- Turning the Fleet Bar off does not clear `seen` or `hidden`.
- Preview exclusion and Fleet exclusion can disagree in either direction and
  neither mutation changes the other list.
- If visibility persistence fails, `settings.update()` rolls back the in-memory
  section, the endpoint refuses the mutation, and the checkbox returns to its
  prior authoritative value.
- While Fleet telemetry is inactive, known characters are not described as
  offline; their runtime state is unknown until a current snapshot arrives.

## Files and components

- `wingman/settings.py`: defaults and validation for `seen` and `hidden`.
- `wingman/telemetry/model.py` and `wingman/telemetry/coordinator.py`: stamp and
  expose the Fleet activation generation used to reject retired callbacks.
- `wingman/ui/api.py`: generation rejection, roster derivation, sparse name
  persistence, visibility endpoint, display filtering, and synchronized pushes.
- `wingman/web/index.html`: collapsed Characters disclosure and status slot.
- `wingman/web/previews.js`: authoritative roster rendering and immediate
  per-field commits.
- `wingman/web/style.css`: only the layout needed to align the compact roster
  with existing Settings controls and Running/Offline/Known vocabulary. Any
  authored display rule on the disclosure body has an explicit
  `details:not([open])` override so WebView2 cannot expose closed content, and
  the `summary` has the shared visible `:focus-visible` treatment.
- `wingman/web/fleetbar.js`: semantic all-hidden empty state.
- `wingman/web/dev.js`: Fleet roster fixture and mutation stub for browser
  smoke testing.
- `docs/smoke-checklist.md`: Settings and auxiliary-window manual checks.

No new package or runtime dependency is required.

## Testing

### Settings and API

- Defaults and old files gain empty `seen` and `hidden` lists.
- Validation drops malformed, duplicate, empty, and `hwnd:` entries and caps
  each list.
- Save-time normalization writes the complete section shape.
- Snapshot receipt promotes the current roster as one deterministic recency
  tier, remembers newly observed names, and does not write or log for an
  unchanged roster on every publication.
- A failed background roster write retains session-pending names and retries on
  a later semantic roster transition rather than every metric tick.
- Hidden names remain in the derived Settings roster after `seen` eviction.
- Running names precede offline names; each group sorts case-insensitively.
- Invalid and unknown visibility mutations and the 65th hide are refused.
- Applied, no-op, and persistence-failure/refused outcomes obey the Settings
  transaction contract.
- Interleaved snapshot and visibility publications carry monotonic revisions;
  delayed payloads cannot repaint stale row or checkbox state.
- A callback from a retired Fleet activation, including one forced during the
  closed reconciliation handoff, is rejected before it can change snapshots,
  remembered names, revisions, or either page.
- Persisted-enabled startup installs its accepted generation before sampling
  the coordinator's latest snapshot; callbacks arriving before that are
  rejected and recovered from the latest-value read or next publication.
- A forced Fleet-toggle settings-write failure restores the prior accepted
  generation, snapshot, and roster signature rather than leaving callback
  acceptance closed.
- Main-page Fleet state is pushed for semantic roster transitions, not
  DPS/EWAR-only publications.
- Visibility changes push both authoritative Settings state and a refiltered
  Fleet snapshot.
- Fleet filtering does not mutate metrics or Preview exclusion state.
- Re-enabling the Fleet Bar retains both lists while still clearing stale
  snapshot generations as it does today.

### Web source contracts

The repository does not execute this JavaScript in pytest. Automated web checks
are therefore limited to lexical contracts and Python payload behavior:

- Generated-checkbox source uses `.check` / `.box` and assigns row-specific
  accessible names.
- Source includes the no-commit-before-hydration guard, revision rejection,
  per-row pending gate, keyed focus-restoration path, and closed-`details` CSS
  override.
- Python payload tests cover running, offline, unknown, hidden, duplicate-free,
  and no-known-character data shapes.
- Python payload plus lexical source checks cover the no-clients/all-hidden
  branch and the subsequent `fit()` call; actual DOM behavior remains a manual
  check.
- The floating page remains free of buttons and inputs.
- Existing bridge and page-convention lexical guards cover any new handler or
  markup convention.

### Manual Windows smoke pass

- Observe several characters, then verify Running and Offline grouping as
  clients log in and out.
- Hide and restore the first, middle, and final visible running character.
- Verify the all-hidden message and that the empty bar remains draggable.
- Hide while DPS or tackle is active, then restore and confirm the current
  metric state returns without a reset.
- Configure visibility while the Fleet Bar is off; verify the list says Known
  characters rather than falsely labelling them Offline, then enable it.
- Restart Wingman and verify hidden choices and offline restoration controls
  persist.
- Navigate the disclosure entirely by keyboard. Verify focus survives a commit
  and a running/offline row move, the disclosure stays open, and rapid repeated
  activation cannot resolve out of order.
- Simulate or instrument visibility persistence failure and verify the box
  reverts with one inline error rather than claiming a session-only change.
- Exercise the 64-name hidden limit and verify the next hide is refused without
  silently restoring an older character.
- Verify Preview visibility, alerts, and keybind behavior are unchanged for a
  Fleet-hidden character.
- Exercise the Settings card and floating bar at 100%, 125%, 150%, and 200%
  display scaling.

## Compatibility

Existing installations default to showing every character, exactly as before.
The schema grows within the existing `fleet_bar` section and is normalized by
the current load/save path. No migration marker or version bump is needed.

The feature revises the original Fleet Bar design's v1 non-goal of
per-character configuration. It does not revise that design's stronger
interaction decision: the auxiliary window remains display-only, and all
configuration remains in Settings.

## Acceptance criteria

1. Every running named character remains visible by default on existing and
   new installations.
2. Unticking a known character in Settings removes its Fleet row immediately
   and persistently without changing Preview or Alert behavior.
3. Hidden offline characters remain listed in Settings and can always be
   restored; while Fleet telemetry is inactive they appear as Known rather
   than being falsely described as Offline.
4. Restoring a running character immediately shows its current telemetry
   without waiting for a new session or resetting metrics.
5. An enabled bar with running clients but no visible rows says `All running
   characters are hidden.` and remains draggable.
6. The one-second snapshot cadence does not cause repeated settings writes,
   main-page pushes, or repeated failure logs for an unchanged roster.
7. Older concurrent snapshot or mutation results cannot repaint newer Fleet
   rows or Settings checkboxes, and callbacks from a retired Fleet activation
   cannot be assigned a new presentation revision.
8. A failed visibility save or a 65th hide is refused without changing or
   evicting an existing persistent choice.
9. Malformed persisted names and invalid bridge requests cannot corrupt the
   Fleet settings shape.
10. Automated checks pass and the Windows smoke checklist records the
    UI/runtime behavior that pytest cannot render.
