# Profiles: hide deleted characters and clean account links

## Intended outcome

When Profiles opens on a Tranquility profile, Wingman verifies locally
discovered character IDs through ESI. A character that ESI explicitly reports
as deleted is removed from every live Profiles character choice and from
Wingman's saved account-character links. Wingman does not delete, rename, or
rewrite the corresponding EVE settings file or any backup.

Unresolved characters remain visible during network outages. Profiles remains
usable offline. No validity check runs for non-Tranquility or unrecognized
shards. Existing account names and character links are formally interpreted as
Tranquility metadata; account identity management is unavailable on other
shards.

The separately reported missing-new-character symptom is not part of this
change. It reproduced correctly on the maintainer's machine, and a local
harness confirmed that discovery sees a valid `core_char_<id>.dat` added after
the first scan. There is no demonstrated application defect to fix.

## Confirmed ESI behavior

The first draft proposed treating rejection from `POST /universe/names` as a
deletion signal. Independent review correctly rejected that assumption.

A diagnostic against the selected real profile established:

- the profile contained 41 `core_char_*.dat` files;
- `/universe/names` resolved all 41, including recently deleted characters;
- `GET /characters/{character_id}` returned ordinary character data for 39;
- it returned an explicit 404 for two recently deleted characters:

  ```json
  {"status":404,"error":"Character has been deleted!"}
  ```

The deleted IDs were `2122839572` and `2124127801`. There were no transient
failures. Therefore `/universe/names` remains suitable for names but is not a
deletion detector.

A proposed affiliation prefilter was also disproved. Live ESI returned
corporation `1000044` for one deleted character and `1000045` for the other;
those are School of Applied Knowledge and Science and Trade Institute, while
Doomheim is `1000001`. Any corporation-based prefilter would already miss one
of the two confirmed examples. The design therefore uses bounded direct
character-information requests and no affiliation inference.

## Evidence and constraints

- `wingman/evesettings/tree.py` rescans the selected profile on every
  `discover()` call. It is a pure inventory of local files and recognizes only
  `core_char_<ASCII digits>.dat` as character files.
- `Api.eve_settings_state()` calls `discover()` on every state request; it does
  not cache the filesystem roster (`wingman/ui/api.py`).
- Profiles requests state and starts ESI resolution when its route is entered
  (`wingman/web/evesettings.js`). Network work must stay off the bridge thread.
- `wingman/evesettings/names.py` treats timeouts, rate limits, gateway failures,
  malformed responses, and route-level errors as transient. Cosmetic ESI
  failures leave local characters visible as `Character <id>`.
- Discovery supports Tranquility, Serenity, Singularity, Duality, Thunderdome,
  Infinity, and unknown raw shard directories. Current ESI URLs are fixed to
  `datasource=tranquility`; a Tranquility verdict must not hide a character from
  another shard.
- Account-character links are Wingman-owned persisted metadata. The model
  permits at most three active IDs per named account and each character may
  belong to only one account (`wingman/settings.py`, `wingman/ui/api.py`).
- Profiles mutations are serialized by `Api._eve_mutation`. Settings
  read-modify-write operations are serialized and roll back the live dictionary
  on failure, but `_save_locked()` currently publishes with `Path.write_text()`
  and can expose a truncated or partial document after interruption
  (`wingman/settings.py`). The repository already provides
  `atomicio.write_atomic()` for replace-based publication.
- Backups are independent recovery artifacts and remain useful even when the
  live character was deleted.
- The automated suite does not execute the page. Asynchronous row removal and
  identification reset require a Windows smoke pass (`DESIGN.md`,
  `docs/smoke-checklist.md`).

## Decisions for review

### 1. Require an explicit deleted-character response

A character is hidden only when the public character-information endpoint
returns HTTP 404 with a parsed JSON object whose `error` value is exactly
`"Character has been deleted!"`.

All other outcomes are non-destructive:

- 2xx with a valid non-empty character name means active and also supplies the
  cosmetic name;
- timeout, transport error, rate limit, 5xx, malformed JSON, or another 404 body
  is transient and leaves the character visible;
- local validation failures such as 422 are not deletion evidence and leave the
  file visible.

Matching this explicit API result is intentionally strict. The consequence is
conservative: an unknown response can leave a stale row visible, but cannot hide
an active character or remove its saved link.

### 2. Make bounded direct checks and cache only monotonic facts

Check each locally discovered Tranquility character through
`GET /characters/{character_id}` in a background worker. Bound parallelism to a
small fixed number so a 41-character profile does not serialize dozens of
round trips but also cannot burst unbounded requests at ESI. Keep the existing
per-request timeout and honor transient outcomes independently: one failed ID
must not turn another into a deletion verdict.

Cache names and confirmed deletions by `(datasource, character_id)` for the
process. Do **not** cache "active" as a permanent validity result: a character
that is active on one Profiles visit must be checked again on a later visit so
a deletion during a long-running Wingman process is eventually detected.
Deleted is monotonic for the process; transient outcomes are never cached.

Track each pass separately by canonical server/profile paths using real-path
and platform-normalized case, matching repository path-identity rules. A stale
pass may learn a global name or deletion fact, but cannot clean or repaint a
different current selection.

The existing `/universe/names` path remains for non-Tranquility contexts and
for Tranquility IDs present only in saved account links. Successful
character-information responses supply names for locally discovered
Tranquility files, so those IDs do not need a second lookup. Association-only
IDs remain name-only: without a local file they are not deletion candidates or
authorized for automatic cleanup.

### 3. Define account identity and deletion cleanup as Tranquility-only

Do not authorize cleanup from the existing server key alone. `_shard()` maps
any directory name containing `tranquil` to that display key, which is suitable
for labeling but too permissive for persisted deletion.

Add a separate strict `is_tranquility_server()` predicate for this destructive
boundary. After canonical path normalization, accept only a server basename
that is exactly `tranquility` or ends with EVE's terminal
`_tq_tranquility` marker. Require both this predicate and the discovered
`tranquility` key before running deletion checks, account naming/linking, or
automatic cleanup. Names such as `tranquility_backup`,
`fake_tranquility_other`, or a generic directory merely containing `tranquil`
remain untrusted and non-destructive. False negatives degrade to visible stale
rows and no cleanup, which is the safe failure.

The persisted `account_names` and `account_characters` schema has no datasource
field. Existing values are interpreted as Tranquility metadata. This is a
deliberate compatibility rule rather than an unsafe guess at provenance. On
non-Tranquility and unknown shards:

- character/account settings files remain available for copy and backup;
- character names retain existing best-effort/fallback behavior;
- account rows use internal IDs rather than applying Tranquility account
  metadata;
- account identification and manual account-link controls are unavailable;
- no deletion filtering or metadata cleanup occurs.

This avoids a migration for a feature used very rarely outside Tranquility and
prevents a Tranquility deletion verdict from mutating another shard's identity
state. Add a payload flag so the page derives account-identity availability
from Python rather than reimplementing shard recognition.

Deletion candidates come only from character files in the selected
Tranquility profile. Associations without a matching local Tranquility file are
not probed or pruned.

### 4. Automatically prune confirmed deleted account links

After a current-context pass, remove each confirmed deleted local character ID
from all Tranquility `eve_settings.account_characters` values; drop entries that
become empty and keep `account_names` unchanged.

Do not hold `_eve_mutation` during network calls. The resolver is already a
background worker, so it may wait normally to acquire `_eve_mutation` for the
short cleanup phase without blocking the bridge thread or spinning retries.
After acquiring it, revalidate the canonical trusted-Tranquility context,
reread the live mapping, and persist the cleaned mapping through
`settings.update_section()`.

Before adding automatic background cleanup, change `settings._save_locked()` to
publish its complete JSON payload through the existing
`atomicio.write_atomic()` rather than `Path.write_text()`. This is a
behavior-preserving hardening of every settings write: the old document remains
intact if serialization, temporary-file writing, fsync, or replacement fails,
while `settings.update()` continues to restore the in-memory dictionary. Add
focused tests for replacement failure, intact old content, successful
publication, and compatibility with the existing save lock. This deliberately
broadens the mechanical write path because automatic cleanup must not introduce
a new unattended opportunity to truncate the application's whole settings
document.

If persistence fails, rollback leaves the live mapping intact. Retain the
process deletion verdict, mark cleanup pending, log IDs without account names,
and retry on the next route-triggered or coalesced resolution pass. While
cleanup is pending:

- live account payloads filter the deleted IDs so they are not displayed;
- account mutation endpoints first retry cleanup under their already-held lock;
- if cleanup still cannot persist, refuse the requested edit with a specific
  save error rather than accepting a complete-roster submission containing
  hidden state.

The local EVE files and all backups remain untouched. Worker-spawn or worker
exceptions always release the coordinator's running state in `finally`, then
start a requested trailing pass if one exists.

### 5. Filter at every Python authorization boundary

For the current Tranquility context:

- exclude confirmed deleted records from `characters` and
  `identity_characters`;
- filter pending-cleanup IDs from live account summaries and `character_ids`;
- exclude deleted IDs from automatic identification candidates;
- reject them in `eve_settings_set_account_characters()`;
- revalidate identification confirmation before persisting it.

Unresolved IDs remain accepted and visible. Backup rows remain listed. A
character backup may retain its last name; an account backup remains listed but
its live Tranquility account summary omits deleted links.

### 6. Invalidate only the identification candidate that became deleted

Protect ephemeral identification publication with a monotonic generation and
a dedicated short-held identification-state lock, independent of
`_eve_mutation`. Hold this lock only to read/increment the generation, clear
state, or atomically compare-and-publish a completed snapshot/candidate. Never
hold it during filesystem work, ESI calls, settings writes, or dialogs.

Cancellation remains independent of `_eve_mutation`, so route exit cannot be
refused while cleanup owns that lock. Under the identification-state lock it
increments the generation and clears the observation/candidate atomically.
Start and check capture a generation, do their work outside the state lock,
then reacquire it and publish only if the generation is unchanged; otherwise
they return a cancelled/idle result. This closes the check-then-publish race:
cancellation either runs before publication and invalidates it, or runs after
publication and clears it. Confirmation validates its candidate generation
under the same state lock before mutation.

If learned deletion intersects the current Python candidate, cleanup increments
the generation and clears identification under this short state lock while it
owns `_eve_mutation`. The generation is process-local and needs no migration.

Carry the identification generation across the bridge, not only inside
Python. Every identification start/check/candidate/cancel response includes its
captured generation. `onEveSettingsNames` includes the current generation plus
`deleted_candidate_ids`, defaulting to an empty list.

The page retains the highest identification generation it has observed. Before
rendering any asynchronously resolved identification response, its promise
callback compares that response's generation with the retained value and
ignores an older response. The event handler records its generation **before**
examining local candidate state, then resets the focused step when the current
candidate intersects `deleted_candidate_ids`.

This handles both delivery orders. If a candidate renders first, the newer
deletion event clears it. If the event arrives before the candidate promise
callback, the retained generation causes that delayed callback to discard the
stale candidate instead of resurrecting it. A newer unrelated candidate is not
cleared; a candidate containing the same confirmed-deleted ID is invalid in any
generation.

### 7. Use single-flight with a coalesced trailing pass

Only one ESI worker runs at a time. A request received while it runs sets a
pending flag. In the worker's `finally`, atomically clear running state and
start exactly one pass for the latest selected context if pending. Requests
received during that pass coalesce again.

Thus switching from profile A to B while A is active always resolves B without
overlap or another user action. A stale pass may populate global name/deletion
facts but may not clean, clear identification, or publish for a different local
context.

The current trailing pass evaluates all cached facts against its context and
publishes whenever they newly affect that context, even if the network result
was learned by the stale prior pass. Track context application separately from
remote cache insertion.

Emit `onEveSettingsNames` once when the current context gains a visible name,
hides a deletion, completes cleanup, or resets the matching candidate.

### 8. Preserve files, backups, and recoverability

Do not delete, move, rename, or rewrite any `core_char_*.dat` file. Do not hide
or delete backups. Do not persist ESI status: every application launch
revalidates when Profiles is opened, preventing a permanent blacklist from an
obsolete API response.

The only persisted mutation is removal of a definitively deleted character from
Wingman's own account-link metadata, as requested.

## Alternatives and tradeoffs

### Use `/universe/names` rejection

Rejected by real evidence: it continued resolving both recently deleted
characters.

### Infer deletion from corporation affiliation

Rejected by real evidence: the two deleted examples reported different starter
corporations, neither of which was Doomheim.

### Check character information sequentially

Simpler, but a 41-character first pass would serialize network latency. Small,
bounded parallelism keeps route entry responsive without unbounded ESI load.

### Filter or perform network work in `evesettings.tree`

Rejected. Tree discovery owns filesystem facts, is intentionally pure, and runs
on the bridge thread.

### Hide account links only in the payload

Rejected after independent review. The page submits its visible list as the
complete roster, so the next normal edit would silently delete hidden links
anyway. Explicit persisted cleanup makes the lifecycle honest.

### Preserve deleted links in an inactive archive

Rejected as unnecessary schema expansion. EVE files and backups already
preserve recoverable local data.

### Add datasource fields to account identity metadata

Rejected as disproportionate for the product's use: account identity is used on
Tranquility, while Singularity is visited very rarely. Existing metadata is
interpreted as Tranquility and identity management is unavailable elsewhere,
avoiding both migration ambiguity and cross-shard destructive cleanup.

### Add refresh UI or polling for the remote new-character report

Rejected without a reproducible defect. Discovery already rescans on state
requests and route entry refreshes state.

## Ordered implementation steps

1. Harden settings publication by routing `_save_locked()` through
   `atomicio.write_atomic()` and add failure/intact-old-file tests.
2. Add transport-level tests for strict character-information classification,
   including successful names, explicit deletion, and transient/malformed
   outcomes.
3. Add datasource-keyed process status caching, bounded checks, and a
   single-flight/coalesced worker coordinator.
4. Add and test the strict trusted-Tranquility predicate independently from the
   existing display-oriented shard key; prevent stale contexts from mutating or
   repainting current state.
5. Add tests for automatic persisted association cleanup, write rollback,
   retry, concurrent manual edits, and reload from disk.
6. Filter confirmed deletions from state, automatic identification candidates,
   and character-link mutation/confirmation boundaries.
7. Carry identification generations through responses/events and reject stale
   page callbacks in both event-delivery orders.
8. Run focused and full automated verification, then perform the Profiles
   Windows smoke pass.

## Testing and verification strategy

Automated tests will prove:

- `/universe/names` remains name-only and does not imply deletion;
- only the exact explicit deleted-character 404 becomes a deletion verdict;
- timeout, 429, 5xx, malformed data, another 404, and 422 preserve visibility
  and links;
- bounded checks never exceed the configured parallelism;
- active characters are rechecked on later passes while deleted verdicts are
  datasource-keyed and process-monotonic;
- Tranquility association-only IDs retain batch name resolution but are not
  deletion candidates;
- the strict trusted-Tranquility predicate accepts real `_tq_tranquility`
  directories but rejects names that merely contain `tranquil` or append text
  after `tranquility`;
- a Tranquility deletion cannot affect another shard;
- unknown, heuristic-only, and non-Tranquility shards perform no deletion
  checks and expose no account identity/link management;
- confirmed deleted rows disappear from character and identity payloads;
- automatic identification cannot offer or persist them;
- bridge-visible generations handle both orderings: candidate callback before
  deletion event and deletion event before delayed candidate callback;
- learning deletion after candidate display clears Python candidate state and
  emits matching deleted candidate IDs without resetting an unrelated newer
  candidate;
- cancellation remains successful while cleanup owns the mutation lock, and
  the identification-state lock makes generation compare-and-publish atomic so
  in-flight start/check work cannot recreate hidden state after route exit;
- manual/stale bridge requests cannot relink them;
- atomic settings publication leaves the previous complete document intact on
  replacement failure and publishes the new complete document on success;
- cleanup removes the ID from every account, drops empty lists, preserves
  account names, and survives reload;
- cleanup does not overwrite a concurrent roster edit;
- failed cleanup is retried, while background cleanup waiting on the mutation
  lock neither blocks the bridge nor spins;
- local `.dat` files and backups remain present and listed;
- overlapping requests produce one worker plus at most one coalesced trailing
  pass at a time;
- switching profiles during an in-flight pass eventually resolves the latest
  profile without another user action;
- stale worker results cannot clean or repaint a newly selected profile;
- one semantic refresh follows a current-context identity change.

Verification commands:

```bash
uv run --no-sync python -m pytest tests/test_evesettings_names.py tests/test_api_evesettings.py -q
uv run --no-sync python -m pytest tests/
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
```

Windows smoke coverage:

1. Open Profiles with a known deleted local character file.
2. Confirm it may appear only before ESI answers and then disappears.
3. Confirm a selected source/target disappearing leaves copy controls coherent.
4. Confirm a displayed identification candidate is reset if deletion lands.
5. Confirm the deleted account link is absent after refresh and restart.
6. Confirm active and unresolved characters remain usable.
7. Confirm the deleted character's backup remains listed and local EVE file
   remains untouched.
8. Switch profiles during resolution and confirm the latest profile resolves.
9. Switch to non-Tranquility, unknown, and misleadingly named `tranquil*`
   profiles and confirm no deletion filtering or account identity management
   occurs.

## Adaptation points

- If bounded individual checks still make first entry unacceptably slow, measure
  before optimizing. Any replacement batch signal must be validated against
  both known deleted IDs and must still confirm deletion explicitly.
- If exact ESI wording changes, require equally strong structured evidence from
  current behavior before broadening the classifier; never treat an arbitrary
  404 as deletion.
- If waiting for the mutation lock makes resolution completion visibly slow,
  measure the delay before changing coordination. Any alternative must preserve
  serialization without polling or blocking the bridge thread.

## Explicit exclusions

- Diagnosing or changing the unreplicated remote new-character issue.
- Deleting or cleaning EVE settings files.
- Modifying backup visibility or contents.
- Persisting names or deletion verdicts.
- Validity filtering or account identity/link management on non-Tranquility
  shards.
- Migrating account identity metadata to a datasource-keyed schema.
- Polling Profiles or adding a manual refresh control.
- Archiving deleted account links in a new persisted schema.
