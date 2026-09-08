# Preview cycle groups

Design. Base: `main` (`04156dd`), 2026-09-02. Approved in user brainstorming and revised after independent review.

## Outcome

A multiboxer can create named character groups such as DPS, Logistics, and
Scanner and bind one global forward-cycle key to each group. Pressing that key
visits only the running, preview-enabled characters assigned to that group.

The existing forward and backward cycle keybinds remain the **All characters**
cycle. Every preview-enabled character remains in All regardless of named-group
assignment, and each character may belong to at most one named group. A
character with no named assignment is shown as **All only**.

This is configuration and remains in Settings > Previews. It adds no destination
or floating control.

## Evidence and constraints

**The settings schema already reserves this evolution.**
`wingman/settings.py` stores flat `hotkeys.cycle_next` and `cycle_prev` fields
and says they become the default group's bindings when named cycle groups land,
so existing installs need no migration. Those fields remain the source of the
All cycle.

**The existing cycle is identity-anchored, not index-anchored.**
`wingman/preview/cycle.py` sorts and deduplicates names, advances from a stable
character identity, and falls back to the first entry when the anchor has left
the set. Named groups preserve that behavior. They do not introduce a stored
list index that silently changes meaning as clients log in or out.

**The cycle set already excludes preview opt-outs.**
`PreviewHost._cycle_keys()` returns running characters minus
`preview.excluded`. Named groups filter that same running, non-excluded set by
membership. An opted-out character keeps its saved group assignment but is not
a cycle destination until Preview is ticked again.

**Hotkey actions are folded before one activation.** The preview host drains
queued `WM_HOTKEY` messages and folds direct-focus and relative-cycle actions in
arrival order. A group action must carry stable group identity so rapid mixed
All/group presses resolve against the correct roster without activating every
intermediate target.

**The current character table is deliberately five tracks wide.** The Character,
Preview, Keybind, action, and Geometry tracks fit at the 840x625 window floor
only after Lock and Never minimize moved out of the table. Group assignment must
not add a sixth track. It belongs beneath the name inside the existing Character
cell.

**The page does not execute in CI.** Tests inspect web source lexically but do
not run or render it. The feature needs source guards, realistic `?dev=1` data,
generated screenshots at the floor, and a Windows pass with real global
hotkeys.

**Settings commit per operation.** There is no Save button. Discrete controls
commit on change; free text commits on Enter or an explicit action, never on
blur. A refused write restores the authoritative value and explains the
failure.

## Decisions for review

### 1. All is implicit and backward-compatible

The existing cycle fields retain their shape and meaning:

```text
preview.hotkeys.characters
preview.hotkeys.cycle_next
preview.hotkeys.cycle_prev
```

The page relabels the two cycle rows from **Cycle forward** and **Cycle back** to
**All forward** and **All back** so their scope remains clear beside named
groups. Every non-excluded running character participates, including one also
assigned to DPS or another named group.

A named assignment is therefore additional scope, not removal from All. The
selector value **All only** means only that the character has no named group.
It does not add the character to All; All membership is already implicit.

No defaults-version bump or one-shot migration is needed. Existing settings
have no named groups, retain both current cycle chords byte-for-byte after
normalization, and render the character table exactly as before until the first
group is added.

### 2. Named groups use stable IDs and normalized exclusive membership

The hotkey section grows two fields:

```json
{
  "groups": [
    {"id": "stable-opaque-id", "name": "DPS", "cycle": "Ctrl+Shift+1"}
  ],
  "group_by_character": {
    "Aiga Otsolen": "stable-opaque-id"
  }
}
```

A list preserves user-visible creation order. An opaque ID, generated when the
group is created, keeps rename from changing identity, memberships, hotkey
actions, or per-group runtime cycle history. Names are presentation, not keys.

The membership map makes “at most one named group” structural: a character name
has zero or one group ID. It is preferable to a members list on every group,
which would require the validator to resolve a character present in several
lists.

Validation:

- `groups` must be a list of objects;
- IDs and names must be non-empty strings;
- IDs must be unique;
- names are trimmed and unique case-insensitively;
- `cycle` is empty or canonicalized through `preview.gestures`;
- malformed groups are dropped independently rather than discarding the whole
  preview section;
- membership keys use the existing preview-roster character constraints,
  including rejection of unstable `hwnd:` names;
- membership pointing to a missing group is dropped;
- unknown fields are not preserved.

Group names are not role enums. Users create the vocabulary that matches their
fleet.

### 3. Each named group has one forward-only cycle keybind

Named groups intentionally omit a backward binding in this first version. All
keeps both existing directions. This limits both screen height and global chord
consumption while answering the requested role-specific switch.

A named group walks only the intersection of:

1. currently discovered, stably named clients;
2. clients not in `preview.excluded`;
3. character names mapped to that group ID.

Within that set, the existing deterministic name ordering remains unchanged.
This feature does not take the opportunity to change the current case-sensitive
sort, because `docs/preview-roadmap.md` records that as a separate user-visible
ordering change.

If the foreground EVE character belongs to the group, cycling advances from it.
If the foreground is an EVE character outside the group, it is a missing anchor
and the action starts at the group's first running member. Outside EVE, the host
continues from that group's own last-cycled character. If that character logged
off or left the group, the existing missing-anchor rule starts at the first
running member. An empty group is a logged no-op.

Runtime history is per stable group ID, with the existing scalar history
retained for All. It is not persisted. Deleting a group drops its history;
renaming does not.

### 4. Hotkey planning carries group identity and keeps deterministic precedence

`plan_registrations()` continues to merge duplicate character-focus chords
first. It then plans All forward, All back, and one named-group cycle action per
group in visible creation order. Existing All actions retain their
`("cycle", delta)` shape. A named group uses
`("cycle_group", stable_group_id)`, with forward `+1` implicit because named
groups have no backward action in this version. Names never enter dispatch
identity.

Registration precedence is therefore:

1. character focus bindings;
2. All forward;
3. All back;
4. named groups in visible order.

This preserves the existing character-over-cycle and All-forward-over-All-back
rules and gives named groups one deterministic extension. The page's
`clashes()` calculation counts `cycle_next`, `cycle_prev`, and every
`groups[*].cycle`, so a group-versus-character or group-versus-group binding
dropped by the planner is marked on every affected row rather than failing
silently. Several characters may still share one focus chord; that remains a
supported setup and is not reported as a conflict.

`PreviewHost` resolves a group action through a new
`_group_cycle_keys(group_id)` helper, which filters the same live,
non-excluded character set as `_cycle_keys()` by the current membership map
before calling unchanged `cycle.step()`. Membership comes from an
`_active_hotkeys` snapshot installed on the preview thread by
`_apply_hotkeys()` in the same turn as `_registered`; it does not read
`_desired_hotkeys`, which may already describe a newer table whose Windows
registrations have not been applied. Teardown clears both snapshots.

Rapid mixed actions retain sequential meaning. For example, DPS then Logistics
applies DPS's step to the current virtual target, then applies Logistics's step
to that result. If the DPS target is not in Logistics, the second action uses
the existing missing-anchor rule and starts at Logistics's first running
member. The host activates only the final target.

History bookkeeping is per cycle scope, not merely for the final cycle action.
During one folded batch, every successful All cycle updates a pending All
history value and every successful named cycle updates a pending value keyed by
its stable group ID. After the fold, those pending values update `_last_cycled`
and the per-group history map respectively, even when a later direct-focus
request determines the final dispatch target. This preserves the current rule
that direct focus does not rewrite cycle fallback history.

The existing `cycle_seen` concept remains one boolean because it answers only
whether the final target can skip redundant activation when it already equals
the foreground client. The cycle scope does not change that answer. It is not
used for history ownership; the per-scope pending values above own that. Thus a
mixed batch that resolves back to the starting foreground remains a no-op, as
today, without losing any scope's sequential history.

### 5. Groups are compact above the existing character table

The **Global keybinds** card keeps its current explanation of global scope and
bookmark precedence. Its binding stream becomes:

1. All forward;
2. All back;
3. one keybind row per named group;
4. group management;
5. the existing character table.

Named-group keybind rows use the same capture button, Clear, and Edit… behavior
as existing preview bindings. They do not add a new control vocabulary. An
empty group remains bindable so a user can prepare a fleet before its characters
are online.

Group management is an inline disclosure, not a modal:

- collapsed summary: **Manage groups** plus the group count when nonzero;
- an Add group field with an explicit **Add** button; Enter performs the same
  commit;
- one compact row per group with its name, **Rename…**, and **Delete** actions;
- rename uses `WM.prompt` and commits only when that page-owned prompt is
  accepted, never on blur;
- delete uses `WM.confirm`, names the group and exact assigned-character count,
  and states that those characters remain in All.

Delete is `.btn.danger`, because it irreversibly removes the group's cycle
keybind and assignments. The page derives the confirmation count from the
membership map in the latest authoritative payload rather than storing a
second count. While a group lifecycle or assignment write is in flight, those
controls take their normal temporary disabled/loading state, so this single
page cannot alter membership between composing the confirmation and sending
the delete. The delete endpoint re-resolves the group under the writer lock and
removes its membership map entries atomically, leaving those characters as All
only.

No group-management control is shown per character. The roster remains the
assignment surface; the disclosure owns only lifecycle.

### 6. Assignment stays inside the Character cell

When at least one named group exists, every known character row gains a compact
native select beneath its name. Its options are **All only**, then group names
in creation order. Changing it commits immediately through a per-character
endpoint.

The select is appended to the existing `.lab` character-cell node, not to the
grid row, so `makeRow` gains no additional `row.appendChild` and the five-cell
track invariant is unchanged. The Character heading still names the cell.
While selectors are present, a scoped class makes only character `.lab` cells
stack their existing `.lab-name` and select vertically; cycle rows retain their
current geometry. The select takes `width: 100%`, `min-width: 0`, and
`max-width: 100%` inside the existing bounded `minmax(150px, 260px)` track.
The current name ellipsis and title remain. A long selected group may
ellipsize visually, but its option text and accessible value remain complete.
The select uses the existing dark field vocabulary and keeps normal enabled
text treatment on an offline row, because offline membership is still
editable.

When there are no named groups, the select is not rendered. This preserves the
current row height on existing installations and avoids a control whose only
option is the value already in force.

Assignment remains available for offline characters because the existing table
merges running clients, the persisted seen roster, and names with character
bindings. A character need not be running to be prepared for the next fleet.
The Preview opt-out continues to disable controls that act on a nonexistent
preview; it does not disable the group selector, because saving membership for
later remains a valid action.

### 7. Group writes are operation-specific and serialized

The page must not replace the full groups/membership structure from a stale
snapshot. pywebview may serve calls on separate threads, and clients can open or
close while a keybind capture or assignment write is in flight.

Add operation-specific API methods for:

- create group;
- rename group;
- delete group;
- set one group's cycle binding;
- assign one character to a group or All only.

Each method validates its narrow input, mutates the latest live document inside
`settings.update()`, and returns `{applied, persisted, error}` plus the
normalized authoritative group state where the page needs to repaint. A failed
write leaves the previous control value visible after refresh and reports a
specific inline error.

`Api.__init__` creates one non-reentrant `threading.Lock` named
`self._preview_hotkey_lock`. Every method that mutates `preview.hotkeys`,
including the existing `set_preview_binds`, acquires it before entering
`settings.update()` and releases it only after the successful normalized table
has been handed to `PreviewHost.set_hotkeys()`. The order is therefore lock,
persist, host delivery, unlock. Read-only state methods, preview restyles, and
non-hotkey preview settings do not take this lock.

The existing `set_preview_binds` endpoint continues to validate and replace the
character bindings and All forward/back fields it owns, but no longer assigns a
three-key object over the whole `hotkeys` section. Inside the update it starts
from the latest durable hotkey object, replaces only `characters`,
`cycle_next`, and `cycle_prev`, and leaves `groups` and
`group_by_character` intact. It never accepts group metadata back from the
page. Named-group endpoints likewise mutate only their owned entry. This
prevents a character-keybind save from wiping every group, and prevents an
older whole-table snapshot from resurrecting a deleted group or undoing a newer
assignment.

After a successful mutation the host receives the normalized complete hotkey
table while `_preview_hotkey_lock` is still held. A persistence failure calls no
host method. Consequently two bridge threads cannot apply host tables in the
reverse of their durable write order.

### 8. Pushes and capture do not detach active controls

`get_preview_hotkey_state()` and `onPreviewHotkeys` add groups and membership to
the existing single payload. There is no second fetch whose result could paint
a roster from a different generation.

The current capture guard remains authoritative: a push while any keybind row is
armed defers the full render until capture ends. Named-group rows use that same
path. Assignment and group-management handlers patch only the control and
summary they own when no newer payload has landed; otherwise they refresh from
the authoritative payload. They do not rebuild the table beneath a focused
select or armed capture.

Deleting the group currently selected by a character repaints that character as
All only. Renaming updates the visible group row and every affected select
without changing their stable selected ID. The assignment select remains a
child of the existing `.lab` cell throughout these repaints; it never becomes a
sixth grid child.

## Failure behavior

- Invalid, duplicate, or empty group names are refused with the field left
  editable and a specific inline message.
- A stale group ID in an assignment request is refused and the selector returns
  to the authoritative value.
- A group deleted while its rename or keybind request is in flight cannot be
  recreated by that older request; the operation-specific endpoint resolves
  against the latest document and refuses a missing ID.
- A persistence failure changes neither the live settings document nor host
  registrations. The page refreshes and reports that the change was not saved.
- A group with no running eligible member logs a DEBUG no-op and leaves the
  foreground unchanged.
- A group member logging out during hotkey folding is re-resolved before
  activation through the host's existing live-client lookup. No stale HWND is
  persisted or introduced into group state.
- Preview opt-out, group deletion, and assignment changes trigger a hotkey
  replan without starting or stopping the host.

## Testing

All implementation work is test-first.

### Settings and validation

- Existing settings with only `cycle_next`/`cycle_prev` round-trip unchanged.
- Defaults remain a fixed point of `validated_preview`.
- Groups preserve creation order and canonicalize valid chords.
- Malformed groups drop independently; duplicate IDs/names have one
  deterministic outcome.
- Membership accepts one stable character-to-group mapping, rejects `hwnd:`
  names, and drops references to missing groups.
- Rename preserves ID and membership; delete removes all membership pointing to
  that ID.

### Pure cycle and host planning

- A group cycle includes only running, non-excluded assigned members.
- Foreground member, foreground nonmember, outside-EVE history, missing history,
  one member, and empty group behavior.
- Histories are independent between All and every named group.
- Rename preserves history; delete drops it.
- Planner action identity uses group ID, order is deterministic, and duplicate
  precedence matches the design.
- Rapid All/group/direct-focus batches produce hand-derived final targets and
  only one activation.
- Capture returns a named-group chord rather than executing it.

### API and concurrency

- Create, rename, delete, bind, and assign mutate only their owned fields.
- Existing All/character binding writes preserve group metadata.
- Every endpoint tolerates no preview host and still persists.
- Persistence failure rolls the live document back and does not call the host.
- Concurrent stale operations cannot resurrect a group, revert membership, or
  apply host tables out of durable order.
- Public `Api` attributes remain methods or underscore-prefixed.

### Web source and rendered UI

- Named-group rows use the existing keybind capture, Clear, Edit…, clash, and
  unknown-registration treatments.
- The group selector is rendered inside the Character cell, not as a sixth
  track, and is absent when no groups exist.
- Select changes commit only after the first payload; name fields never commit
  on blur.
- Delete uses `WM.confirm`; no browser-native dialog is introduced.
- Rejected writes restore the authoritative value and report an inline error.
- A push during capture defers rendering; group mutations do not detach the
  focused select.
- `dev.js` supplies realistic All-only, assigned, offline, opted-out, empty, and
  keybind-clash states. `test_dev_harness.py` asserts that the fixture contains
  groups, exclusive membership, an empty group, and canonical group gesture
  strings rather than allowing the new fixture fields to be omitted silently.
- The grid-cell convention test additionally proves that group assignment is
  appended inside `.lab`, not as another row cell, while retaining the existing
  derived track-count assertion.
- Screenshot staging captures the complete card and 840x625 floor with long
  character and group names.

### Verification commands

```bash
uv run --no-sync python -m pytest tests/test_preview_cycle.py tests/test_preview_host.py tests/test_preview_wiring.py tests/test_settings_preview.py tests/test_page_conventions.py -q
uv run --no-sync python -m pytest tests/ -q
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
```

## Windows and EVE smoke checks

Update the existing **Cycle forward**/**Cycle back** references in
`docs/smoke-checklist.md`, `docs/ui-walkthrough.md`, and relevant live
stylesheet/source commentary to **All forward**/**All back** where they describe
the resting labels. Then add the following to `docs/smoke-checklist.md` and run
them with real clients:

1. Existing All forward/back chords behave exactly as before on an upgraded
   settings file with no groups.
2. Create DPS and Logistics, assign online and offline characters, and confirm
   each group chord visits only its running assigned members.
3. From a foreground member, a foreground nonmember, and a browser, verify the
   anchor/history behavior in decision 3.
4. Alternate All, DPS, Logistics, and direct-character hotkeys rapidly; the
   final client matches sequential meaning without displaying intermediate
   targets.
5. Opt a member out of previews. Its assignment remains selected, its focus
   chord is released, and its group cycle skips it. Re-enable Preview and it
   rejoins without reassignment.
6. Rename a group while previews run. Its chord and membership continue without
   reconfiguration.
7. Delete a populated group. The confirmation gives the exact assignment count,
   its chord is released, and every former member reads All only while remaining
   in the All cycle.
8. Log members in and out during repeated cycling. No wrong client, stale
   window, crash, or stuck hotkey results.
9. Arm a named-group keybind capture, then trigger a roster push by opening or
   closing a client. The capture remains visible and receives the next chord.
10. At 840x625, inspect the full card with long names. No sixth column, horizontal
    clipping, native light control, or inaccessible group value appears.

## Non-goals

- Membership in more than one named group.
- Backward cycle keybinds for named groups.
- Nested groups, group colors, icons, drag reordering, or fixed role templates.
- Group-specific preview placement, size, visibility, lock, alerts, or minimize
  behavior.
- A clickable runtime cycle button in Wingman's window; this feature configures
  global keybinds used while another application is foreground.
- Preview profiles or EVE-O/EVE-X profile import.
- Changing cycle name ordering, hotkey notation, preview switching mechanics,
  or the rule that Wingman never moves or resizes an EVE client window.
