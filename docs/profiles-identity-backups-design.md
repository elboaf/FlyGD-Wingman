# Profiles identity and backup safety

Design brief. Base: `main` (`652dceb`), 2026-09-01.

## Outcome

Profiles must identify every source, target, and backup in human terms before
the user copies or restores EVE settings. Wingman will add account aliases,
confirmed account-to-character associations, guided account identification,
resolved backup labels, a full-width backup history, and visible automatic
backup retention.

This work closes two related P1 findings:

1. Account and backup rows expose numeric storage identities where choosing the
   wrong item can overwrite live settings.
2. The Backups card compresses that identity into a narrow, internally
   scrolling list while leaving useful page width empty.

The work is one safety change, not two cosmetic changes. The page must make the
object of an operation recognizable before it asks for confirmation.

## Product and design direction

- **Register:** product.
- **User:** an EVE multiboxer preparing several clients, usually focused on
  avoiding an expensive settings mistake rather than learning EVE concepts.
- **Primary action:** recognize exactly which account, character, profile, or
  backup an operation will affect.
- **Color strategy:** restrained. Use Wingman's existing tokens and component
  vocabulary; identity and layout, not decoration, carry the hierarchy.
- **Physical scene:** a multiboxer prepares several EVE clients on a dark
  secondary monitor and needs to distinguish similar accounts without leaving
  the task.
- **Reference surfaces:** the existing Profiles controls, the Uploader's
  full-width list treatment, and conventional account-management identity rows.
- **Scope:** production-ready behavior, persistence, bridge methods, page
  changes, automated tests, and Windows smoke coverage.

No new title-bar destination or modal-first flow is introduced. Account
identification is a focused sub-screen of Profiles.

## Confirmed constraints

### EVE does not provide account names here

`core_char_<id>.dat` identifies a character. Wingman resolves that public
character ID through ESI. `core_user_<id>.dat` carries an internal EVE account
ID, but neither its filename nor its decoded document provides the launcher
login name or an account-to-character roster. `docs/history/eve-settings-design.md`
already records account aliases as deferred work and calls numeric account
labels a known rough edge.

An account name or association is therefore Wingman-owned local metadata. It
must never be presented as data read from EVE.

### Timestamps are evidence, not identity

Filesystem timestamps cannot safely create permanent associations by nearest
match. EVE sessions, multibox client shutdown, Wingman copies, restores, and
profile-wide operations can produce clustered or identical modification times.
A timestamp comparison is useful only inside a controlled, explicit
before-and-after workflow followed by user confirmation.

### Existing backup compatibility must survive

Backup filenames are the listing index. `enumerate_backups()` deliberately does
not open every archive, and the manifest remains authoritative for restore.
Existing archives encode enough in `kind` and `stem` to resolve a character ID,
account ID, or profile name without changing their format.

### Automatic and manual retention differ

Wingman already keeps the newest `auto_keep` automatic backups independently
for each `(kind, source profile, target stem)` group. Manual backups are never
pruned. Copy, restore, and formation saves already invoke pruning. This design
exposes and strengthens that policy; it does not replace it with one global
history limit.

### Rendering remains manually verified

The test suite reads web source lexically but does not execute or render the
page. Bridge contract tests, source tests, and a Windows pass through
`docs/smoke-checklist.md` are all required.

## Identity model

Persist two mappings under the existing `eve_settings` settings section:

```json
{
  "account_aliases": {"19191934": "Main multibox"},
  "account_characters": {"19191934": ["2115754172", "2115754173"]}
}
```

`settings.validated_eve_settings()` owns both defaults and validation, so old
settings documents acquire empty mappings through the existing normalization
path rather than a separate migration.

IDs are stored as decimal strings. Values loaded from `settings.json` are
validated defensively:

- reject non-decimal or empty IDs;
- trim aliases and enforce a documented length limit;
- discard malformed collection members without discarding valid siblings;
- deduplicate character IDs;
- ensure one character is associated with at most one account.

Associations are local metadata only. They must not alter EVE files, backups,
ESI state, or the launcher. They persist across settings profiles so the same
account remains recognizable when the user switches from Default to Alt.

If a manual edit moves a character to another account, the new confirmed
association wins and the old one is removed. The UI must state this before the
move is committed.

## Human-readable account labels

Account controls use a primary human label and retain the raw account number
without repeating an `ID` label the surrounding Accounts context already
provides.

| Known data | Primary label | Secondary metadata |
|---|---|---|
| Alias and characters | `Main multibox` | `Aiga Otsolen + 2 · 19191934` |
| Characters only | `Aiga Otsolen + 2` | `19191934` |
| Alias only | `Main multibox` | `19191934` |
| Neither | `19191934` | none |

`+ N` counts only other confirmed associations. Wingman must not imply that it
knows the complete launcher roster.

Native select options cannot render two lines, so source and formation account
pickers use a flattened form:

- `Main multibox · Aiga Otsolen + 2 · 19191934`
- `Aiga Otsolen · 19191934`
- `19191934`

The label producer belongs in Python. Source lists, target rows, formation
account selection, copy confirmations, completion or error text, and backup
rows must not maintain separate account-label logic. This deliberately changes
the existing account `name` payload from `Account <id>` and requires the
corresponding `test_api_evesettings.py` expectations to change with it.

`#es-source` already takes the available row width. The formation account
selector must be widened from the shared 150px select default so its chosen
identity remains readable. Native option labels stay compact and put the human
label first; the full two-line identity remains visible in account management
and target rows.

Character labels retain the existing ESI name with `Character <id>` as the
offline or unresolved fallback.

## Guided account identification

Accounts mode gains a plain `.btn` labelled **Identify accounts…**. It is
hidden in Characters mode and opens the chromeless `accountidentity` sub-screen
of Profiles. The copy card remains a copy form; no management panel expands
between its mode switch and source picker. The trailing ellipsis is intentional
because the button opens the focused flow.

### Start

The opening state says:

> EVE stores account settings under a number, not a name. Wingman can match that
> number to a character by watching which settings change together.

Before the action, it says to close every EVE client and explains that one
character will be launched after identification starts. **Start identification** records a
snapshot of every account and character file in the selected server and
profile. The snapshot includes path, size, and high-resolution modification
time so a same-size rewrite still counts and an unchanged file does not.

Starting identification does not write any EVE or Wingman setting.

### Observe

After the snapshot, show:

> Launch one character, enter the game, then close that client. Keep other EVE
> clients closed.

Actions are **Check changes** and **Cancel**. The workflow does not poll. A
check compares the current discovery result with the snapshot.

While identification is active, Profiles actions that mutate EVE settings are
disabled: copy, restore, delete backup, create backup, formation editing, and
retention changes. This prevents Wingman's own writes from contaminating the
observation. The backend enforces the same exclusion, so a direct or stale page
call cannot bypass the disabled controls.

Start, check, and cancel are request/response bridge methods named
`eve_settings_identification_start`, `eve_settings_identification_check`, and
`eve_settings_identification_cancel`. They perform the same bounded directory
scan and file-stat class of work already accepted in `eve_settings_state`, so
they run on the bridge thread and return semantic state directly. They do not
add a Python push or a `WM.HANDLERS` entry.

Leaving the `accountidentity` sub-screen sends
`eve_settings_identification_cancel`; changing root, server, or profile also
cancels the Python-owned snapshot. The sub-screen follows Probe Formations'
route pattern: the title-bar destinations are hidden and `‹ Profiles` is the
explicit way back. Starting identification is refused
while `_eve_mutation` is held, and `_eve_begin` refuses every EVE mutation
while an identification snapshot exists. This mutual exclusion is enforced in
Python as well as painted in the page.

### Candidate rules

- Exactly one account and one character changed: propose that pair.
- Exactly one account and several characters changed: show the changed
  characters and require the user to choose one manually.
- No account or no character changed: do not propose a link.
- More than one account changed: do not guess. Ask the user to close other EVE
  clients and restart identification.
- A file added after the snapshot counts as changed.
- A file removed, an unreadable directory, a changed server/profile selection,
  or a changed EVE root invalidates the session rather than producing a
  candidate.

The candidate names both objects and requires **Link character**. Confirmation
creates only the selected association; it never adds every character that
happened to change. Completion says which character was linked to which account
number and makes **Back to Profiles** the primary next action.

Suggested failure copy:

- No useful pair: `No account and character changes were found. Close the client fully, then check again.`
- Several accounts: `More than one account changed. Close the other EVE clients and start again.`
- Folder changed: `The selected EVE profile changed. Start identification again.`

### Manual identity management

A secondary **Manage names and character links…** disclosure on the sub-screen
lets users:

- add or edit an account alias;
- associate additional discovered characters with an account;
- remove a confirmed association;
- move a character from one account to another after explicit confirmation.

These use synchronous request/response methods
`eve_settings_set_account_alias` and `eve_settings_set_account_characters`.
Python validates and persists the complete value, returns the standard
`{applied, persisted, error}` shape, and the page refetches state after an
applied change. Moving a character is confirmed by the page through
`WM.confirm` before sending the new complete association set. No new push
handler is required.

Removing or moving an association changes Wingman's labels only. It does not
remove a character or modify EVE settings.

## Backup target labels

The backup payload gains a display target assembled from the parsed backup
kind and stem. Character and account IDs are recovered only from the exact
`core_char_<digits>` and `core_user_<digits>` stem forms produced by
`create_file_backup`; `_sanitize()` is otherwise lossy, so any non-matching
legacy stem falls back unchanged rather than being partially interpreted:

- character backup: resolved ESI name, falling back to `Character <id>`;
- account backup: alias and confirmed-character summary, falling back to the
  account number;
- profile backup: the profile name already encoded in the stem.

Raw identity remains available as secondary text:

- `Character 2115754172`
- `Account 19191934`
- `Profile`

Old archives require no migration. If a stem is malformed or predates a known
shape, show the existing stem rather than inventing a human label. A deleted
alias or association immediately changes the displayed backup label because
labels are resolved from current local metadata, while the archive's restore
target remains unchanged.

The restore confirmation must use the same display label shown in the row and
must name the backup date. The confirmation still explains that current
settings are backed up before restore and that a whole-profile restore removes
files absent from the archive.

## Backup layout

The Backups card uses the same available width as the Copy EVE settings card.
It no longer has an inner scrollbar. The Profiles route remains the single
scroll owner.

Use one aligned header and row grid:

| Date | Target | Origin | Actions |
|---|---|---|---|
| UTC date and time | Human label plus secondary raw identity | `Automatic` or `Manual` | `Restore`, `Delete` |

Requirements:

- Target receives the flexible track and the most width.
- Date and Origin remain scannable fixed or bounded tracks.
- Actions align to the right edge.
- Long aliases and character names truncate only after the raw identity remains
  available through accessible text and a tooltip.
- Column headers use the same row padding and tracks as their data.
- At the 840 CSS-pixel floor, identity remains readable and actions do not wrap
  into an ambiguous order.

Render the newest 20 backups initially. If more remain, show **Show 20 older
backups** after the rows. Each activation reveals the next 20 from the complete,
newest-first backup array already held by the page; `eve_settings_state()` must
continue returning all backups rather than pre-slicing them. The control does
not re-query or reorder the list and disappears when all entries are visible.

Empty and unreadable states retain their current distinction. An unreadable
backup folder must never render as `No backups yet.`

## Profile backup action

The manual profile backup button includes the selected profile name:

- `Back up Default profile`
- `Back up Alt profile`

When no profile is selected it reads `Back up profile` and is disabled. The
confirmation, completion status, and errors name the selected profile where
that context changes the user's decision.

## Automatic backup retention

Expose the existing `auto_keep` value in the Backups card:

**Automatic backups to keep per item**

`[10] [Apply]`

**Apply** uses the ordinary `.btn` treatment. `Copy to selected` remains the
route's only accent button.

Supporting copy:

> Applies separately to each character, account, and profile. Manual backups
> are always kept.

The input accepts integers from 1 through 100, matching current settings
validation. It does not save on blur. Enter and **Apply** submit the value.

### Applying a retention change

`eve_settings_set_auto_keep` validates the raw value synchronously before
starting a worker. An invalid or busy request returns
`{accepted: false, value: <persisted value>, error: <specific message>}`, which
lets the page restore the authoritative value and explain the refusal inline. A
valid request claims the existing mutation lock, starts the retention worker,
and returns `{accepted: true, value: <current value>, error: null}`; completion
still arrives through `onEveSettingsDone`.

The backend computes the actual prune set using the same grouping and ordering
as `backup.prune`; the page never reproduces retention logic.

- Invalid value: refuse it inline and restore the last applied value.
- Higher or unchanged value: persist without deleting anything.
- Lower value with no excess files: persist without confirmation.
- Lower value with excess files: confirm with the exact deletion count, for
  example:

> Keep 3 automatic backups per item? This will permanently delete 47 older
> automatic backups. Manual backups will be kept.

Persisting the new value and pruning happen in one worker under the existing
EVE mutation lock. The page may perform advisory input checks but treats the
endpoint's returned value and the refreshed state as authoritative. It waits
for worker completion before committing a valid request's displayed value.

The existing `onEveSettingsDone` push remains the sole mutation-completion
handler. No new push is added: a rejected or failed retention change sends
`ok: false`, the normal refresh restores the persisted value, and an applied
change sends `ok: true`. A partial prune sends `ok: true` because the retention
setting was persisted, raises a warning naming the number of files that could
not be deleted, and leaves those files eligible for a later prune.

To support truthful partial results, `backup.prune()` changes from returning a
list of deleted paths to a `PruneReport` carrying `deleted` and `failed`
outcomes. Existing copy, restore, and formation callers may ignore successful
deletions but must surface failures rather than swallowing them. A persistence
failure prunes nothing. A declined or timed-out `_eve_confirm` changes nothing.

Existing pruning after copy, restore, and formation saves remains. Opening
Profiles alone never deletes files.

## Interaction and state ownership

Python owns:

- validation and persistence of aliases and associations;
- the account display-label representation;
- identification snapshots and candidate classification;
- backup target resolution;
- retention validation, prune preview, mutation, and failure reporting.

The page owns:

- whether the secondary names-and-links disclosure is expanded;
- the currently visible batch of backup rows;
- filter and selection state that changes only what is drawn;
- rendering backend-provided labels and semantic states.

Identification session state is ephemeral and scoped to the selected root,
server, and profile. It is not written to `settings.json`. Associations and
aliases cross the bridge because they change labels Python computes.

This design adds bridge methods but no new Python push names. Identification
and identity-management methods return their semantic results directly;
retention reuses `onEveSettingsDone`. If implementation introduces any push
instead, its literal name must be added to `WM.HANDLERS`, registered in the
owning page module, and covered by `test_bridge_contract.py`. Workers push
semantic completion or state events and never touch the page directly.

## Key states

The implementation and smoke pass cover:

- no EVE folder selected;
- no accounts discovered;
- unidentified account;
- alias without associated characters;
- one and several confirmed characters;
- unresolved ESI character name;
- identification awaiting activity;
- no useful file changes;
- one account with several changed characters;
- several changed accounts;
- changed or unreadable profile during identification;
- successful and cancelled identification;
- no backups;
- unreadable backup store;
- fewer than, exactly, and more than 20 backups;
- malformed legacy backup stem;
- invalid retention value;
- retention saved without deletion;
- exact-count destructive retention confirmation;
- partial prune failure;
- mutation already busy.

## Testing

### Settings and identity model

- Valid aliases and associations round-trip through settings persistence.
- Malformed entries are discarded without losing valid siblings.
- Aliases are trimmed and bounded.
- One character cannot remain associated with two accounts.
- Associations survive changes between EVE settings profiles such as Default
  and Alt.
- Existing settings documents receive empty mappings without migration errors.

### Identification

- One changed account plus one changed character yields one candidate.
- One changed account plus several characters requires a manual character
  choice.
- Several changed accounts, no changed account, and no changed character never
  produce a candidate.
- Added files count as changed.
- Removed files and changed selection invalidate the session.
- Cancel and route leave clear the snapshot.
- No EVE file is written during observation or association persistence.

### Labels and bridge

- One Python label producer covers account source, target, formation, confirm,
  and backup payloads.
- Character fallbacks remain usable offline.
- `+ N` counts confirmed additional characters only.
- Raw IDs remain present as secondary metadata.
- New handlers satisfy the three-way bridge contract.

### Backups and retention

- Existing backup names resolve without opening archive manifests.
- Unknown stems degrade to their stored value.
- The payload remains newest-first and page batching does not reorder it.
- `eve_settings_state()` continues returning the complete backup history for
  client-side batching.
- Prune preview and prune execution select the same paths.
- `PruneReport` records both deleted and failed paths.
- Lowering retention reports the exact count before deletion.
- Manual backups are never selected for pruning.
- Persistence failure deletes nothing.
- Partial deletion is reported accurately.

### Page conventions

- The Backups card has no nested scrolling cap.
- Backup rows and headers share tracks and padding.
- The card uses the route's full available width.
- Target owns the flexible track.
- The selected profile appears in the backup button.
- Account controls use the generated human labels.
- Every control has a visible focus state and an accessible name.

### Manual Windows smoke pass

At minimum:

1. Identify one account by launching and fully closing one character.
2. Exercise no-change and multiple-account ambiguity without creating a link.
3. Add an alias and manually associate another character.
4. Switch profiles and verify the identity follows the account ID.
5. Copy account settings and verify the roster and confirmation use the same
   label.
6. Check the backup table at 840x625 and a wide window with more than 20 rows.
7. Restore a character, account, and profile backup after verifying the target
   label and date.
8. Lower retention, verify the exact deletion count, decline once, then accept.
9. Confirm manual backups survive pruning.

## Non-goals

- Reading launcher credentials or private launcher storage.
- Discovering or displaying an unconfirmed complete account roster.
- Sending account aliases or associations over the network.
- Renaming EVE account IDs or settings files.
- Changing backup archive compatibility or restore destinations.
- Automatically deleting manual backups.
- Inferring permanent associations from historical nearest timestamps.
