# EVE Settings management

Design. Base: `main` (b2bac93), 2026-08-24.

## Outcome

Copy one EVE character's in-game settings onto many other characters without
digging through `%LOCALAPPDATA%\CCP\EVE` by hand, with every overwrite backed
up first and every backup restorable.

The capability exists today in TriffView (GPL-3.0-only, C#/.NET). This is a
port into Wingman, which has been GPL-3.0-only since #22 — see
`eve-preview-design.md` for why that relicense was what made deriving from
TriffView lawful, and what it means going forward.

This is a port, not a rewrite. Where it diverges from TriffView it does so
deliberately, and each divergence is recorded below with the defect it avoids.

## What was verified, and how

No probes were needed: unlike the preview subsystem, nothing here depends on
undocumented Win32 behaviour. What *was* needed was reading TriffView's
implementation closely enough to find the parts that should not be copied.
Two independent passes over `native/EveSettings/` produced the table below.

| # | Question | Result |
|---|---|---|
| 1 | Does TriffView write settings files atomically? | **No.** `native/Eve/AtomicFile.cs` exists and is used by TriffFleets and PlanStore; `EveSettingsController` uses none of it. Plain `File.Copy(overwrite: true)`. |
| 2 | Can a multi-target copy fail partway? | **Yes.** Backup names are second-granularity UTC; two in the same second collide, `ZipFile.Open(Create)` throws, and the loop aborts with some targets copied and some not. No report of which. |
| 3 | What does listing backups cost? | **One zip opened and parsed per backup, on every state refresh** — and a refresh follows every operation. The tool gets slower the more it is used. |
| 4 | Are the file operations tested? | **No.** All 16 tests in that feature cover the name resolver. Every destructive path is untested. |
| 5 | Can Wingman's `atomicio` be reused as-is? | **No.** `write_atomic` takes `str` and opens the temp in `"w"` mode with an encoding (`atomicio.py:13,35`). `.dat` files are binary; a binary sibling is required. |
| 6 | Does Wingman already build archives safely? | **Yes, and the precedent is directly applicable.** `combatlog.build_archive` stages to a `.tmp` and `os.replace`s it into place, because "a run that dies partway must not leave a truncated archive that reads as a complete export" (`combatlog.py:283-324`), with a regression test at `tests/test_combatlog.py:349-361`. |

Finding 5 is the load-bearing one for implementation order: it is new code in a
module whose current 60 lines are entirely about text, and everything in
`ops.py` depends on it.

## Architecture

```
web/evesettings.js ──► ui/api.py (thin) ──► evesettings/
                                              ├─ tree.py    discovery + containment   (no deps)
                                              ├─ names.py   ESI id → name             (no deps)
                                              ├─ backup.py  zip, restore, prune       → tree
                                              └─ ops.py     copy one → many           → tree, backup
```

Dependencies point one way. `tree.py` and `names.py` know nothing about each
other; `ops.py` is the only module that composes. The split exists so that
almost everything tests on Linux against `tmp_path` — see Testing.

`obs_youtube_uploader/evesettings` **must** be added to `tool.setuptools.packages`
in `pyproject.toml`. Discovery there is enumerated by hand, and an omission
installs cleanly in a checkout while dying at import in the frozen build.
`tests/test_packaging_completeness.py` exists to catch exactly this. The
`web/` directory ships wholesale (`packaging/uploader.spec:36`), so the new JS
needs no packaging change.

### Threading contract

Three lanes. The middle one is forced, not chosen.

| Lane | Work | Why |
|---|---|---|
| Bridge thread | `eve_settings_state()` | `scandir` over a few dozen files answers inline. |
| Worker thread | every mutation | `_confirm()` blocks the calling thread until the page answers, and the answer arrives on the bridge thread. Confirming inline deadlocks. |
| Background thread | The running-client probe | `discovery.list_clients()` enumerates windows and resolves PIDs to executables, which is not "scandir over a few dozen files". It drives an advisory pill, so state returns the last known answer and the probe pushes `onEveSettingsRunning` only when the value changes. |
| Background thread | ESI name resolution | Fired when the route is first opened, never at launch: the tray app starts hidden and must not make a network call nobody asked for. |

The worker-thread rule is the same one `delete_selected` already follows, and
for the same reason it documents at `ui/api.py:377-389`.

**The selection is a mutation too.** `root` is an input to every containment
check, so repointing it while a restore or a copy is in flight would have that
operation validate against a different root than the one in effect when the
user approved it. Picking a root and choosing a server/settings-set therefore
take the same lock, non-blocking, and are refused when it is held. Non-blocking
is not merely policy here: those two run on the bridge thread, and a worker
holding the lock is parked in `_confirm()` waiting for an answer the bridge
thread must deliver, so a blocking acquire would deadlock the app outright.

**One mutation at a time.** A per-mutation worker says nothing about how many
may exist at once, and `_confirm()` parks each one independently
(`ui/api.py:262-286`) — so two operations approved moments apart can interleave
over the same files and produce a partial backup or a half-applied restore.
Every mutation therefore takes a single module-level mutation lock, acquired
*before* the confirmation prompt and held until the operation finishes. A
second request that finds the lock held is refused with a message rather than
queued: queueing behind a dialog the user has not answered yet is worse than
declining, because the queued operation's own confirmation would describe
state that has since changed. The UI disables its action buttons while a
mutation is in flight; the lock is what makes that correct rather than
merely tidy.

### Bridge shape

One `eve_settings_state()` returning the whole tree; mutations return a report
dict; the page re-fetches state afterwards. Request/response, not push.

With one exception, which the request/response shape does not cover on its own:
**ESI name resolution completes after the state that triggered it was already
returned.** The first state build hands back `Character 98123456` for every
row, and nothing in a pure request/response bridge would ever tell the page
otherwise. So when a resolution pass finishes and produced at least one new
name, the background thread pushes `onEveSettingsNames` and the page re-fetches
state. One push per pass, not per name; a pass that resolved nothing pushes
nothing. This is the same `self._push(...)` channel the upload progress and
status messages already use.

TriffView pushes a full state object and diffs it against
`_lastPostedStateJson` to skip no-op sends — but every call site passes
`force: true`, so that dedupe is unreachable. There is nothing to port.

## Modules

### `tree.py`

`default_root()`, `discover(root)`, and the containment validators. Pure:
`scandir` and `stat`, no mutation, no network.

The three-level model is EVE's own:

```
%LOCALAPPDATA%\CCP\EVE\
  c_eve_sharedcache_tq_tranquility\   server
    settings_Default\                 profile ("settings set" in the UI)
      core_char_<characterId>.dat
      core_user_<accountId>.dat
```

Discovery is name-pattern based and top-directory-only at every level. A
directory is a server if it contains `settings_*` children or its name matches
a known shard; a profile is any `settings_*` directory. A settings file's ID
must be **all digits** — `core_char_abc.dat` is invisible to the tool, which
is TriffView's rule and worth keeping, since a non-numeric ID cannot be a
character.

`discover()` also carries TriffView's `NormalizeSelectedPaths` self-healing:
pointing "root" at a profile or server directory walks back up and rewrites
the selection rather than showing an empty list. Cheap, and the failure
without it is the most likely first-run confusion.

**Containment is the real defense.** Every path crossing into an operation is
resolved with `os.path.realpath` — not merely normalised — and checked to be
under the equally-resolved root, with a separator-aware prefix comparison so
that `C:\EVE-evil` does not pass as being under `C:\EVE`. Files must end
`.dat`, backups `.zip` and sit under the backup root.

`realpath` rather than `normpath` because a lexical check cannot see a symlink
or a Windows junction. Either can sit beneath a legitimate root and redirect a
delete or an overwrite outside it, and junctions in particular are something a
user can create by accident with `mklink /J` while reorganising an EVE install.
Resolving both sides before comparing is what makes the prefix test mean what
it says.

**Discovery is bounded.** Every child directory of the root costs a `scandir`
apiece to probe for `settings_*` children, on the bridge thread. That is
nothing for `%LOCALAPPDATA%\CCP\EVE`, which holds a handful; it is hundreds
of directory reads for a mis-picked root like `C:\Users\me`. A root with more
than `MAX_ROOT_CHILDREN` (64) directory children is refused as too wide to be
an EVE folder and says so, rather than probed slowly or truncated silently --
the same posture `unreadable` takes. The probe itself is lazy and capped too:
it returns on the first `settings_*` it sees and stops after
`MAX_PROBE_ENTRIES`.

**Enumeration failures are reported, not swallowed into emptiness.** TriffView
wraps every enumeration in a helper that returns empty on any exception, which
makes an unreadable directory indistinguishable from an empty one. `discover()`
returns the failure alongside the empty result so the UI can say *"Couldn't
read that folder"* rather than *"No settings sets"*.

### `names.py`

Character ID → name, against ESI's `universe/names`. Unauthenticated: no SSO,
no token, no scopes.

This endpoint **rejects the entire batch with 404 if a single ID in it is
unresolvable**, so a rejection identifies no particular ID. The resolver
bisects a rejected batch until bad IDs are isolated, and only IDs proven bad
alone are remembered as invalid.

The subtlety, and the reason most of TriffView's tests are here: ESI also
returns 404 for a route-level failure — a moved or renamed endpoint — with a
plain-text body. Treating that as invalid-IDs would bisect the whole set and
permanently blacklist every character the user has. So the two are separated
by response *shape*: a JSON object carrying a non-empty `error` string is the
invalid-IDs rejection; anything else that 404s is transient. Matching on shape
rather than wording means CCP can reword the message without breaking it.

A transient failure never bisects and never poisons the cache — it says
nothing about validity. Those IDs are simply left unresolved and retried on
the next state build.

Transport is stdlib `urllib.request`, following `discord.py:11-12,253`. Wingman
declares no general-purpose HTTP client — the Google stack brings `httplib2`
along for its own use (`pyproject.toml:26-30`), but nothing in the app calls a
request library directly — and one POST does not justify adding `requests`. The
batch fetch is injected as a parameter, so the whole bisect is testable against
fixed status/body pairs with no network.

Names are cosmetic. Every failure degrades to `Character 98123456` and is not
surfaced as an error; the tool is fully usable offline.

**Accounts never resolve.** A `core_user_*` ID is an EVE account ID, not an
ESI entity, and always renders as `Account 12345`. With notes deferred,
account rows are distinguishable only by ID and modification time. Acceptable
— you have a handful of accounts and dozens of characters — but it is a known
rough edge, listed in Scope.

### `backup.py`

Backups live at `state_dir() / "eve-settings-backups"`, beside `settings.json`
and the token. Never inside the EVE tree: that directory belongs to CCP, and
writing archives into it risks confusing the launcher and losing every backup
to a reinstall.

**The filename is the index.**

```
20260824-123456-000-auto-character-a1b2c3d4-core_char_98123456.zip
└ UTC ────────┘ └seq┘ └origin┘ └ kind ┘ └src┘ └──── stem ────┘
```

This closes two of TriffView's defects at once.

The sequence number makes two backups inside the same second distinguishable —
the collision that aborts a 40-target copy partway (finding 2).

And because origin, kind, source and stem are all in the name, **listing
backups is one `listdir` and a parse; no archive is opened** (finding 3). The
manifest stays inside the zip and remains authoritative for the full source
path, which is too long and too path-shaped to encode in a filename. Restore
opens exactly one archive: the one being restored.

`kind` is `character`, `account`, or `profile`. `src` is the first 8 hex
characters of a SHA-256 over the normalised absolute path of the source's
**parent profile directory**.

That `src` segment is not decoration. `core_char_98123456.dat` exists in
*every* settings set, so a grouping key built from the stem alone would treat
backups of one character across two profiles as the same source — and backing
that character up from `settings_Alt` would prune the rollback history
belonging to `settings_Default`. The grouping key is `(kind, src, stem)`, and
only that triple.

**Archives are staged, then published.** The final name is claimed with
`O_CREAT | O_EXCL` so no two writers can pick it, the archive is built to a
staging file beside it, and `os.replace` moves it into place on success; a
failure unlinks the staging file and the claimed name.

Claiming alone is not enough, and the repository already knows why:
`combatlog.build_archive` stages exactly like this because "a run that dies
partway must not leave a truncated archive that reads as a complete export"
(`combatlog.py:283-324`, with a regression test at
`tests/test_combatlog.py:349-361`). Since listing here is filename-only, a
half-written archive left under its final name would be presented to the user
as restorable — which would contradict this design's own outcome statement.
Claim for collision-safety, stage for integrity; the two compose.

**Pruning** groups auto-backups by `(kind, src, stem)` and keeps the newest
`auto_keep` within that group. Manual backups are never pruned, and are
distinguishable without opening anything because origin is in the name.
Pruning runs after any operation that created an auto-backup — a copy or a
restore — never on a timer. TriffView prunes nothing at all, and since every
copy auto-backs-up, a single "copy to all others" across 40 characters leaves
40 archives behind forever.

**Restore.** Two paths.

*File restore* replaces one `.dat` from its archive.

*Profile restore* is the most destructive operation in the feature, and runs
in this order:

1. Validate the manifest's recorded target still sits under the current root.
2. **Validate every archive entry before touching anything.** Each name must
   flatten to a bare `core_*.dat` (or the manifest itself); anything else —
   a nested path, an absolute path, a `..` component, an unexpected file —
   fails the whole restore before a single deletion. Validation is complete
   and up-front, not interleaved with extraction, so a bad archive cannot
   leave the profile emptied and half-repopulated.
3. Auto-backup the existing profile. **A failure here aborts the restore** —
   this backup is what makes step 4 recoverable.
4. Delete every `core_*.dat` in the target directory.
5. Extract.

Step 4 means files that were in the profile but not in the backup are gone;
step 3 is why that is survivable. Archive entries are flattened through
`os.path.basename` on extraction as well — belt and braces behind step 2's
allowlist, since flattening alone would silently *accept* an unexpected member
rather than reject it.

A backup taken under a different root, or after the user repointed the folder,
fails containment and says so rather than restoring somewhere unexpected.

### `ops.py`

`copy_to_targets(source, targets)`. For each target in turn:

1. Verify the kind matches — character settings only onto character settings,
   account onto account.
2. Back the target up. **If this fails, the target is skipped untouched** —
   never overwrite something that could not be protected first.
3. Write.

A failure at step 3 is recorded and **the loop continues**. The result is a
report of per-target outcomes, in the shape `library.delete` established:
what succeeded, what failed, and why (`ui/api.py:405-411`).

This is a deliberate divergence. TriffView throws on the first failure,
leaving an unknown mix of copied and uncopied targets, and discards the count
it computed.

The source is filtered out of its own target list and duplicates are collapsed
before any work begins.

**Writes go temp-then-replace.** The temporary file is created in the
destination directory — `os.replace` is only atomic within one filesystem —
and replaced over the target, reusing the bounded retry loop from
`atomicio.write_atomic`. That retry exists because Windows raises a sharing
violation when the destination is held open by a reader that did not grant
`FILE_SHARE_DELETE`, and EVE holds `core_*.dat` open. It needs a binary
sibling; the existing function is `str`-only (finding 5).

The trade-off, stated plainly because users will meet it: `os.replace` needs
`FILE_SHARE_DELETE` from whoever holds the file, which is a rarer share mode
than a plain copy requires. **This will refuse in cases where TriffView would
have succeeded.** That refusal is the better outcome — a copy that "succeeds"
into a running client is silently reverted when EVE writes its settings back
on logout — but it means the error message must say *close EVE and retry*
rather than reporting an OS error code.

## Persisted state

A `validated_eve_settings()` section in `settings.py`, following the shape the
other nested sections already use — a fresh dict every call, never the module
global, unknown keys dropped by construction:

```python
{"root": None, "server": None, "profile": None, "auto_keep": 10}
```

Three remembered paths and the prune depth. `auto_keep` has no UI control in
the first slice — it is a settings value so that it *can* move, not because
anything yet moves it. Everything else is derived from disk on each state
build, so there is nothing to migrate and nothing that can drift out of step
with reality. The paths are re-validated on load: a folder that vanished
between runs resolves to `None` and the UI shows the folder picker rather than
a broken selection.

This is one section in `settings.json` rather than a separate file, matching
every other feature in the app.

**Selection writes read, merge, and save — they do not save a snapshot.**
`_SAVE_LOCK` serializes the final projection and write (`settings.py:180-189`);
it does not make the surrounding read-modify-write atomic, and callers that
build a payload from a stale copy before acquiring it can silently revert
another writer's key (`ui/api.py:1055-1066` constructs `cfg` from
`self._state.settings` and then saves it). Since `save()` projects the complete
document from `DEFAULTS`, a lost key is not a corrupt file — it is a setting
that quietly reverts, which is far harder to notice.

The pattern to follow already exists: `preview/store.py:56-68` re-reads the
live settings, merges its own section into that, and saves the result. This
feature owns exactly one section and writes it only on an explicit user action,
so the contention window is small — but "small" is what the preview store
thought too, before three writers existed.

TriffView keeps its own `%APPDATA%\TriffHud\eve-settings.json`, and its notes
dictionary keys profile notes on the full path, so renaming a settings set
orphans its note. Notes are deferred here; when they land, they should key on
something stabler.

## User interface

One flat route — a fourth button beside Uploader, Bookmarks and Previews.
Wingman's navigation has no sub-navigation anywhere, and introducing an inner
sidebar for one feature is not worth the inconsistency. TriffView splits this
across five inner sections (Overview, Characters, Accounts, Backups,
Advanced); the first slice needs three of them and they fit on one screen.

Top to bottom:

- A header strip: root folder with a picker, server and settings-set
  selectors, and an *EVE running* / *EVE closed* pill.
- A Characters ↔ Accounts toggle over a source picker and a target checklist,
  with search, select-all/none, and a Copy button.
- A Backups panel: list, restore, delete, and back-up-this-profile.

**The EVE-running pill is advisory**, matching TriffView. Detection reuses
`preview/discovery.py`, which already resolves a window's PID to an executable
name, compares it against `CLIENT_IMAGE = "exefile.exe"`, treats an
unopenable process as "not a client" rather than an error, and caches the
lookup per PID (`preview/discovery.py:16,39-51,92-139`). If the pill only needs
"is any client running", that is `list_clients()` — otherwise the image-name
helper is worth extracting rather than reimplementing.

Not `procid.py` or `evewindows.py`: the first describes one already-known PID
through PowerShell (`procid.py:21-51`) and the second enumerates window titles
(`evewindows.py:80-98`). Neither does an executable-name match, and reaching
for them would mean rebuilding what discovery already has.

Nothing is blocked — the copy explains itself if it fails.

**Confirmation is real, not cosmetic.** Every destructive operation runs on a
worker thread and blocks on `_confirm()` before touching anything. Worth
recording because in TriffView the modal is frontend-only: a message posted
directly to the bridge executes unconfirmed, leaving the containment
validators as the only actual defense. Here the containment checks still run
regardless, but the confirmation sits on the same side as the work.

## Error handling

Two channels, matching what the app already does.

User-facing failures go through `_alert("error", ...)` or a status push, and
say what to do: *"Could not copy to 3 of 40 characters. EVE may be running —
close it and retry."* Failed targets are listed by character name, not by path.

Diagnostics go to `logger.exception(...)`, landing in `state_dir()/logs`.

TriffView has neither: raw exception messages, full filesystem paths included,
are posted straight to the UI, and nothing is logged.

Smaller edges, all decided:

- Copying a file onto itself is filtered out, not an error.
- Switching profile clears a stale source selection rather than carrying it.
- A root that vanished between runs shows the folder picker.
- An unreadable folder says so instead of reporting no settings sets.
- Transient ESI failures are silent and retried; only IDs proven bad alone are
  remembered.

## Testing

The module split exists to make this possible. TriffView has **no tests on any
file operation** — all 16 are on the name resolver — so there is nothing to
port here except the resolver's own suite, which is worth porting closely.

| Module | Covered |
|---|---|
| `tree.py` | A fake EVE tree in `tmp_path`: discovery, the digits-only ID rule, server canonicalisation, self-healing root, and every containment case including `..` traversal, the `C:\EVE-evil` prefix confusion, and a symlink beneath the root pointing outside it. |
| `names.py` | `classify_response` against fixed status/body pairs (JSON-`error` 404 vs plain-text 404); `resolve` against a fake batch fetch, asserting a bad ID bisects to isolation while a transient failure neither bisects nor poisons the cache. |
| `backup.py` | Create/enumerate/restore round-trip; two backups in the same second both survive with distinct names; a failure mid-build leaves neither a staging file nor a claimed name behind, and enumeration does not list it; pruning keeps newest-N within `(kind, src, stem)` while never touching manual backups **and never pruning across two profiles holding the same character**; an archive carrying an unexpected or path-bearing entry is rejected before any deletion; a manifest whose target no longer sits under the root fails containment. |
| `ops.py` | Kind mismatch refused, source excluded from its own targets, duplicates collapsed; failure paths driven by injecting a failing backup or write — backup fails means target untouched, write fails means reported and the loop continues. |
| `ui/api.py` | Thin delegation, the worker-thread/confirm wiring, and the mutation lock: a second mutation attempted while one holds the lock is refused rather than interleaved. Follows `tests/test_api_bookmarks.py` and `tests/test_preview_wiring.py`. |
| `settings.py` | `tests/test_settings_evesettings.py`, beside `test_settings_eve.py` and `test_settings_preview.py`. Includes a read-merge-save round trip asserting that writing the selection does not drop a key another writer set. |

`test_packaging_completeness.py` already fails if the new package is not
declared; no new test is needed for that.

**What cannot be tested here.** The Windows sharing-violation behaviour when
EVE holds a file open, and the real `os.replace` retry. These go on
`docs/smoke-checklist.md`:

- Copy with EVE closed — succeeds, target updated, backup written.
- Copy with EVE running — fails with the *close EVE and retry* message, and
  the target is left intact.
- Restore the pre-copy backup — the original settings come back.
- Profile restore — the settings set is replaced, and the pre-restore backup
  contains what was there before.

## Scope

**First slice:**

1. Browse root → server → settings set, with the folder picker and
   self-healing selection.
2. List character and account settings files, with ESI-resolved character
   names.
3. Copy one file onto many kind-matched targets, auto-backing-up each and
   reporting per-target outcomes.
4. Back up a settings file or a whole settings set.
5. List, restore and delete backups, with auto-backups pruned to the newest
   `auto_keep` per source.

**Deferred, in rough priority order:**

**6. Notes.** Free-text labels on characters, accounts and settings sets. The
only labelling mechanism for accounts, which cannot be name-resolved, so this
is the first thing to add. Key them on something stabler than the full path —
TriffView's profile notes orphan themselves on rename.

**7. Settings-set management** — create, duplicate, rename, delete. Delete
auto-backs-up first in TriffView; create is the one mutating operation it does
not confirm, which should not be copied.

**8. Multiple named profiles for the tool's own selection**, so a user
switching between setups does not re-pick root/server/set each time.

**9. A backup-size indicator and bulk delete**, once enough backups accumulate
for pruning depth to be something a user wants to tune.

**Explicitly excluded**: parsing or rewriting the contents of a `.dat`. The
files are copied byte-for-byte and never interpreted. This matches TriffView's
own stated position — its confirmation dialog says so in as many words — and
should not be quietly crossed: the format is undocumented, version-specific,
and corrupting it costs a user their entire UI layout.

## Risks and open questions

1. **`os.replace` may refuse more often than expected.** The share-mode
   reasoning above is sound, but which share mode EVE actually requests has
   not been measured. If refusals turn out to be common even with EVE closed,
   the fallback is the third option considered and rejected during design:
   attempt temp-then-replace, and on a lock failure specifically, offer a
   direct overwrite behind an explicit second confirmation. The smoke checks
   are what will reveal this.

2. **Server-name canonicalisation is a substring match** on a fixed list of
   shard names. A new shard renders under its raw folder name — degraded, not
   broken, and the folder is still selectable.

3. **`auto_keep` defaults to 10 with no evidence behind the number.** It is a
   settings value precisely so it can move; the cost of it being wrong is disk
   use in one direction and a lost rollback in the other.

4. **Profile restore deletes files the backup does not contain.** Called out
   again here because it is the one operation whose blast radius exceeds what
   its name suggests. The pre-restore auto-backup is the mitigation, and its
   failure aborts the restore.
