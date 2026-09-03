# Profile Folder Management Design

## Purpose

Make the Profiles destination work from the EVE settings root instead of making a user manage one profile-directory path at a time. Keep the rarely changed server available as secondary context, make profile switching the prominent everyday control, and add safe whole-profile duplication within the selected server.

The feature supports two operations:

1. Create a new profile from the selected profile.
2. Replace an existing profile with an exact copy of the selected profile's recognized EVE settings files.

Replacement backs up the destination first and automatically rolls back a caught publication failure while Wingman remains alive. A hard kill or power loss relies on the durable backup instead. Both operations require EVE to be closed.

## Product fit

Profiles is occasional fleet-preparation work. A user should be able to choose the settings tree once, switch between profiles by name, and deliberately clone a known setup without returning to Explorer.

Server selection remains available because test servers and alternate shards are valid, but it is not the dominant control. Profile creation changes files only. Wingman does not edit EVE launcher configuration, activate a profile in EVE, or promise launcher behavior beyond creating a discoverable `settings_<name>` directory.

## Selected approach

Add a focused profile-copy operation under `wingman/evesettings/`. It owns profile-name validation, source and destination validation, staging, recognized-file replacement, and rollback. It is separate from the existing one-file copy loop because file-level atomicity does not provide an all-or-nothing profile operation.

`ui/api.py` retains ownership of cross-cutting Profiles behavior:

- the shared nonblocking mutation lock
- strict EVE-closed checks
- bounded worker-thread confirmation
- durable destination backup
- automatic-backup retention
- persisted server/profile selection
- semantic completion pushes and user-facing status

The rejected alternatives are:

- Generalizing backup restore into cloning. Existing archives record their original destination and are durable recovery artifacts; destination overrides would blur copy and restore authority.
- Extending the existing file-copy loop. A late failure could leave a mixed destination and require manual restoration, contradicting the selected rollback guarantee.

## Settings and compatibility

The persisted `eve_settings` shape remains:

- `root`: EVE settings root
- `server`: selected server directory
- `profile`: selected profile directory

Keeping all three fields avoids a settings-schema migration and preserves existing selection behavior.

Future explicit folder picks are canonicalized before they are saved:

- An EVE root is stored directly.
- A server folder is accepted, then lifted to its parent root while retaining that server selection.
- A `settings_<name>` folder is accepted, then lifted to its grandparent root while retaining its server and profile selections.

Existing installs may already have a server or profile directory stored in `root`. Discovery continues to normalize those values without writing settings merely because the route was opened. That normalization must not permanently force the profile named by a deep `root`: an explicit server/profile selection canonicalizes and saves `root`, `server`, and `profile` together under the mutation lock. A profile-copy request does the same canonicalization before any filesystem mutation and aborts untouched if that settings write fails. This gives legacy installs sibling-profile operations without a write-on-read migration.

Backup restore also derives and validates against the effective canonical root rather than the raw persisted `root`. This is required so a backup of a sibling profile created through the new operation remains restorable before the user makes another explicit selection.

Selection remains bridge-owned because changing server or profile rescopes the character/account roster, identity workflow, formations, backups, and subsequent filesystem validation.

## Profiles layout

The EVE settings context card becomes profile-first.

### Primary profile row

The primary row contains:

- a `Profile` label
- a wide `.field` dropdown showing friendly names such as `Default`, never full paths or the `settings_` prefix
- an adjacent ordinary `.btn` named **Copy profile…**

Changing the profile persists immediately, clears character/account target selections and completed-copy follow-up state, refreshes the roster, and resolves names through the existing flow.

### Secondary folder and server context

A quieter line beneath the profile row shows:

- the selected server as `<name> server`, for example `Tranquility server`
- the canonical EVE settings root
- **Change folder or server…**

That action expands the existing folder chooser, Detect action, and server dropdown. Server remains a separate selection but no longer competes visually with the everyday Profile control. Changing server clears stale target selection, refreshes its profile list, and chooses the first valid profile when the previous profile is unavailable.

The three-state EVE pill remains outside collapsible content so it cannot disappear with secondary setup controls.

## Inline Copy Profile flow

**Copy profile…** opens an inline disclosure anchored below the primary profile row. It keeps the source profile and selected server visible while the destination is chosen.

The disclosure shows `Copy <source>` and two `.radio` choices:

### New profile

This is the default mode. It contains:

- a free-text profile name
- an ordinary **Create copy** button
- inline validation status

The field commits only through **Create copy** or Enter, never on blur. Creating a profile does not require a second confirmation because it does not overwrite an existing profile.

After success, the new profile is selected, the disclosure closes, and the roster refreshes.

### Replace existing

This mode contains:

- a destination dropdown listing other profiles on the selected server and excluding the source
- an ordinary **Replace profile** button
- inline validation status

Replacement opens a bounded worker confirmation naming source and destination and stating that the destination will be backed up first. It is not styled `.danger`: a successful automatic backup and automatic rollback make it recoverable, matching the existing Restore treatment.

After success, the original source remains selected and the disclosure closes.

### Shared interaction behavior

**Cancel** closes the disclosure without changing profile state. A failed operation leaves the disclosure, selected mode, and entered destination intact so the user can correct or retry.

Both commit buttons remain ordinary `.btn` controls. **Copy to selected** remains the route's single accent action.

While a profile operation owns the mutation lock, profile, character/account copy, backup, restore, and formation mutation controls use the existing shared busy state. Navigation and the only route out remain available.

## Endpoint authority

The page sends intent, not arbitrary filesystem authority. The API receives the expected source-profile token shown by the page, the destination mode, and either a proposed friendly name or a selected destination-profile token. Under the mutation lock, Python rediscovers the current tree and derives:

- the effective canonical root
- the selected server
- the selected source profile
- the destination beneath that same server

The expected source must resolve to the freshly discovered selected profile. This closes the asynchronous gap between a page rendering one source and a separate profile-selection request completing. The operation rejects stale or fabricated values, source-equals-destination requests, and cross-server destinations.

Containment is checked at every resolved hierarchy edge, not only at the final file:

1. The freshly discovered server must either be a direct child entry that resolves beneath the canonical root or be the canonical root itself when discovery confirms that the root directly contains profiles.
2. Source and existing destination profiles must be direct discovered children and resolve beneath that server.
3. A proposed new destination must have that server as its direct lexical parent and resolve beneath it.
4. Every recognized source and destination file must be a direct entry and resolve beneath its own profile.

A server or profile junction that resolves outside its authorized parent is refused even when every later file is beneath that junction. Cross-server copying is not offered or accepted.

## New-profile names

Validation is authoritative in Python. JavaScript may provide immediate hints but cannot make a name valid.

A new friendly name is trimmed before validation, so surrounding spaces normalize away. The resulting name:

- contains 1 to 80 characters
- is entered without the `settings_` prefix
- contains no Windows-invalid filename characters or control characters
- has no path separator
- does not end with a space or period
- is not `.` or `..`
- is not a reserved Windows device name
- does not collide case-insensitively with an existing profile on the selected server

The destination directory is derived as `settings_<friendly name>`. Existing discovered profiles remain selectable even when a historical name would fail creation rules.

## Exact-copy semantics

“Exact copy” means the complete recognized EVE settings-file set:

- `core_char_<ASCII decimal id>.dat`
- `core_user_<ASCII decimal id>.dat`

Every recognized source file is copied byte-for-byte. Recognized files present only in an existing destination are removed. Unrelated files and directories in the destination are preserved and are not added to Wingman's backup format.

This definition keeps replacement fully recoverable through the existing profile backup format, which archives exactly the same recognized file domain.

## EVE-closed verification

The existing `list_clients(strict=True)` behavior is not sufficient for this operation: it raises when enumeration throws, but currently treats a missing window PID or an executable image that could not be queried as “not a client.”

The new flow uses an exception-preserving tri-state probe over EVE-titled windows:

- **closed:** every candidate was resolved and none belongs to `exefile.exe`
- **running:** at least one resolved candidate belongs to `exefile.exe`
- **unknown:** window enumeration, PID lookup, process opening, or image lookup failed for any EVE-titled candidate

Both **running** and **unknown** refuse the operation. **Unknown** dominates when one candidate is known to be running but another EVE-titled candidate cannot be resolved, preserving the fail-closed rule. The unknown message says Wingman could not verify that EVE is closed. Existing preview discovery and established Profiles writes retain their current behavior; only the new whole-profile flow consumes the fail-closed result.

## New-profile publication

Creation follows this order:

1. Rediscover and validate the expected source, selected server, and proposed name.
2. Canonicalize and persist any legacy deep root before touching profile files; abort if that write fails.
3. Verify through the tri-state probe that EVE is closed.
4. Create a uniquely named, non-discoverable staging directory beside the destination.
5. Copy and validate every recognized source file into staging.
6. Recheck that the destination still does not exist.
7. Rename staging into place.
8. Persist the new profile selection and refresh state.

Staging beside the destination keeps final publication on one filesystem. Its name uses a reserved Wingman prefix such as `.wingman-profile-copy-<uuid>.stage`, never `settings_`, so discovery cannot show crash debris as a profile. If copying or validation fails, staging is removed and no destination is created. If another actor creates the destination before publication, the operation refuses rather than changing it.

Filesystem publication and selection persistence are separate outcomes. If the profile is created but saving its selection fails, Wingman treats creation as successful, closes the disclosure, refreshes the list, retains the prior selection, and reports: `Created <name>, but Wingman could not remember the selection. Select it from Profile.` A retry must not imply creation failed or overwrite the colliding profile.

## Existing-profile replacement and rollback

Replacement follows this order:

1. Rediscover and validate the expected source and destination on the selected server.
2. Canonicalize and persist any legacy deep root before touching profile files; abort if that write fails.
3. Verify through the tri-state probe that EVE is closed.
4. Stage and validate the complete recognized source file set before touching the destination.
5. Ask for confirmation naming both profiles and the backup-first behavior.
6. Recheck through the tri-state probe that EVE is closed after confirmation.
7. Create the durable automatic backup of the destination. Backup failure leaves the destination untouched.
8. Publish the staged source set: replace matching files, add missing files, and remove recognized destination-only files.
9. If publication raises while the process remains alive, remove the partially published recognized set and restore from the durable backup.
10. Remove temporary staging material.
11. Apply automatic-backup pruning only after publication or rollback has settled.

Publication remains a sequence of per-file atomic replacements because unrelated destination entries must remain in place. “Automatic rollback” covers caught runtime failures while Wingman remains alive; it is not a claim of crash or power-loss atomicity. A hard kill during publication can leave a mixed recognized-file set, but the durable destination backup already exists and remains the recovery path.

All staging uses the non-discoverable `.wingman-profile-copy-<uuid>.stage` namespace. Normal completion removes it in `finally`. Before a new profile operation, Wingman removes abandoned staging directories from that namespace only after validating that each candidate is a direct child of the selected server and is not a discovered profile. A stage-shaped link, junction, or otherwise unvalidated candidate refuses the operation rather than being followed or silently ignored. Because the durable backup, rather than staging, owns rollback state, abandoned staging can be removed without discarding the recovery copy.

EVE can start after either probe. Per-file replacement failures remain part of the rollback path, and the user is told to close EVE before retrying. Strengthening every existing Profiles write to use this gate is out of scope.

## Error reporting

Failures distinguish the state left on disk:

- **Copy not started:** invalid name, collision, stale expected source, unreadable source, cross-server request, failed canonical-settings write, EVE running, or EVE status could not be verified.
- **Destination unchanged:** staging or durable backup failed before publication.
- **Created; selection not saved:** the new profile exists and is offered in the refreshed dropdown, but the prior profile remains selected.
- **Replacement failed; destination restored:** publication failed and automatic rollback from the durable backup succeeded.
- **Replacement and rollback failed:** the alert names the durable automatic backup and directs the user to Backups for recovery.
- **Interrupted by process termination or power loss:** automatic rollback is not claimed; the durable backup is the recovery path once publication had begun.

Detailed filesystem exceptions remain logged. User-visible messages state what happened and what to do, without raw Windows error codes when a specific instruction is available.

The existing `onEveSettingsDone` semantic event remains the sole completion push for Profiles mutations. Profile copy extends its payload with the operation identity, whether filesystem publication succeeded, and whether the new selection was persisted. This lets the page close the disclosure after successful creation even when remembering the selection failed, while final `eve_settings_state()` remains authoritative. No second competing completion handler is introduced.

## Accessibility and visual behavior

- Profile, server, destination, and name controls use associated `.lab` labels.
- New/Replace choices use the required `.radio` and `.ring` structure.
- All controls retain the shared visible `:focus-visible` treatment.
- Inline errors are associated with their field and do not rely on color alone.
- Empty profile and destination lists render disabled controls with actionable placeholders rather than blank working-looking dropdowns.
- The disclosure can be opened, completed, canceled, and retried with keyboard alone.
- Any selector that sets display and participates in `hidden` receives an explicit `[hidden]` override.
- The profile-first card and open disclosure fit at the 840×625 CSS floor without adding a nested scrollbar.

## Development harness

`wingman/web/dev.js` gains representative state and method stubs for:

- multiple profiles with `Default` selected
- the New profile disclosure
- the Replace existing disclosure
- invalid and colliding names
- an accepted busy operation
- successful creation selecting the destination
- successful replacement retaining the source
- refused EVE-running and rollback-failure outcomes

The harness fabricates display data only. Python remains authoritative for all validation and mutation decisions.

## Verification

### Automated

Add focused tests for:

- friendly profile names and stable ordering
- canonical persistence for root, server, and profile folder picks
- compatibility with legacy deeper `root` values without write-on-read migration
- explicit selection and profile mutation canonicalizing all three persisted paths together
- restore validating against the effective canonical root for a sibling-profile backup
- new-profile creation and final selection
- exact recognized-file copying
- preservation of unrelated destination entries
- case-insensitive collision detection
- Windows name validation, including reserved names and trailing spaces/periods
- stale expected-source, source-equals-destination, and cross-server refusal
- complete root → server → profile → file containment, including real Windows server/profile junctions
- non-discoverable staging names, abandoned-stage cleanup, and destination-race failures leaving no new profile
- tri-state EVE-running and unknown-process refusal, including native PID and executable-image lookup failures
- destination backup before replacement
- backup failure leaving the destination untouched
- publication failure with successful rollback
- rollback failure retaining a usable durable backup and producing the correct recovery message
- retention pruning after settled success or rollback, not before
- shared mutation-lock refusal and release on every completion path
- post-success selection rules for create and replace
- created-profile preservation and actionable reporting when selection persistence fails
- documented hard-kill boundary with the durable backup remaining recoverable
- bridge allowlist and Profiles completion-handler ownership
- profile-first DOM order, secondary server/folder treatment, inline disclosure states, one accent action, disabled placeholders, busy behavior, and `[hidden]` overrides
- `dev.js` method and scenario coverage
- package completeness for the new module within the existing `wingman.evesettings` package

### Manual

Update and exercise `docs/smoke-checklist.md` on Windows for:

- no folder, one profile, multiple profiles, and multiple servers
- selecting a root, server, or profile directory and seeing canonical context
- profile switching and route re-entry
- new profile creation and launcher/profile visibility
- replacement confirmation, success, and destination backup
- declined confirmation
- EVE-running and EVE-probe-failure refusal
- forced staging, backup, publication, and rollback failures where practical
- source selection after replacement and destination selection after creation
- keyboard-only use and focus behavior
- 840×625 at 100% and 200% display scaling
- long valid profile names and long canonical paths

The full Python suite, Ruff lint, and Ruff format checks remain required before completion. The web page still requires a real Windows smoke pass because repository tests do not execute JavaScript.

## Out of scope

- Copying profiles across servers
- Copying unrelated files or nested directories
- Changing the profile backup archive domain or format
- Editing EVE launcher configuration or activating a profile in EVE
- Deleting or renaming profiles
- Adding granular copy-progress events
- Automatic rollback after a hard kill or power loss; the durable backup remains the recovery path
- Tightening EVE-closed behavior for existing character/account copy, backup, restore, or formation operations
- Redesigning the character/account copy workflow
