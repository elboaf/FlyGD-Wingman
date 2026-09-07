# Overview and window-layout sharing: discovery

Date: 2026-09-07
Repository baseline: `a38c7a0` — Extract ProfilesController and preserve current Formations contracts (#175)
Status: evidence and approved product direction, **not an implementation specification**.

## Approved direction

The next phase combines overview configuration and supported character window
layout in a Wingman-specific preset. Native EVE YAML is a limited compatibility
input, not a complete setup-sharing format. The curated library remains deferred.

The user approved:

- Account-level overview configuration and overview-window/tab grouping.
- Character-level window layout.
- Preserving custom ship-label order and multiplicity.
- Explicit preview and apply, rather than automatically merging active setups.
- Preserving recipient-local display settings, rather than importing sender
  hardware preferences or accidentally resetting a new profile to EVE defaults.

Complete setups still default to a new profile. The exact supported window set,
display-mismatch policy, and publication workflow must be settled in the design.
Probe copy/paste was reported working by the user; that is not a sign-off on every
outstanding probe-sharing smoke-check item.

## Evidence and limits

Inspection was authorized by the user. Original account/character files were
read into snapshots and decoded with the existing native codec. Raw settings,
account/character identifiers, user labels, and launcher application bundles are
not fixtures and must not be committed. Private experiment snapshots and hash
manifests remain outside the repository in the user's Windows temporary folder.

The user supplied a current EVE export and performed a native import into `Test`.
There is no captured fresh, pre-import `Test` baseline. Consequently, the result
can be compared with the export and sender reference; it cannot establish every
change caused by import separately from EVE startup/default initialization.

An earlier assistant-prepared profile cloned the sender's existing configuration.
That was **not a valid blank-profile import test** and must not be cited as one.
Its retained files are usable as a sender reference only.

### Export and imported result

| Component | Supplied YAML | Saved native-import result |
| --- | --- | --- |
| Custom filter definitions | 42 | All 42 definitions match |
| Tabs, filter/bracket references, per-tab columns and ordering | 8 | All eight tab records match |
| Additional saved presets | No `DefaultPreset_*` entries | 36 `DefaultPreset_*` entries alongside the imported 42 |
| Overview-window assignments | Absent | `tabsByWindowInstanceID` absent |
| Internal window geometry | Absent | Only one overview window recorded on the populated character |
| Ship-label entries | 9, including four with null type | 6, including only one with null type |

The six retained labels' `pre`/`post` values match corresponding exported entries.
This round trip did not preserve the sender's label multiplicity. The export also
sorts label records differently from the sender's stored sequence; its separate
`shipLabelOrder` repeats null, so treating labels as a dictionary keyed by type
loses information. A Wingman preset needs an ordered list, not that dictionary.

The native YAML has 13 root fields and is 182,366 bytes. It therefore already
exceeds probe sharing's 64 KiB input limit. Measure native and Wingman transport
sizes separately; this is not justification for an unbounded parser.

The file contains no YAML aliases. That does not establish whether community
packs require aliases or which bounded YAML subset the compatibility importer
should support.

Only `useSmallColorTags` occurs in this export's `userSettings` list. It is not a
complete enumeration of persisted overview options. Missing-option reset versus
preservation semantics remain unproven without an appropriate before/control.

### Account overview storage

Observed `overview` entries include:

- `overviewProfilePresets`: named definitions with `groups`, `filteredStates`,
  and `alwaysShownStates` integer lists.
- `tabsettings_new`: tab records with `name`, `color`, `overview`, `bracket`,
  `tabColumns`, and `tabColumnOrder`.
- `tabsByWindowInstanceID`: lists of tab indices. The sender reference has three
  groups; the native export has none.
- `shipLabels`: an ordered list with repeated null-type literal entries and both
  older and newer formatting-field shapes.
- Colour, blink, state-order and state-membership settings. Native colour names
  map to EVE-specific numeric colours, not ordinary CSS named colours.

The section also contains unsaved filter overrides, active selection, history and
restore data. `defaultoverview` has separate default-profile identifiers. Do not
copy either whole section or assume all of its fields belong in a public preset.
The supplied YAML matches saved definitions rather than the observed unsaved
filter override; Wingman's export policy for such overrides needs to be explicit.

### Character layout storage

`windows.windowSizesAndPositions_1` contains six-integer tuple records in the
inspected sender-reference corpus: 6,141 occurrences across 41 character files.
Many files contain duplicated settings, so this is not 41 independent layouts.
The last two values vary between saved windows, including within one character;
a single current display size cannot be assumed to describe every cached record.
Coordinate interpretation and cross-resolution adaptation are not yet verified.

Related maps include `openWindows`, `minimizedWindows`, `collapsedWindows`,
`compactWindows`, `lockedWindows`, overlay/background preferences, stack
membership and preferred stack position. Geometry alone is not a complete layout.
There are also layout-related fields outside this section, including info-panel
modes. Their presence is not approval to copy the entire character UI document.

Window keys include both recognizable general-purpose windows and dynamic keys.
An alphabetic-looking key is not a portability guarantee. A supported-window
allowlist and dependency rules must exclude personal channel associations,
item/ship identities, unrelated dialogs and history. Stale cached overview-window
records must not create extra active windows merely because geometry exists.

### Recipient-local display state

The ordinary profile and the first cloned test differed in `core_public__.yaml`:
the ordinary profile had explicit windowed UI scaling and saved window dimensions;
the test had automatic scaling and unset windowed dimensions. The cloning helper
had copied only account/character DAT files, leaving EVE to initialize local
preferences. It did not explicitly resize an EVE client, but it did not preserve
the full local display environment either.

The complete-setup constructor must preserve verified **recipient-local**
preferences. Neither `core_public__.yaml` nor `prefs.ini` belongs in the shared
artifact. Do not broaden ordinary profile-copy/backup semantics incidentally.

## Launcher discovery: separate from file copying

The installed EVE launcher 1.16.1 application code was inspected read-only. Its
bundled `.webpack/main/index.js` contains a disk scan that:

1. Chooses settings-server directories corresponding to the configured shared
   cache and supported tenant.
2. Enumerates child directories whose names start with `settings_`, excluding
   the default name from the additional-profile list.
3. Updates the launcher's in-memory profile list through `setProfiles`.

The scan runs at startup and is exposed through an `updateProfilesFromDisk` IPC
action. This scan does **not** require a `prefs.ini` or `core_public__.yaml` file.
No account/auth stores, launcher logs or tokens were inspected or changed.

This explains why Wingman's filesystem discovery is insufficient evidence of
immediate launcher visibility. The workflow must include an explicitly verified
launcher refresh/restart step; do not invent a registration-file write or claim
that a missing local preference file caused the missing launcher option. The
original folder has not been rechecked in the launcher after a restart.

## Current repository integration boundaries

- `wingman/evesettings/controller.py` now owns Profiles orchestration;
  `ProfilesPorts` supplies effects and `ui/api.py` remains the bridge facade.
  Do not build new workers back into the old monolithic API implementation.
- `profilecopy.prepare_copy`, `stage_copy` and `publish_new` provide validated,
  non-discoverable staging and new-directory publication. Prepare every component
  before publishing; do not publish a profile and then patch its DAT files.
- `tree.file_kind` deliberately recognizes only account/character DATs. Existing
  profile-copy staging omits local YAML/INI; existing backups do not cover new
  writes to those files. Extending that classifier would affect unrelated roster,
  backup, restore and deletion behavior.
- Codec content revisions guard individual files. A reviewed multi-file source
  snapshot and staged-publication contract must be explicit for a complete setup.
- Existing-profile rollback is not a crash-atomic multi-file transaction. The
  new-profile-first policy avoids promising that independent file writes are
  atomic together.
- Account-character identity links do not prove both local files exist. Review
  and apply must bind to exact local targets and revalidate them.
- Selective copy clones a sender document before restoring exclusions. It is not
  a safe export projection or an external-data import implementation.

## Remaining design decisions and acceptance gates

1. Define the coherent first supported window set and its required flags, stacks,
   overview groups and other dependencies. Do not call arbitrary DAT cloning
   complete portable layout support.
2. Decide how different resolutions/UI scales are handled. Preserve recipient
   display settings; do not claim automatic fitting before it is implemented
   and verified. Never move or resize a running EVE client.
3. Define ordered label serialization and saved-versus-unsaved filter semantics.
4. Define recipient-local seeding, missing local-file policy, new-profile staging,
   launcher visibility and failure recovery without changing existing profiles.
5. Make YAML limitations visible before apply; do not silently advertise it as
   equivalent to a full Wingman preset.
6. Validate the actual Wingman import into a genuinely fresh recipient baseline,
   not a sender clone. Separately test replacement against a deliberately
   different setup. Record startup/control limitations accurately.

## Verification performed for this discovery

- Native decode and structural comparisons on authorized snapshot bytes.
- Exact matching of exported filter/tab contents to a sender account reference.
- Read-only inspection and retention of the user's saved native-import result.
- Read-only inspection of installed launcher profile-scan code.
- New worktree at `a38c7a0`: `uv sync --locked --extra dev` succeeded.
- Baseline `uv run --no-sync python -m pytest tests/ -q -rs`:
  **6,875 passed, 37 skipped**. Nine skips require Windows; 28 require a native
  codec binary not installed in this worktree. This is a baseline, not evidence
  that an overview/layout importer exists or passes acceptance.
