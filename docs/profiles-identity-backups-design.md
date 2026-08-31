# Profiles identity and backup safety

Design brief. Original base: `main` (`652dceb`), 2026-09-01. Account-identification follow-up revised from merged PR #128 (`13290ae`).

**Delivery state:** PR #128 shipped account labels, backups, retention, and the
first guided identification pass on `main`. This follow-up changes only the
identification model and flow described below; the backup and retention design
remains authoritative. No release tag contains `13290ae`: `v4.2.0` predates it,
so the unreleased alias-shaped identity state is intentionally replaced rather
than migrated.

## Outcome

Profiles must identify every source, target, and backup in human terms before
the user copies or restores EVE settings. Wingman will add required local
account names, confirmed account-to-character associations, guided account
identification, resolved backup labels, a full-width backup history, and
visible automatic backup retention.

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
already records local account naming as deferred work and calls numeric account
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
  "account_names": {"19191934": "eve-login-name"},
  "account_characters": {"19191934": ["2115754172", "2115754173"]}
}
```

The name is the EVE Online username the user supplies. EVE does not expose or
verify it through the settings files, so Wingman treats it as user-confirmed
local metadata. It is stored in plaintext in `settings.json`, displayed on
Profiles identity surfaces, and never sent over the network. The UI says to use
the username used to sign in and that it stays on this computer.

`settings.validated_eve_settings()` owns both defaults and validation. This
follow-up replaces the unreleased `account_aliases` model from PR #128 rather
than migrating it: no compatibility read or write of that key remains.

IDs are stored as decimal strings. Values loaded from `settings.json` are
validated defensively:

- reject non-decimal or empty IDs;
- trim account names, reject empty values, and enforce the 80-character limit;
- require account names to be unique after trimming and case-folding while
  preserving the entered capitalization for display;
- discard a later duplicate name in persisted mapping order;
- retain names for accounts with no current character links;
- discard associations whose account has no valid name;
- discard malformed collection members without discarding valid siblings;
- deduplicate character IDs and let the first account in persisted mapping
  order retain a character claimed by malformed duplicate entries;
- retain the first three valid, unclaimed character IDs in each account's
  persisted list order and discard the rest.

An EVE account has at most three character links. The maximum, unique-name
rule, and name-before-links rule are enforced in Python endpoints as well as
normalization. The page may hide impossible actions but is not authoritative.

Associations are local metadata only. They must not alter EVE files, backups,
ESI state, or the launcher. They persist across settings profiles so the same
account remains recognizable when the user switches from Default to Alt.

A character already linked to any account is omitted from every Add dropdown.
Manual relocation is therefore an explicit remove-then-add sequence rather
than an Add action that silently changes ownership. A guided identification
candidate may still reveal that a character belongs to another account; that
path names both accounts and confirms the move. Python validates the complete
destination roster, including its three-character maximum, before removing the
character from its previous account. A refused or failed move changes neither
account.

## Human-readable account labels

Account controls use the supplied account name as the primary human label and
retain the raw account number without repeating an `ID` label the surrounding
Accounts context already provides.

| Known data | Primary label | Secondary metadata |
|---|---|---|
| Name and characters | `eve-login-name` | `Aiga Otsolen + 2 · 19191934` |
| Name only | `eve-login-name` | `19191934` |
| Not identified | `19191934` | none |

A persisted character association without a valid account name is malformed
and is removed during normalization, so a character-only account label is no
longer a valid state. `+ N` counts only other confirmed associations. Wingman
must not imply that it knows the complete launcher roster.

Native select options cannot render two lines, so source and formation account
pickers use a flattened form:

- `eve-login-name · Aiga Otsolen + 2 · 19191934`
- `eve-login-name · 19191934`
- `19191934`

The label producer belongs in Python. Source lists, target rows, formation
account selection, copy confirmations, completion or error text, and backup
rows must not maintain separate account-label logic.

`#es-source` already takes the available row width. The formation account
selector must remain wide enough for its chosen identity to be readable.
Native option labels stay compact and put the human label first; the full
two-line identity remains visible in account management and target rows.

Character labels retain the existing ESI name with `Character <id>` as the
offline or unresolved fallback.

## Guided account identification

Accounts mode has a plain `.btn` labelled **Identify accounts…**. It is hidden
in Characters mode and opens the chromeless `accountidentity` sub-screen of
Profiles. The copy card remains a copy form; no management panel expands
between its mode switch and source picker. The trailing ellipsis is intentional
because the button opens the focused flow.

The flow has five steps: explanation, waiting, candidate confirmation,
required account name, and optional account roster. No-change, ambiguity,
invalidated selection, and EVE-still-running responses are variants of the
waiting step rather than additional steps. Each step has one visually primary
action. `‹ Profiles` remains available throughout and cancels any unpersisted
observation or candidate.

### Start

The opening state says:

> EVE stores account settings under a number, not a name. Wingman can match that
> number to a character by watching which settings change together.

Before the action, it says to close every EVE client and explains that one
character will be launched after identification starts. **Start identification**
records a snapshot of every account and character file in the selected server
and profile. The snapshot includes path, size, and high-resolution modification
time so a same-size rewrite still counts and an unchanged file does not.

Starting identification does not write any EVE or Wingman setting.

### Observe

After the snapshot, show:

> Launch one character, enter the game, make a small settings change, then close
> the client completely.

Do not suggest moving an in-game window unless live EVE testing proves that it
dirties both required settings files. The generic instruction is accurate
without claiming an unverified example.

**Check changes** is the primary action and **Cancel** is secondary. The
workflow does not poll. A check compares the current discovery result with the
snapshot.

While identification is active, Profiles actions that mutate EVE settings are
disabled: copy, restore, delete backup, create backup, formation editing, and
retention changes. This prevents Wingman's own writes from contaminating the
observation. The backend enforces the same exclusion, so a direct or stale page
call cannot bypass the disabled controls.

Start, check, and cancel remain request/response bridge methods named
`eve_settings_identification_start`, `eve_settings_identification_check`, and
`eve_settings_identification_cancel`. They perform the same bounded directory
scan and file-stat class of work already accepted in `eve_settings_state`, so
they run on the bridge thread and return semantic state directly. They do not
add a Python push or a `WM.HANDLERS` entry.

Leaving the `accountidentity` sub-screen sends
`eve_settings_identification_cancel`; changing root, server, or profile also
cancels the Python-owned snapshot and candidate. The sub-screen follows Probe
Formations' route pattern: the title-bar destinations are hidden and `‹
Profiles` is the explicit way back. Starting identification is refused while
`_eve_mutation` is held, and `_eve_begin` refuses every EVE mutation while an
identification snapshot exists. This mutual exclusion is enforced in Python as
well as painted in the page.

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

The identification check records the exact account and set of offered
characters as the Python-owned pending candidate. The page names both objects
and makes **Link character** the primary action. Pressing it selects one offered
pair for the next page state but does not yet persist metadata. A stale or
fabricated confirmation may not substitute another discovered account or
character.

If the candidate account already has a valid account name, **Link character**
calls `eve_settings_identification_confirm` with that existing name and opens
the roster after the link is saved; it does not show the naming step. Name
uniqueness always excludes the account being renamed or reconfirmed. A
character already linked to that same account is a successful no-op that opens
the roster. If the account already has three different links, identification
may show the match but refuses another link and directs the user to account
management. If the selected character belongs to another named account, the
page uses `WM.confirm` to name both accounts before continuing. Python
revalidates ownership and destination capacity before any write.

Suggested failure copy:

- No useful pair: `No account and character changes were found. Make a small settings change in the client, then close it completely and check again.`
- Several accounts: `More than one account changed. Close the other EVE clients and start again.`
- Folder changed: `The selected EVE profile changed. Start identification again.`

### Required account name and atomic confirmation

After the user confirms the first character, show the pending match and require:

**Account name**

> Use the username you sign in to EVE Online with. Stored only on this computer.

The field commits through **Save and continue** or Enter, never on blur. Both
paths send the name with the selected pending account and character to
`eve_settings_identification_confirm`. Python verifies that the pair belongs to
the latest pending candidate, validates the name and uniqueness rules, and
persists `account_names` plus the first `account_characters` entry in one
`settings.update_section()` call. The observation and candidate clear only
after that atomic write succeeds.

A case-insensitive duplicate is refused inline with:

> That EVE Online username is already assigned to another account.

A refused name or persistence failure leaves the candidate and typed value on
screen. Leaving the route before a successful save discards the pending match
and writes neither map.

### Add the remaining characters

After the atomic save, the same focused screen becomes an account-roster step.
It confirms the first link, leads with the account name, and shows `1 of 3
characters linked`, `2 of 3 characters linked`, or `3 of 3 characters linked`.
It says:

> Check this account in the EVE launcher, then add any other characters shown
> there.

Wingman cannot read the launcher roster. The remaining-character control lists
characters discovered in the selected EVE profile but never implies they
belong to this account. Each additional link requires an explicit user choice.

The roster shows confirmed characters, one dropdown of remaining discovered
and globally unlinked characters, and **Add character**. Additions happen one
at a time so a large multibox roster does not become a wall of checkboxes.
Characters linked to this or any other account never remain in the dropdown.
While an addition is available, **Add character** carries the screen's single
accent treatment and **Done** remains an ordinary button.
Done remains available after the first save, so one-character and two-character
accounts are never forced to fill all slots. It returns to Profiles without a
separate mostly empty completion screen.

If no other unlinked character is discovered in the selected profile, hide the
picker and Add action. Explain that only characters discovered in this EVE
profile can be offered, and that another character can be made available later
by launching it, making a small settings change, and closing EVE completely.
In this state, and at the three-character maximum, **Done** becomes the single
accent action.

At three links, show the `3 of 3` state and point users to the management
disclosure if a wrong or obsolete link must be removed. Python refuses a fourth
link. A destination already at three rejects a stale direct request.

Beside **Done**, offer a secondary **Identify another account** action. It
returns to the explanation step without leaving the sub-screen; pressing
**Start identification** there takes the fresh snapshot after the user has
closed every EVE client. The roster also reports `<named> of <discovered>
accounts identified in this profile`; both numbers derive from the current
payload rather than being maintained separately by the page.

### Manual identity management

A secondary **Manage account names and character links…** disclosure on the
sub-screen lets users:

- add or rename an account using a non-empty, globally unique account name;
- associate discovered characters with a named account, up to three total;
- remove a confirmed association without removing the retained account name;
- relocate a character by removing its existing link before it becomes
  available in another account's Add dropdown.

The existing alias endpoint is replaced by
`eve_settings_set_account_name`; `eve_settings_set_account_characters` remains
the complete-roster endpoint. Both are synchronous request/response methods.
Python validates before mutating, persists the complete value, returns the
standard `{applied, persisted, error}` shape, and the page refetches state after
an applied change. Account names may be changed but never cleared. Add controls
omit every character already linked to any account; Python still preserves
single ownership if a stale or direct request supplies one. No new push handler
is required.

Manual management remains scoped to accounts discovered in the selected EVE
profile. Names and links for an account absent from that profile remain stored
and become manageable again when that account appears in the selected profile.

Removing or moving an association changes Wingman's labels only. It does not
remove a character or modify EVE settings.

## Backup target labels

The backup payload gains a display target assembled from the parsed backup
kind and stem. Character and account IDs are recovered only from the exact
`core_char_<digits>` and `core_user_<digits>` stem forms produced by
`create_file_backup`; `_sanitize()` is otherwise lossy, so any non-matching
legacy stem falls back unchanged rather than being partially interpreted:

- character backup: resolved ESI name, falling back to `Character <id>`;
- account backup: account name and confirmed-character summary, falling back to
  the account number;
- profile backup: the profile name already encoded in the stem.

Raw identity remains available as secondary text:

- `Character 2115754172`
- `Account 19191934`
- `Profile`

Old archives require no migration. If a stem is malformed or predates a known
shape, show the existing stem rather than inventing a human label. A renamed
account or changed association immediately changes the displayed backup label
because labels are resolved from current local metadata, while the archive's
restore target remains unchanged.

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
- Long account names and character names truncate only after the raw identity
  remains available through accessible text and a tooltip.
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

- validation and atomic persistence of account names and associations;
- case-insensitive account-name uniqueness and the three-character maximum;
- the account display-label representation, including the `account_name`
  payload field that replaces `alias`;
- identification snapshots, candidate classification, and the exact pending
  candidate that may be confirmed;
- backup target resolution;
- retention validation, prune preview, mutation, and failure reporting.

The page owns:

- the current presentation step within backend-authorized semantic state;
- whether the secondary names-and-links disclosure is expanded;
- the currently visible batch of backup rows;
- filter and selection state that changes only what is drawn;
- rendering backend-provided labels and semantic states.

The observation and pending candidate are ephemeral and scoped to the selected
root, server, and profile. They remain underscore-prefixed `Api` attributes.
Neither is written to `settings.json`. Candidate comparison, persistence, and
clearing happen under the mutation lock so two concurrent confirmations cannot
both succeed. Account names and associations cross the bridge because they
change labels Python computes.

This design adds bridge methods but no new Python push names. Identification
and identity-management methods return their semantic results directly;
retention reuses `onEveSettingsDone`. Every literal `WM.send` target must remain
a callable `Api` method; renaming the account-name endpoint and adding the
atomic confirmation endpoint update the bridge-contract and Profiles lexical
tests. If implementation introduces any push instead, its literal name must be
added to `WM.HANDLERS`, registered in the owning page module, and covered by
`test_bridge_contract.py`. Workers push semantic completion or state events and
never touch the page directly.

## Key states

The implementation, `?dev=1` harness, and smoke pass cover:

- no EVE folder selected;
- no accounts discovered;
- unidentified account;
- account name without associated characters;
- one, two, and three confirmed characters;
- attempted fourth character;
- unresolved ESI character name;
- identification awaiting activity;
- no useful file changes, including recovery copy naming the settings change;
- one account with several changed characters;
- several changed accounts;
- changed or unreadable profile during identification;
- candidate confirmed but account name not yet saved;
- candidate account already named;
- candidate character already linked to another account;
- candidate account already at three links;
- blank, duplicate, overlong, and persistence-failed account names;
- pending candidate discarded by cancel or route departure;
- first name and character saved atomically;
- optional remaining-character roster with Done available at one and two links;
- no remaining discovered characters;
- full three-character roster with no add affordance;
- guided confirmation moving a previously linked character to an account with
  room;
- refused guided move to a full account;
- linked characters omitted from guided and manual Add dropdowns;
- named account absent from the selected profile;
- manual account rename and refused name clearing;
- identifying another account without leaving the sub-screen;
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

- Valid account names and associations round-trip through settings persistence.
- Names are trimmed and bounded; case-insensitive duplicates keep only the
  first persisted account.
- Names without links remain valid.
- Associations without valid names are discarded.
- One character cannot remain associated with two accounts.
- A malformed list retains its first three valid, unclaimed IDs and discards a
  fourth without losing valid siblings.
- Account names and associations survive changes between EVE settings profiles
  such as Default and Alt.
- The retired `account_aliases` key is not loaded or written.

### Identification

- One changed account plus one changed character yields one candidate.
- One changed account plus several characters requires a manual character
  choice.
- Several changed accounts, no changed account, and no changed character never
  produce a candidate.
- Added files count as changed.
- Removed files and changed selection invalidate the session.
- Check while EVE is open remains in the waiting state.
- No-change recovery mentions making a small settings change.
- Candidate confirmation persists nothing before a valid account name.
- The atomic confirmation accepts only the latest offered account and one of
  its offered characters.
- A candidate account with an existing name skips the naming step, and its own
  name does not conflict with itself.
- Initial confirmation refuses a full account and confirms before moving a
  character linked elsewhere.
- Blank, overlong, or case-insensitively duplicate account names persist
  neither the name nor the first link.
- A persistence failure writes neither map and keeps the candidate retryable.
- Successful confirmation writes the name and first link together and clears
  the observation.
- Two concurrent confirmations cannot both consume one pending candidate.
- Additional links stop at three in both guided and manual paths.
- Guided candidate moves validate destination capacity before changing the old
  account.
- Every linked character is omitted from both guided and manual Add dropdowns.
- Cancel and route leave clear the snapshot and pending candidate.
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
- Waiting, candidate, account-name, and roster states each expose one primary
  action.
- Done remains visible with one or two links; the add controls disappear when
  no candidate is available or at three.
- Step changes move focus to the new step's heading. The roster count is a live
  status, and inline account-name errors are associated with the field through
  `aria-describedby`.
- The dev harness accepts an explicit `?dev=1&identity=<state>` selector for
  idle, waiting, no-change, ambiguous, multi-character candidate,
  pending-name, existing-name, one/two/three-link roster, empty roster, move,
  and limit states at 840x625 and a wider viewport.
- Every control has a visible focus state and an accessible name.

### Manual Windows smoke pass

At minimum:

1. Start identification, launch one character, enter the game, make a small
   settings change, close the client completely, and check changes.
2. Confirm the proposed character, then leave before entering an account name;
   verify that neither the name nor link was saved.
3. Repeat, enter the EVE Online username, and verify the name plus first link
   are saved together.
4. Add a second character from the launcher-confirmed roster, then use Identify
   another account without leaving the sub-screen. Finish with Done and verify
   each identity follows its account ID across EVE profiles.
5. Re-identify an already named account and verify the naming step is skipped.
6. Complete a three-character account and verify neither guided nor manual
   management offers a fourth; verify a stale direct request is refused.
7. Attempt a case-only duplicate account name and verify it is refused without
   changing either account.
8. Verify characters linked to any account are absent from every guided and
   manual Add dropdown. Remove one link and verify that character then becomes
   available to add elsewhere.
9. Identify a character already linked to another account, accept the move
   confirmation, and verify it leaves the source account and joins the
   destination. Repeat with a full destination and verify refusal leaves the
   source unchanged.
10. Exercise no-change and multiple-account ambiguity without creating a link;
    verify no-change recovery mentions making a small settings change.
11. Exercise a profile with no other discovered character and verify the empty
    roster explains how to make one available later while Done remains usable.
12. Copy account settings and verify the roster and confirmation use the same
    label.
13. Check the identification flow in `?dev=1` at 840x625 and a wider viewport,
    including every state listed under Page conventions.
14. Check the backup table at 840x625 and a wide window with more than 20 rows.
15. Restore a character, account, and profile backup after verifying the target
    label and date.
16. Lower retention, verify the exact deletion count, decline once, then
    accept.
17. Confirm manual backups survive pruning.

## Non-goals

- Reading launcher credentials or private launcher storage.
- Discovering or displaying an unconfirmed complete account roster.
- Sending account names or associations over the network.
- Renaming EVE account IDs or settings files.
- Changing backup archive compatibility or restore destinations.
- Automatically deleting manual backups.
- Inferring permanent associations from historical nearest timestamps.
