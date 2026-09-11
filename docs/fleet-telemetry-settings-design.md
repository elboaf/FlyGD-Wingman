# Fleet telemetry Settings and attempt history

Status: revised after independent review; both findings accepted and incorporated.
Implemented in the linked worktree; installed Windows/WebView2 acceptance remains
open. See [implementation and verification](fleet-telemetry-settings-verification.md).

Baseline: upstream `main`, `04e9e9b9c6c8f404bdd71e4650d65d4c9632ba64`
(`Add configurable gamelog alerts (#202)`), fetched before creating the linked
worktree on branch `ui/fleet-telemetry-settings`.

Before implementation the worktree was fast-forwarded to current upstream
`491bfd59` (`Make Fleet Bar threat-first and horizontally resizable (#204)`).
The relocation includes its Fleet Bar Reset width control and preserves the new
display behavior; no floating-window/native changes are part of this task.

## Goal and scope

Make Fleet setup discoverable in its own Settings section and keep ended roster
verification attempts from crowding current work. This is presentation and
navigation cleanup, not another activation or consent implementation.

The request explicitly supersedes PRODUCT.md's placement of Fleet controls under
Previews. Retain Wingman's existing dark, plain HTML/CSS/ES5 design, per-field
persistence, and bridge/controller ownership. No new top-level destination,
framework, dependencies, global Save button, or unrelated redesign.

Do not change pairing, Fleet Read authorization, boss verification, ESI retry or
rate-limit behavior, protocols, database or journal formats, or retained backend
records. Do not deploy authGD, publish a release, or mutate live fleet state.

## Confirmed implementation constraints

- `wingman/web/index.html` currently places Fleet combat bar and Fleet sharing
  cards inside `section-previews`, among actual Preview controls. Its Preview
  shortcut uses `data-preview-jump`; that handler scrolls rather than navigating.
- `wingman/web/app.js` owns section selection, remembered in-session section,
  `WM.openSettingsSection`, section enter/leave notifications, and `WM.EVE_SECTIONS`.
  Leaving Settings also dispatches a section notification. Bookmarks and Previews
  rely on this to disarm document-level keybind capture.
- At the upstream baseline, the first IIFE in `wingman/web/previews.js` owns Fleet
  bar settings, keyed character visibility rows, the status-strip toggle, and
  boot hydration. The final scope correction moves that complete controller into
  `wingman/web/fleet.js`; its runtime remains independent of visiting Settings or
  Preview enablement.
- `wingman/web/fleetsharing.js` owns one sharing state handler and a serialized
  watch chain. Its visibility predicate currently requires the Previews section.
  It merges server sources, local Start results, and pending source commands by
  source UUID and avoids moving correctly positioned DOM rows on heartbeats.
- Source observations in `wingman/fleetsharing/protocol.py` have state/reason and
  `pending_expires_at`, but no terminal event timestamp. That deadline is not an
  end time. UUIDs, array order, and whole-payload `presentation_order` cannot
  establish which historical attempt ended last.
- `source_results` in `wingman/fleetsharing/worker.py` contains bounded,
  session-only rejected/expired local Starts. These are not server-ended source
  records. Pending commands can coexist with an older ended observation.
- `wingman/ui/api.py` owns worker/subscription lifetime and pending-command
  handling. Moving a panel does not justify new owners or subscriptions.

## 1. Settings → Fleet telemetry

Add an EVE-gated `fleet` section labelled **Fleet telemetry** to the existing
Settings rail, adjacent to Previews. It contains two existing-style cards:

1. **Fleet combat bar** — local floating display switch, display status, and
   per-character visibility. Explain that hiding the bar changes only the view.
2. **Fleet sharing** — connection and participation controls, boss selection,
   Fleet Read authorization, Start verification, source Stop controls, account
   sources, and the existing eligible-character/details disclosure.

Keep local display and shared setup visibly separate; neither card's switch is
presented as the other's master switch. Preserve the status-strip Fleet bar
toggle as a display toggle, not a sharing or source action.

Move the markup, retaining control IDs and existing event bindings. Per the
final scope correction, extract the self-contained Fleet Bar controller from
`previews.js` into `fleet.js`, loaded immediately before `previews.js`. Preserve
the controller's one pushed handler, boot hydration, and global status-strip
synchronization even when Fleet telemetry is closed. Do not duplicate or
section-gate that controller. If the initial read fails, show a failure message
and retry only on Fleet section re-entry while still unhydrated, with at most one
read in flight. Successful hydration keeps later section changes read-free.

Include #204's `#fleetbar-reset`, tokenless Settings `reset_fleet_bar_width` call,
hydration, failure/session-only warnings, and status-strip synchronization.
Preserve `preferred_content_width` (default 500px, bounds 420–720px) and the
settings format. The floating window's token-bound `reset_fleet_bar_page_width`,
`hide_fleet_bar`, activation/deactivation, and resize lifecycle remain untouched.
Do not restore fixed-width sizing or removed `fit_fleet_bar`/`move_fleet_bar`
methods. The separate session owns mixed-row DPS alignment, obsolete height-fit
retries, programmatic monitor clamps, and authGD's joint-proof adapter/revision
pin; none belong in this patch.

Actual client previews, cropping, cycling, layout, and preview keybind controls
stay in Previews. Replace the Fleet-specific Preview jump with a cross-section
shortcut through `WM.openSettingsSection('fleet')`, not a DOM-only scroll or
visibility manipulation. Audit other Fleet-specific links and fixture navigation
for the same change; generic Preview links retain their existing target.

Add `fleet` to the EVE-gated section list and align rail/pane ordering tests. Use
the existing section event contract for all entry paths, including direct
shortcuts, the Settings gear's remembered section, and return from other routes.
A hidden Fleet section must not be reachable through a shortcut or restored
selection while EVE tools are hidden. Keep the existing backend refusal to hide
EVE tools when doing so would conceal required running-feature controls.

Change sharing's visibility predicate to the new section. Preserve serialized
watch admission, stale-reply protection, document visibility handling, and
existing state hydration. Section exit disables only view watching; it never
Stops a source or changes sharing participation. Opening Settings or changing
sections must not enqueue mutations, reset drafts, or create additional runtime
subscriptions. Keybind capture must disarm before keyboard use in the Fleet panel.

## 2. Current attempts and previous attempts

### Classification

Continue merging observations, local results, and pending commands by source ID
before deciding presentation. Each ID has one keyed row. Use a canonical lowercase
UUID as the case-insensitive presentation key across observations, local results,
pending commands, source-ID-bearing in-flight requests, and DOM reconciliation.
An uppercase ended observation and its lowercase pending Stop are the same
attempt: render one primary row and do not count it as history while pending.

This normalization is page-local identity matching, not a protocol change.
`protocol.uuid()` accepts and preserves casing (`wingman/fleetsharing/protocol.py`),
whereas `request_source_stop()` lowercases queued Stop IDs
(`wingman/fleetsharing/worker.py`). Do not rewrite payloads, signed bytes,
journal records, or backend identifiers to implement UI deduplication.

| Evidence for an attempt | Presentation |
| --- | --- |
| Server active, pending, paused, or any other non-ended state | Primary source list |
| Locally queued/persisted Start or Stop, even with an ended server observation | Primary source list until that operation settles |
| Local rejected/expired Start without a server observation | Visible local failure in the primary area, not server history |
| Server ended, with no locally pending operation | Previous attempts |

The UI must also retain a source while its explicit Start/Stop bridge request is
in flight, rather than allowing an intervening ended observation to hide it
before the command result is known. Any page-local request tracking is only
presentation state: it must not fabricate a source UUID, persist intent, or
replace worker command stages. An in-flight Start without a returned source ID
needs visible request feedback by its selected character until the real result
arrives. A page request finishing does not mean a worker-pending operation has
settled. Leaving and returning within the same connection binding must not lose
pending feedback. Connection changes invalidate identity-bound feedback as
described below.

### History disclosure

Place a native `<details>` after the primary source list, with a summary
**Previous attempts (N)**. Derive N from the actual rendered history rows, not
all source records or a hard-coded fixture count. This is the history reported
by the existing payload, not a promise of a complete archive.

- Initially collapsed; hidden when it contains no history.
- Preserve open/closed state during live updates and section re-entry.
- Show character identity, terminal state, and reported reason for each row;
  preserve the existing safe identity fallback when the character is unknown.
- Use text properties for external names/reasons, never injected HTML.
- No delete, reset, restart-history, or backend record removal action.
- Do not label records as latest, recent, or chronological without evidence.

### Ended-only, failed, empty, and unavailable states

Distinguish an untouched setup from one whose attempts ended. When no current
attempt exists but history does, keep a concise summary outside the collapsed
disclosure: **No current verification**, a breakdown of reported terminal
reasons, and a next action such as **Choose your current fleet boss, then Start
verification to try again**. Group repeated reasons rather than selecting a
supposed latest UUID. Do not characterize intentional `stopped` or `superseded`
ends as verification failures. Local rejected/expired Starts keep their specific
visible explanation and explicit retry guidance.

When a connection, owned character, or Fleet Read is missing, use the existing
prerequisite-specific guidance instead of implying Start is immediately usable.
When an authoritative source snapshot reports no attempts and there are no local
pending requests or results, retain a distinct first-use state. Unknown source
state is not an empty account. Preserve existing error reporting and fail-closed
mutation availability; do not reinterpret an unversioned failed read as a newer
successful snapshot.

#### Retention and connection identity

Retain known source/history rows across unavailable states and failed Refresh
only within the same `metadata.binding`. This is last-known presentation, not
current authorization or proof of current source state. Retained data must never
re-enable mutations, restore stale eligibility, or override current worker state.

Distinguish three transitions:

- **Failed read without a payload:** retain same-binding known rows and disclosure
  state; do not treat failure as a new successful observation.
- **Accepted payload with `sources: null`:** source state is unknown, including
  during a session reset that leaves the binding unchanged. Preserve same-binding
  rows as explicitly last-known, but show **Current source state unknown** rather
  than **No current verification**, even if all retained observations are ended.
  Merge current local pending commands/results for feedback without treating old
  observations as fresh acknowledgements or permission to retire pending work.
- **Accepted authoritative source snapshot, including an empty sources array:**
  replace the previous observed source set. An empty snapshot is not a failed
  read and must not preserve absent rows as current reported history. Local
  pending commands/results still participate in classification.

When `metadata.binding` changes, including disconnect/re-pair, discard retained
observations, keyed source/history rows, selected boss, and identity-bound
in-flight request feedback before presenting the new connection. Reset the
history disclosure for that connection. Invalidate old request generations so a
delayed response cannot repopulate the prior connection's rows or feedback after
navigation or re-entry. Preserve existing presentation-order and action-reply
guards. An ordinary same-binding session reset makes observations unknown, not a
new connection; keep only the last-known presentation allowed above. An identical
presentation order is not newer evidence, including delayed preference replies
and repeated pushes. Only newer evidence or a successful current watch read
clears failed-read state; a fresh successful Refresh may reuse an unchanged
presentation order.

This matches the worker's identity reset (which clears observations and local
results) and session reset (which clears observations even without a binding
change), and the existing page's binding-change invalidation. No persistent cache
or changes to worker reset behavior are introduced.

### Stable rows and keyboard focus

Maintain keyed rows across both primary and history containers. Reuse existing
nodes; do not rebuild the disclosure or move an already-correct row during a
heartbeat. Update history count and row text in place. Maintain selected boss,
character visibility edits, and pending sharing preference feedback.

When an operation settles and its focused row moves into collapsed history,
move focus to the visible history summary so focus is not stranded in hidden
content. If the history is open and the focused control remains applicable,
preserve it; if the settled action becomes unavailable, use the summary as the
fallback. Never steal focus when the affected row was not focused. Verify real
browser focus, not only node identity in a DOM double.

## 3. Copy and documentation

Update current user-facing Fleet setup directions from Settings → Previews to
Settings → Fleet telemetry. Known touchpoints include the EVE-tools refusal
message in `wingman/ui/api.py`, PRODUCT.md, DESIGN.md's Settings navigation and
lifecycle guidance, and Fleet entries in `docs/smoke-checklist.md`. Update relevant
placement comments and executable fixtures. Do not rewrite historical design
records under `docs/history/` or change unrelated Preview instructions.

The authGD checkout was located at `/home/tng/workspace/authGD`; initial search
found no matching Previews copy in that primary checkout. During implementation,
inspect its current upstream and repository instructions before locating the
actual guidance. If a correction is present, make it in a separate linked
worktree as a small copy-only patch. Preserve existing worktrees/local changes;
do not edit an old feature worktree merely because it contains the old wording.
Report a genuinely absent or inaccessible correction rather than inventing a
file or silently expanding into authGD behavior work. Do not deploy it.

## 4. Verification and acceptance

Extend existing executable JavaScript/DOM harnesses and Python regression tests,
not only lexical assertions. Cover:

- One active source plus two expired server-ended attempts: one primary row,
  two history rows, correct derived count, collapsed by default.
- Only ended attempts: visible terminal-reason summary and useful next action;
  intentional stopped state differs from failure and first use.
- Pending Start and Stop with stale ended observations, queued and persisted
  stages, delayed bridge replies, and transition to history after settlement.
- Local rejected/expired Start results remain visible without being invented
  as server history; IDs appearing in multiple payload collections render once.
  Include an uppercase ended observation with a lowercase pending Stop: one
  keyed primary row, zero history contribution, then one history row only after
  settlement. Apply the same case-insensitive matching to results and in-flight
  source-ID tracking.
- No-history, unknown-state, unavailable, and failed Refresh after a good payload;
  same-binding known rows, disclosure state, and relevant errors survive as
  last-known presentation without granting mutation authority.
- Same-binding session reset with `sources: null` preserves labelled last-known
  rows and shows unknown current state, even when only ended rows were known.
  A later authoritative empty snapshot removes absent observed history while
  retaining any current local pending commands/results.
- Binding changes invalidate cached rows, selection, disclosure state, and
  identity-bound request feedback. Delayed old-binding replies after section
  re-entry cannot restore stale data or clear the new connection's feedback.
- Keyed row identity, unchanged-heartbeat focus, selection, disclosure toggling,
  focus fallback on settlement, long names, and keyboard-only interaction.
- Entry/exit through the rail, Fleet shortcut, gear restoration, other routes,
  EVE-tools gating, document visibility, and delayed/out-of-order watch replies.
- No duplicate runtime subscriptions, section-induced Start/Stop/participation
  writes, lost in-flight preference feedback, or escaped Preview/Bookmark
  keybind capture.

Likely coverage homes: `tests/test_fleetsharing_page.py`,
`tests/test_fleetsharing_hydration.py`, `tests/fixtures/fleetsharing_page.cjs`,
Settings/Preview navigation tests, and existing Fleet API/runtime ownership tests.
Run relevant Python tests, `test_bridge_contract.py`, `test_page_conventions.py`,
and the executable JavaScript smoke gate. Run repository-wide Ruff lint and
format checks. If running the full Python suite, satisfy the Node and built
settings-codec prerequisites first; missing-native skips are not full coverage.

Keep all rendered fake data in `wingman/web/dev.js`. Open the actual dev page in
a browser at **840×625** and **839×621**. Exercise mixed and ended-only attempts,
pending operations, unavailable/failed reads, long names, disclosure keyboard
interaction, live-update focus, navigation, and EVE gating. Check horizontal
layout/overflow, scrolling, and access to all actions, not just a screenshot.

Report rendered browser evidence separately from actual Windows/WebView2
acceptance. DOM doubles and Chromium do not prove native keybind capture,
WinForms scaling, floating-window behavior, or the installed bridge lifecycle.
Keep the relevant Windows manual smoke checks explicitly open unless performed.

## Current verification status

Before implementation, in the new linked worktree, the unchanged focused
baseline passed:

```text
PYTHONDONTWRITEBYTECODE=1 /mnt/c/dev/flygd-wingman/.venv/bin/python -m pytest \
  tests/test_fleetsharing_page.py tests/test_fleetsharing_hydration.py \
  -q -p no:cacheprovider
13 passed in 5.64s
```

The independent second opinion (Claude Opus 5) returned **REVISE** with two
medium concerns: case-insensitive source identity and explicit retained-state
boundaries. Both were accepted by the user and incorporated into Classification,
Retention and connection identity, and the regression cases above. The reviewer
also reported **114 passing tests** across the Fleet page, hydration, and protocol
baseline. These baseline results predate this document-only revision; they do not
verify an implementation of the proposed behavior.

These are pre-implementation checks, not final verification. Implementation
results and remaining acceptance checks are recorded separately. The revised
document has not received a second review pass.
