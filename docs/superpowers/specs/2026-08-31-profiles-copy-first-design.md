# Profiles Copy-First Design

## Purpose

Make copying EVE settings the clear primary task of Profiles. Move backup administration and probe formation editing into focused Profiles-owned subroutes without misclassifying either feature as application configuration.

The change also makes account targets recognizable, clarifies bulk-selection scope, and keeps copy progress and completion feedback beside the action that produced it.

## Product fit

Profiles is occasional fleet-preparation work. Users open it to copy a known setup onto known characters or accounts. The route should optimize that task rather than present copying, recovery administration, and formation editing as equal stages in one long page.

Backups and formations remain under Profiles rather than moving to Settings:

- Backups are recovery artifacts created by profile operations.
- Probe formations are profile content that users create and edit.
- Neither configures persistent Wingman behavior.

This preserves the product rule that destinations are places where users do work, while Settings contains configuration.

## Information architecture

### Profiles route

The primary route contains:

1. A compact profile context area with the EVE folder, server, profile, running state, and **Change…** action.
2. A quiet tool row containing **Manage backups…** and, when available, **Edit probe formations…**.
3. The Copy EVE Settings workflow.

The current Backups and Probe Formations cards leave the primary route.

### Profiles-owned subroutes

Add a focused Backups subroute alongside the existing Account Identity and Formations subroutes. All three are chromeless child routes of Profiles:

- The Profiles title-bar destination remains selected.
- **‹ Profiles** is the clear exit.
- Visiting Settings and returning resolves to Profiles, not a hidden child route.
- Disabling EVE features removes every route into these screens.

The title bar gains no destination.

## Profiles layout

### Profile context

Replace the narrow folder card with a compact context treatment that uses the available horizontal space. It shows:

- Selected profile name
- Server
- EVE settings root
- Three-state EVE status
- **Change…**

The secondary-tool row sits immediately below this context. It is outside the copy card so Backups and Formations remain discoverable without appearing to be copy steps.

The Formations entry is hidden when the decoder or account data is unavailable, preserving current behavior.

### Copy workflow

The workflow keeps its existing order:

1. Characters or Accounts mode
2. Source
3. Groups to copy
4. Target filter and bulk controls
5. Targets
6. Copy action and result

The explanatory copy must preserve the distinction between recognized groups and all other keys. Selective copy starts from the complete source and restores each unchecked recognized group from the target; settings outside those groups still come from the source. Use:

> Checked groups are copied as a unit. Unchecked groups stay unchanged. Everything else is copied.

This is a wording change only. Selective-copy semantics remain unchanged.

The backup promise remains beside the copy action and continues to use the existing shared, payload-derived sentence:

> Every copy backs up what it is about to overwrite.

`evesettings.js` remains responsible for deriving the full `auto_keep`-aware retention note and painting both its compact promise on Profiles and its complete explanation in the Backup manager. Do not introduce a second hand-maintained backup promise.

### Bulk-selection language

Rename:

- **Select all** to **Select shown**
- **Clear** to **Clear selection**

`Select shown` continues to act only on targets visible after filtering. Hidden selections do not become copy targets. `Clear selection` clears all selected targets.

The action button includes the effective quantity and mode:

- **Copy to 1 character**
- **Copy to 12 characters**
- **Copy to 1 account**
- **Copy to 4 accounts**

The adjacent consequence text remains explicit: `4 accounts will be overwritten`.

## Account recognition

Accounts mode shows an identification summary before source and target selection:

> **1 of 10 accounts identified**
> Identify accounts to replace internal IDs with names.

The existing **Identify accounts…** action remains the route into the Account Identity flow.

Account display identity remains owned by `evesettings.identity.account_identity()`, not reconstructed in JavaScript. Persisted settings require every character association to belong to a named account, and the live endpoint enforces the same invariant. The UI therefore supports two reachable states:

- Named account: account name is primary; linked-character summary and `Account <id>` are secondary.
- Unidentified account with neither a name nor confirmed links: `Account <id>` is primary; `Not identified` is secondary.
- A bare numeric identifier is never the only visible label.

Its `option` value must continue to derive from the same primary and secondary strings. This intentionally updates source options, target rows, Confirm Copy labels, and formation account choices.

Backup rows use a separate `_eve_backup_identity()` path. Update it to preserve the canonical account identity's primary and secondary strings instead of replacing the secondary value with another `Account <id>`. This prevents duplicate IDs for unidentified accounts and keeps all account surfaces aligned. Python tests in `tests/test_evesettings_identity.py` and `tests/test_api_evesettings.py` must pin both reachable states and their downstream representations.

Unidentified accounts remain usable. Identification is encouraged but not required. The summary is absent in Characters mode.

The **Identify accounts…** action is offered only when the selected profile contains at least one account file and one character file, which are the backend's preconditions for starting identification. Otherwise Accounts mode shows guidance naming the missing discovery state:

- No accounts: `No accounts found in this profile. Launch a character, make a small settings change, then close EVE completely.`
- No characters: `No characters found in this profile. Launch a character, make a small settings change, then close EVE completely.`

The source remains disabled when its corresponding list is empty.

## Copy lifecycle feedback

The backend currently reports operation acceptance and final completion, not per-target progress. This design does not add granular progress events.

Before starting, the page captures that a copy is the pending operation. From worker acceptance through the EVE-running check and confirmation, the primary button uses neutral wording:

- `Copy operation in progress…`

It must not claim that copying has begun while the worker may still refuse the operation or the user may cancel confirmation. Controls continue to use the existing shared busy state and mutation lock.

Python's existing `format_eve_copy_done()` and global status strip remain the sole owner of the successful quantity and outcome. The page does not infer how many backups Python created and does not repeat the global success sentence. After complete success, it shows a quiet local follow-up beside the reset action:

> Copy complete. **View backups**

This follow-up is not a second live announcement. **View backups** opens the Backups subroute with the newest entries visible. The follow-up survives that round trip back to Profiles for the current session, then clears when the source, mode, server, profile, or root changes or another copy begins.

On partial or complete failure, the existing detailed error path remains authoritative. No local success follow-up is shown. Selection clears only after complete success, preserving current behavior.

## Backup manager

### Structure

The Backups subroute contains:

1. **‹ Profiles** and the Backups heading
2. **Back up <profile> profile** as the single accent action
3. A concise automatic-retention summary
4. A text filter
5. A **Retention…** disclosure
6. The backup list
7. Batched **Show 20 older backups** disclosure

The route uses the existing page scrollbar. It does not introduce a nested list scrollbar.

### Filtering

Filtering is client-side and matches the metadata already in the Profiles state payload:

- Resolved target name
- Target identifier or metadata
- Character, account, or profile kind
- Automatic or manual origin

No new persisted search state is introduced. Origin matching accepts both the stored tokens (`auto`, `manual`) and the rendered terms (`Automatic`, `Manual`) so the visible vocabulary works in the filter.

When no rows match, show `No backups match this filter` with **Clear filter**. When no backups exist at all, explain that copies create backups automatically and keep the manual profile-backup action available. An unreadable backup directory retains the existing actionable error.

### Rows and actions

Rows retain date, target identity, and origin. Restore remains directly visible because it is the primary purpose of the archive.

Delete moves into an accessible per-row overflow disclosure to prevent repeated destructive controls from dominating the list. This is a purpose-built `details`/`summary` row control styled with the existing menu tokens, not a claim that the uploader's pointer-owned `#ctxmenu` already supplies reusable keyboard behavior. The disclosure:

- Has an accessible trigger name containing the target and timestamp.
- Opens with pointer, Enter, or Space through native summary behavior.
- Closes on Escape through a scoped key handler.
- Returns focus to its summary trigger when closed.
- Closes other open row disclosures before opening.
- Retains the existing destructive confirmation.

The design does not group backups into copy events. Current backup metadata has no operation identifier, and grouping by approximate timestamps would be unreliable.

### Retention

**Retention…** reveals the current numeric control and **Apply** action inline. Lowering retention keeps the existing confirmation and continues to state the exact number of automatic backups that will be deleted. Manual backups remain exempt.

Restore, Delete, manual backup, and retention controls remain disabled while another Profiles mutation or account-identification operation owns the lock. Filtering, disclosure navigation, route exit, and pagination remain available so the user can inspect the archive while a mutation runs.

## Formation editor

Remove the Probe Formations card and account selector from the Profiles route. **Edit probe formations…** opens the existing two-pane editor directly.

Move the account selector into the formation rail above the formation list. `evesettings.js` already owns the Profiles state containing account paths and shared display identities; it passes that account list and a preferred path to `WM.openFormations(accounts, preferredPath)`. `formations.js` owns the session-only selected path and renders the supplied labels without reconstructing account identity.

Entry behavior is:

1. Reuse the last account selected during the current session when it still exists in the supplied list.
2. Otherwise select the preferred or first available account.
3. Load that account immediately.

Switching accounts with clean state loads the selected account. Switching with unsaved edits asks whether to discard them:

- Confirming discards edits and loads the new account.
- Cancelling restores the previous account selection and keeps all edits.

Failure behavior distinguishes two cases:

- An initial entry load has no previous editor state to preserve. It retains the existing behavior: route back to Profiles first, then explain the failure over the screen that offered the action.
- A switch from an already loaded account keeps the previous editor state, restores the previous selector value, and explains the failure without leaving the editor.

The selector and mutation controls are disabled while saving. No new persisted preference is introduced.

Formation validation, ID stability, unit conversion, preview behavior, save behavior, and the shared mutation lock remain unchanged.

## Error handling and state ownership

- `evesettings.js` continues to own the Profiles state, the Profiles route, and the new Backups subroute. It renders backup state and starts backup mutations from both surfaces.
- `evesettings.js` remains the only module that registers `onEveSettingsDone`. The handler continues forwarding formation completions to `WM.formationsDone`; the Backups subroute must not register a second handler.
- The page remains responsible for selection, filters, disclosure state, neutral local busy labels, and the non-authoritative local **View backups** follow-up.
- Python remains responsible for filesystem validation, containment, EVE-running enforcement, backup-first mutation, pruning, formation validation, successful-copy quantities, and user-facing operation errors.
- Workers continue to communicate through semantic bridge events and never touch the page directly.
- Existing confirmation mechanisms remain unchanged. Opening the page-owned backup disclosure needs no confirmation; its Delete action invokes the existing worker-owned bounded confirmation path.
- Any new bridge handler must be added to `WM.HANDLERS`, registered by the owning module, and covered by the lexical contract tests.

## Accessibility

- Existing `.check` and `.radio` wrappers remain mandatory.
- Every interactive control retains a visible `:focus-visible` state.
- Account identification uses text as well as visual hierarchy.
- Copy completion continues to use the existing global live status region. The local **View backups** follow-up is not another live region.
- Backup disclosure triggers include the affected backup in their accessible names.
- Disclosure state, keyboard dismissal, and focus restoration do not depend on pointer input.
- The main route and both subroutes remain usable at the 840×625 CSS floor and at 200% Windows display scaling.

## Verification

### Automated

Add or update coverage for:

- Backups route mapping, Profiles title-bar ownership, and last-destination behavior
- EVE feature-gate removal of every Profiles-owned route
- Backup-route enter and leave behavior
- Backup filtering, clear-filter behavior, unreadable state, and empty state
- Accessible backup-disclosure labels, one-open-at-a-time behavior, Escape dismissal, and focus return
- Dynamic copy labels for singular and plural characters and accounts
- Neutral copy busy state before confirmation, global success ownership, local follow-up, partial failure, and complete failure
- Persistence of the local follow-up across a Backups round trip and clearing it when context changes
- Named and unidentified account rendering in `tests/test_evesettings_identity.py`
- Canonical account identity in source options, target rows, confirmations, and formation choices
- Named and unidentified account backup identities in `tests/test_api_evesettings.py`
- No-account and no-character guidance, with identification unavailable when its backend preconditions are absent
- Formation account-list handoff and selection on entry
- Clean account switching
- Dirty switching with confirm and cancel outcomes
- Failed account loading without state loss
- Existing bridge allowlist, pywebview public-attribute, backup, selective-copy, and formation invariants
- `tools/shoot_screens` coverage for the Backups route, or a documented exclusion if the route cannot be captured independently
- `dev.js` fixtures for the Backups route, account-label states, copy busy and follow-up states, and formation account switching
- Backup filtering against both stored origin tokens (`auto`, `manual`) and rendered terms (`Automatic`, `Manual`)

### Manual

Exercise the Profiles section of `docs/smoke-checklist.md`, adding checks for the new Backups route and formation account selector. Verify:

- Character and account modes
- No folder, one profile, multiple profiles, and no accounts
- Identified and unidentified accounts
- Empty, unreadable, filtered, and long backup lists
- Manual backup, restore, Delete, and retention reduction
- Formation switching with clean and dirty state
- Successful, partially failed, and refused copy operations
- Keyboard-only operation and focus return
- The 840×625 floor at 100% and 200% display scaling
- A wide window with long names and paths

## Out of scope

- Moving profile tools into Settings
- Adding another title-bar destination
- Persisting the last formation account across application restarts
- Adding per-target copy progress events
- Changing backup file format or adding operation identifiers
- Grouping backups by inferred timestamps
- Redesigning the formation editor itself
- Changing copy, restore, pruning, or validation semantics
