# Saved Preview layouts — first slice (#213)

Status: approved for implementation planning in the maintainer conversation,
after independent review of the lossless-exclusion revision returned SHIP.
Implementation and task-scoped reviews are complete through Task 5. Task 6
[documentation and acceptance preparation](preview-layouts-implementation-notes.md#task-6--documentation-and-acceptance-preparation)
is recorded; fresh final whole-branch review/polish and global gates remain
coordinator work. Windows/WebView2/live-EVE acceptance and authorized integration
are still pending; #213 is not closed. The maintainer approved the
[shared-presentation amendment](preview-layouts-publication-amendment.md), retaining
the blanket no-page-work-on-pump guarantee. Inspected base: `76afd3dc34f20eb071c97f25cd6d891ae11c352a`.

## Approved behavior

- Call the feature **Saved layouts**, within Previews. Never call it Profiles.
- A named layout saves only primary-preview positions, sizes and per-character
  Preview visibility. Crops, companions, keybinds, locks, appearance, global
  placement/size preferences and foreground policy stay outside the snapshot.
- Named layouts are **explicit snapshots**. Ordinary moves, resizes and Preview
  checkbox changes keep saving the working arrangement as today. They never
  update a named snapshot automatically.
- Applying a snapshot changes only its recorded characters. Characters absent
  from it keep their current geometry and visibility.
- Include known offline characters when saving. A character can have a saved
  visibility choice without a known rectangle.
- Applying a layout uses its geometry immediately where live application is
  possible, without changing the global restore-positions preference. Later
  openings follow that preference. The UI currently calls it **Reopen previews
  where you last put them**; when Off, later openings use the default stack.
- Never move, resize, activate or otherwise manipulate a real EVE client as part
  of saving/applying layouts. Operations affect Wingman's primary previews only.

The original narrow boundary is recorded in
[preview-identification-design.md](preview-identification-design.md#independence-from-saved-layouts).
The maintainer subsequently approved explicit snapshots, leaving absent
characters unchanged, and respecting the global reopen preference for later
openings. Following independent review, the maintainer also approved lossless
retention of explicit Preview exclusions rather than a capacity-based Apply
refusal. The remaining sections propose how to deliver those decisions.

## User interaction

Add one compact Saved layouts block inside **Settings → Previews → Windows →
Placement**. No new destination or subpage, no widened window or character grid.
Use existing fields, buttons, page-owned dialogs and semantic status styling.

| Action | Result |
| --- | --- |
| Select a saved name | Page-local selection only. No settings write or window movement. |
| Apply… | Confirm replacement of the working geometry/Preview choices for the snapshot's character count, then apply. Other characters stay unchanged. |
| Save current as… | Prompt for a name and capture the current arrangement into a new snapshot. No window movement. |
| Update saved… | Confirm replacing the selected snapshot with a fresh capture, keeping its identity and name. No window movement. |
| Rename… | Change only the selected snapshot's display name. |
| Remove… | Confirm deletion of the selected snapshot. The working arrangement stays untouched. |

The Apply confirmation says to save the current arrangement first if it should
be kept. There is no automatic backup snapshot, undo history, or implicit
working-arrangement autosave into the selected name. Selection must not be
labelled “active layout”: subsequent ordinary edits can differ from that snapshot.

Keep the selector separate from wrapping action rows. Explain scope once:
“Saved copies of primary-preview positions, sizes and Preview choices.”
When reopen positions is Off, show its specific consequence near Apply rather
than silently enabling it. With EVE previews Off, management remains usable;
Apply saves the working arrangement for later without starting the runtime.
No known characters is an actionable empty state; Save is unavailable until
there is something to capture. A snapshot whose members are all hidden is valid.

Free text commits only through its dialog's explicit acceptance, never on blur.
Use `WM.prompt`/`WM.confirm`, not a Python confirmation from a bridge method.
Remove uses the existing destructive treatment. Applying a snapshot is an
explicit configuration operation, not a global Settings Save button.
Disarm keybind capture before any layout dialog. Preserve drafts, selected ID,
scroll and owned focus across pushes/tab changes; late replies must not reopen
or focus a departed panel. Disable only controls whose operations conflict.

## Data and compatibility

Keep `preview.layouts` as the current character-to-geometry map and
`preview.excluded` as its current Preview choices. Add a distinct versioned
`preview.saved_layouts` collection in the same settings document, default empty.
Existing installs do not acquire a fabricated named layout or lose current data.
No separate file, new dependency, account, executable identity or import format.

Proposed v1 record shape (illustrative values, not a runtime fixture):

```json
{
  "version": 1,
  "items": [
    {
      "id": "opaque-stable-id",
      "name": "Rolling",
      "characters": {
        "Example Pilot": {
          "visible": true,
          "rect": {"x": 100, "y": 200, "w": 320, "h": 210}
        },
        "Offline Pilot": {"visible": false, "rect": null}
      }
    }
  ]
}
```

Use generated stable IDs, not names as identity. Follow named cycle groups'
trimmed display names and case-insensitive duplicate-name refusal; refuse blank
or control-character names. Preserve exact character-name identity using the
existing strict owner validation; reject anonymous `hwnd:` keys and do not
casefold character keys. Render all names through DOM text properties.

An explicit `visible` boolean distinguishes a saved visible character from an
absent member. A null rectangle means **do not replace that character's current
geometry**, not “reset to defaults.” Strictly validate integer coordinates,
positive dimensions and safe native representability before admitting a write.
Do not copy the legacy `layout.Entry.locked` field into named records: effective
locks are global, and explicit geometry application does not alter them.

**Explicit exclusions are configuration, not recent history.** Retain every valid
entry in `preview.excluded`, independently of the 64-entry recent-history cap.
Preserve its existing identity validation and deduplication; remove only its
truncation. Do not raise the shared roster cap or broaden this change to other
per-character policies. `preview.seen` remains bounded as today.

Apply must preserve every existing exclusion for absent characters, add every
recorded hidden character, and remove only recorded visible characters. The
merged list must survive normalization, persistence, reload and unrelated writes
without eviction, regardless of insertion order. Exceeding 64 exclusions is not
an Apply refusal or a reason to silently drop a choice. Excluded-only owners
must remain available on the character page even outside recent history.

Normalization must retain this collection on every unrelated settings write.
A malformed record must not become a partially applied snapshot: reject the
whole record, retaining valid sibling records and the existing working
arrangement. Unknown schema versions are not interpreted as v1. This first slice
does not promise retention through older binaries that do not know the field.
Duplicate IDs/names follow the existing group load policy: keep the first valid
record, comparing display names case-insensitively. Live mutations refuse
invalid or duplicate names, IDs, stale record revisions or malformed records
before any change, with useful errors rather than silent normalization.

Derive snapshot membership from the application's known-character sources:
live named sessions, retained current geometry/history/Preview settings, and
explicit saved-layout owners. Include offline records; never infer a character
from an arbitrary source-window caption. Retain saved-layout-only owners in
page state independently of the capped recent roster. Removing a snapshot does
not delete the character's current settings or geometry.

## Capture, apply and ownership

**Use a small Preview-layout controller behind ports, not more orchestration on
`Api`.** Keep one-line bridge facades and literal semantic push adapters visible
to the existing contract tests. The controller owns named mutations and operation
receipts; the existing layout writer owns ordering with current-layout writes;
the host pump remains the sole reader/mutator of native preview geometry.
No second layout store, background polling loop or runtime start/stop owner.

Saving a snapshot cannot simply copy settings or `host.layout_entries()`:
settings may lag a debounce, `_saved` may omit untouched live placements, and an
active drag may not have committed its final rectangle. Capture live rectangles
on the pump, combine them with retained offline geometry, and sample committed
Preview choices at the same operation boundary. Temporary hide-active or
lost-focus visibility is not a saved Preview choice.

Use one admitted capture/apply reservation shared with operations that can alter
geometry or membership. A request encountering an active drag, uncompleted
Size/Copy/Reset, conflicting visibility write or runtime transition may refuse
with “Finish the pending Preview change and try again.” It must not take a torn
snapshot or leave a hidden queue of user requests. Recheck admission on the pump;
a page-side busy flag is not a concurrency guarantee. After reservation, new
conflicting commands/gestures cannot mutate the captured generation before the
operation settles. Unrelated settings and companion activity stay independent.

1. Admit and reserve a stable operation identity. Refuse final shutdown and stale
   IDs/revisions. Finish or refuse prior conflicting work before capture.
2. Capture/revalidate native and committed state without disk or page work on the
   pump. With the EVE family Off, use retained committed/offline state and the
   existing writer boundary; do not start a pump solely for a snapshot operation.
3. Serialize the operation behind any in-flight layout persistence. Preserve or
   supersede pending per-character deltas deliberately, never by clearing all
   pending work. Snapshot-only writes do not replace the current arrangement.
4. For Apply, merge recorded rectangles and visibility choices into current
   settings in **one** `settings.update()` transaction. Leave absent members and
   null rectangles untouched. Update the host's retained authority from that
   committed generation; do not loop over per-character Copy endpoints.
5. Deliver live changes in one generation-tagged pump batch. Preserve current
   effective locks and normal source/session validation. Primary exclusion
   changes use existing reconciliation/keybind policy; saved bind definitions
   remain unchanged. Existing crop/companion behavior is not redefined here.
6. Settle the correlated receipt and release admission only when prior callbacks
   can no longer overwrite the committed generation. Later user edits then own
   their normal deltas. A timeout alone is not proof that an admitted operation
   stopped; retain its owner until completion, with no overlapping replacement.

Do not hold the host state lock while waiting for disk, acknowledgements or
joins. A pump acknowledgement must not need a controller lock held by its
waiting caller. Integrate reservation admission/drain with existing EVE-off and
final-shutdown fences; final publication closes before native destruction.
No disk, page or network work belongs on discovery/telemetry callbacks.

A monitor rescue clamps applied live rectangles without rewriting a snapshot or
its saved preferred coordinates. Explicit Save/Update captures the resulting
current live arrangement by user choice; merely unplugging a monitor or applying
an existing snapshot must not overwrite that snapshot. Snapshot geometry also
must not redefine global default size or aspect preferences for future edits.

## Outcomes and recovery

- Persistence failure: refuse, preserving named records, working settings,
  committed host authority and current windows. Retain unsaved ordinary deltas
  rather than losing them on the failed batch.
- After successful persistence: never report that nothing was saved if EVE goes
  Off, a source disappears, or native application fails. Preserve the committed
  working arrangement and report **saved; live application deferred/incomplete**.
  Do not roll back over later work or implicitly re-enable previews.
- Expected offline members are not failures. Their choices persist, and later
  openings obey the approved global reopen rule. Missing geometry is untouched.
- Application cannot be visually atomic across separate HWND calls. The promise
  is a coherent committed generation with fenced ordering, not an instantaneous
  desktop-wide paint or transactional rollback of external/native failures.
- Keep `{applied, persisted, error}` consistent with existing Settings semantics:
  `applied` means accepted into working configuration, not proof every native
  window moved. Carry a separate explicit live outcome (applied, deferred or
  incomplete) and warning for Apply. Do not report mere queue admission as done.
- Reads and receipts expose detached committed state and a revision for stale
  request rejection. The page keeps newer drafts and another operation's error;
  entering a section may refresh state, selecting a name/tab does not add reads.

## Evidence and required verification

Existing seams inspected: `preview/layout.py` (`Entry`, serialization),
`preview/store.py` (`record`, `replace`, `flush`, `clear`), `preview/host.py`
(`layout_entries`, primary-intent admission, `copy_layout`, `_apply_layouts`),
`settings.py` (`validated_preview`, `update`), and current Preview markup/bridge.
`LayoutStore.flush()` has no success receipt and logs write failure; it is not
an acceptable substitute for the acknowledged operation above. The existing
optimistic live Reset endpoint is not the receipt template either.

The inspected `settings.py:627` normalizes `preview.excluded` with
`roster.deserialize()`, whose `roster.py:60` return truncates to its default cap
of 64. `settings.update()` normalizes every write (`settings.py:1188`). This is a
required compatibility change for the lossless contract, not an existing
capability: with 64 absent excluded characters, appending one newly hidden member
currently drops the new choice; prepending it evicts an existing exclusion.

Before implementation is accepted, require:

- Pure-model tests for membership, null geometry, strict validation, independent
  defaults, names/IDs, malformed whole-record rejection and unrelated-write
  round trips. No change to old installs' current state.
- Capacity-boundary tests through real settings transactions and save/reload:
  start with 64 excluded characters absent from a snapshot, apply one additional
  hidden member, and retain all 65 in either merge order. Making that member
  visible removes only its exclusion. Failed persistence restores the complete
  prior list; direct Preview-choice and unrelated writes must not reintroduce
  truncation. Verify recent history still caps at 64 and an excluded-only owner
  beyond that history remains editable on the page.
- Event-controlled store/controller/pump tests for pending and in-flight writes,
  active drags, untouched placements, offline operations, rollback, later edits,
  stale callbacks, failed posts, source replacement and Off/on/Quit admission.
- Apply tests proving absent characters, locks, crops, companions, keybind data,
  appearance, reopen preference and real EVE source geometry remain untouched
  except the existing consequences of each recorded primary Preview choice.
- Monitor and restore-Off tests distinguishing saved geometry from live rescue,
  explicit capture from automatic persistence, and immediate versus later opens.
- Executable production-page tests for hydration, stale revisions, delayed
  results, dialogs, capture cancellation, drafts/focus, refusal/retry and name
  rendering. Bridge conventions and all-page Node smoke remain green.
- Browser interaction/geometry checks at 840×625 and 839×621, separately from
  real Windows/WebView2/live-EVE smoke for multi-client apply, exclusions, locks,
  crops/companions, mixed monitors/DPI, restart and unchanged source bounds.
- Full pytest with Node and the built release codec, Ruff lint/format and the
  independent Cargo regression; review/polish followed by fresh verification.

No runtime or visual acceptance is established by this design. #216 may use the
settled model and transaction path later, but this slice adds no file import,
source-format aliases, companion mapping or layout switching keybinds.
