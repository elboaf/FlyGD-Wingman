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

The explanatory copy becomes:

> Checked groups are copied. Unchecked groups stay unchanged.

The backup promise remains beside the copy action:

> Every overwrite is backed up first.

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

Account labels follow these rules:

- Identified account: account name is primary; `Account <id>` is secondary.
- Unidentified account: `Account <id>` is primary; `Not identified` is secondary.
- A bare numeric identifier is never the only visible label.

Unidentified accounts remain usable. Identification is encouraged but not required. The summary is absent in Characters mode.

If there are no accounts, the page explains how to make them discoverable rather than presenting an inert identification or source control.

## Copy lifecycle feedback

The backend currently reports operation acceptance and final completion, not per-target progress. This design does not add granular progress events.

Before starting, the page captures the effective target count and noun. While the worker runs, the primary button reads:

- `Copying to 3 accounts…`

Controls continue to use the existing shared busy state and mutation lock.

On complete success, a persistent local status region beside the action reads:

> **Copied to 3 accounts.** Three backups created. **View backups**

The result uses `role="status"`. **View backups** opens the Backups subroute with the newest entries visible.

On partial or complete failure, the existing detailed error path remains authoritative. No success result is shown. A new source, mode, selection context, server, profile, or root clears a stale result.

Selection clears only after complete success, preserving current behavior.

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

No new persisted search state is introduced.

When no rows match, show `No backups match this filter` with **Clear filter**. When no backups exist at all, explain that copies create backups automatically and keep the manual profile-backup action available. An unreadable backup directory retains the existing actionable error.

### Rows and actions

Rows retain date, target identity, and origin. Restore remains directly visible because it is the primary purpose of the archive.

Delete moves into an accessible per-row overflow menu to prevent repeated destructive controls from dominating the list. The menu:

- Uses the existing context-menu vocabulary.
- Has an accessible trigger name containing the target and timestamp.
- Supports keyboard opening and Escape dismissal.
- Returns focus to its trigger when closed.
- Retains the existing destructive confirmation.

The design does not group backups into copy events. Current backup metadata has no operation identifier, and grouping by approximate timestamps would be unreliable.

### Retention

**Retention…** reveals the current numeric control and **Apply** action inline. Lowering retention keeps the existing confirmation and continues to state the exact number of automatic backups that will be deleted. Manual backups remain exempt.

Restore, Delete, manual backup, retention, and pagination controls remain disabled while another Profiles mutation or account-identification operation owns the lock.

## Formation editor

Remove the Probe Formations card and account selector from the Profiles route. **Edit probe formations…** opens the existing two-pane editor directly.

Move the account selector into the formation rail above the formation list. Entry behavior is:

1. Reuse the last account selected during the current session when it still exists.
2. Otherwise select the first available account.
3. Load that account immediately.

Switching accounts with clean state loads the selected account. Switching with unsaved edits asks whether to discard them:

- Confirming discards edits and loads the new account.
- Cancelling restores the previous account selection and keeps all edits.

A failed account load keeps the previous editor state and explains the failure. The selector and mutation controls are disabled while saving. No new persisted preference is introduced.

Formation validation, ID stability, unit conversion, preview behavior, save behavior, and the shared mutation lock remain unchanged.

## Error handling and state ownership

- The page remains responsible for selection, filters, disclosure state, local busy labels, and local success feedback.
- Python remains responsible for filesystem validation, containment, EVE-running enforcement, backup-first mutation, pruning, formation validation, and user-facing operation errors.
- Workers continue to communicate through semantic bridge events and never touch the page directly.
- Existing confirmation mechanisms remain unchanged. Page-owned menu actions use `WM.confirm`; worker-owned destructive operations use the existing bounded Python confirmation path.
- Any new bridge handler must be added to `WM.HANDLERS`, registered by the owning module, and covered by the lexical contract tests.

## Accessibility

- Existing `.check` and `.radio` wrappers remain mandatory.
- Every interactive control retains a visible `:focus-visible` state.
- Account identification uses text as well as visual hierarchy.
- Copy completion uses a persistent live status region.
- Backup menu triggers include the affected backup in their accessible names.
- Menu state, keyboard dismissal, and focus restoration do not depend on pointer input.
- The main route and both subroutes remain usable at the 840×625 CSS floor and at 200% Windows display scaling.

## Verification

### Automated

Add or update coverage for:

- Backups route mapping, Profiles title-bar ownership, and last-destination behavior
- EVE feature-gate removal of every Profiles-owned route
- Backup-route enter and leave behavior
- Backup filtering, clear-filter behavior, unreadable state, and empty state
- Accessible overflow-menu labels and keyboard behavior
- Dynamic copy labels for singular and plural characters and accounts
- Copy busy, success, partial-failure, and complete-failure states
- Clearing stale copy results when context changes
- Identified and unidentified account rendering
- Formation account selection on entry
- Clean account switching
- Dirty switching with confirm and cancel outcomes
- Failed account loading without state loss
- Existing bridge allowlist, pywebview public-attribute, backup, selective-copy, and formation invariants

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
