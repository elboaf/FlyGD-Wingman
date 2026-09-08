# Wingman overview and in-space layout presets

Date: 2026-09-07
Status: approved design; pure model/parsers, current-client export/application (Task 4b) and hidden recipient staging (Task 5) implemented. No controller/UI publication integration yet. See the [implementation plan](overview-layout-sharing-plan.md), [parser checkpoint](overview-layout-sharing-verification.md) and [application checkpoint](ui-setup-application-verification.md).
Base: `a38c7a0` plus the discovery record committed in `ed6aa16`.
Evidence: [overview/layout discovery](overview-layout-sharing-discovery.md).

## Goal and approved decisions

Give another player a usable overview and supported in-space window layout,
without exchanging account files or silently changing their display settings.
The primary artifact is a Wingman preset, not EVE's native YAML.

Approved behavior:

- Bring layout sharing forward into the overview-sharing phase.
- Preserve overview configuration, window/tab grouping and ordered ship labels.
- Preview before explicit apply; no automatic merging of active setups.
- Keep native YAML as a visibly limited compatibility input.
- **Copy saved layout geometry as-is.** Do not implement automatic fitting.
- Preserve recipient-local resolution, display mode, monitor preferences and UI
  scaling. Warn that different resolutions/scales can require manual adjustment.
- Never move, resize or otherwise manipulate a running EVE client for this work.

The scope below is deliberately named an **overview and in-space layout preset**,
not a byte-for-byte copy of the entire EVE UI. Chat associations, arbitrary window
stacks, identity-dependent windows and every remembered dialog are not included.

## User flow

### Export

In Profiles, choose one source character and its confirmed account in one local
profile, then open **Share setup…**. Both local DAT files must exist and the
account-character association must be confirmed; do not guess from timestamps.

With EVE closed, read a consistent snapshot and show what the preset contains:
filters, tabs, overview-window groups, ship labels and supported layout windows.
Show any unsupported layout dependency as a blocking error, not a silently
missing part of a successful export.

Copy produces a versioned JSON text artifact. Save file produces the same UTF-8
artifact. Neither operation writes EVE settings. Clipboard success follows the
actual clipboard promise, not merely successful serialization. User-authored
names and label markup travel as text; export is not an anonymization service.

The exported filter definitions represent the effective persisted snapshot:
the present `overviewProfilePresets_notSaved2` map (even empty) takes precedence
over `overviewProfilePresets_notSaved`; only when the second map is absent does
the first apply. Effective entries override selected saved definitions of the
same name in the exported copy. Show a warning/count when this occurs. Do not
save those changes back to the sender, export the cache itself, or imply that
unflushed changes in a running client were captured.

### Review and create

Open **Import setup…** in Profiles and paste text or choose a local file. Select:

1. A recipient-local base profile whose ordinary preferences should be retained.
2. One recipient character and its confirmed account, both present in that base.
3. A new profile name.

The first release creates a **new profile only**. It does not replace an existing
profile in place. Existing local copy tools remain available for subsequent
trusted distribution to more alts; fleet-wide role mapping is not added here.

Review shows the artifact type, included components, target character/account,
new profile name, and the configuration changes within the proposed new copy.
Account-level changes affect other characters of that account if they later use
this new profile; state this explicitly. No account or character IDs from the
sender become destination filenames or identity mappings.

The permanent display notice is:

> Your resolution and UI scale stay unchanged. This layout is copied as saved;
> a different display size or UI scale may need manual adjustment in EVE.

**Create profile** is the sole commit action. Cancel changes nothing. After
publication, say that the profile was created and explain that restarting the
launcher refreshes its profile list. Do not imply that Wingman selected it in the
launcher, and do not restart the launcher or launch EVE automatically.

A native-YAML review must say **Overview configuration only — no window layout**.
It must never acquire a layout component from recipient data and present that
component as having come from the file.

## First supported layout set

The initial allowlist covers the in-space windows observed in the sender layout:

| Logical window | EVE identifier |
| --- | --- |
| Overview instances belonging to the imported tab groups | `overview`, `overview_<ordinal>` |
| Selected item | `selecteditemview` |
| Probe scanner | `probeScannerWindow` |
| Directional scanner | `directionalScannerWindow` |
| Drones | `droneview` |
| Fleet | `fleetwindow` |
| Watch list | `watchlistpanel` |
| Standalone bookmarks | `standaloneBookmarkWnd` |
| Solar-system map | `solar_system_map_panel` |
| Primary map | `primary_map_panel` |

This list is a product allowlist, not a regex accepting every alphabetic window
name. It is defined once in source and used to derive labels and test cases.
Dialog history, inventory/item-specific windows, personal chat windows, channel
membership, Neocom configuration, info-panel modes and ship-specific module
arrangements remain outside this first preset type.

For each included window, preserve its saved geometry and the supported saved
open/minimized/collapsed/compact/locked/overlay/background state. Distinguish an
absent setting from an explicit false value; absence in the source resets that
particular included-window override in the new recipient copy rather than
retaining a contradictory recipient override. Leave unrelated windows alone.

Geometry is an explicitly validated six-integer EVE geometry record, rebuilt as
a known tuple by the internal adapter. Preserve all six values; do not reinterpret
or rescale them. This does not promise identical rendered pixels on a different
client version, resolution or UI scale.

Active overview instances come from the account's tab-group structure, not every
cached `overview_N` geometry key. Retire surplus recipient overview instances in
the new copy so old windows cannot appear with missing or unrelated tabs. Validate
that each included tab belongs to exactly one nonempty overview-window group and
that required overview geometry exists in the source character.

**Initial stack limitation:** supported windows must be unstacked. If an included
or otherwise affected window (including a surplus overview instance being retired)
has a non-null stack association, refuse export or application with the specific
affected window names. Do not silently detach a mixed stack or copy sender-local
stack IDs. Stack support requires its own dependency/remapping work.
This limitation must appear in review/help, not only in an error encountered late
in a write.

The observed account `ui.targetOrigin` / `targetOriginLocked` and character
`windows.shipuialignleftoffset` are additional explicit layout fields: preserve
the saved target-origin pair, lock flag and horizontal HUD offset as-is. They are
not permission to copy either containing section wholesale. Other HUD settings
are not inferred from similarly named keys.

## Portable data and fidelity

Use the existing `wingman-preset` envelope with a new `ui-setup` type and version
1. Formation artifacts and their existing parser remain unchanged. A setup has
separate overview and character-layout components under one artifact; it contains
no raw DAT document, codec envelope, source path, account/character ID, checksum,
content revision, local timestamps, history or hardware preference file.

The overview model contains:

- Explicit named filter definitions: group membership, filtered states and
  always-shown states. Names and references retain exact text, not casefolded or
  automatically renamed equivalents.
- Ordered tabs with names, colours, overview/bracket filter references and per-tab
  column selections/order and showAll/showNone/showSpecials bracket flags. Full
  export materializes client column defaults; native column omission retains
  recipient physical-slot overrides/presence.
- Explicit overview-window grouping using artifact-local ordinals and tab IDs.
- Ordered ship-label records, preserving repeated null-type literal entries and
  supported formatting fields. Never turn them into a type-keyed dictionary.
- Explicit supported appearance/state settings and their presence/absence, not
  the entire `overview` section.

Export all supported custom filter definitions plus the definition dependencies
of the included tabs. Resolve references before producing an artifact. Only
explicitly understood EVE sentinel references may remain external. A missing or
ambiguous definition refuses the operation.

Apply the incoming active configuration as one coherent replacement in the new
recipient copy. Exact-name incoming filter definitions replace matching custom
recipient definitions; preserve unrelated saved definitions so other local uses
are not gratuitously destroyed. This is not a union of old and new active tabs,
styles or window groups. Remove stale unsaved overrides for imported definitions.

Do not overwrite recipient default-profile identity or built-in definitions by
assuming every named entry is custom. If an incoming definition conflicts with a
protected built-in definition, require the versioned public canonical fingerprint
for the incoming body and any recipient collision; equality of two incorrect
saved bodies is not enough. The first supported context is exactly Jotunn, with
its exact stored-name domain; prefix/case/legacy-name lookalikes are custom.
Missing protected source bodies are not reconstructed from hashes. See the
[current-client evidence](ui-setup-client-evidence.md) for provenance and rules;
otherwise refuse the affected case with an actionable explanation. Do not silently rename references.

The adapter must explicitly handle load-bearing selection/cache references to
replaced data. It may reset only specifically understood references to a valid
imported selection. No wholesale deletion of `ui`, `tabgroups`, `defaultoverview`
or history is permitted as a cache-invalidation shortcut. The mapping and tests
must precede enabling publication; unproven dependencies block the affected case.

## Native YAML compatibility

Use a maintained YAML parser, with a safe, bounded loader, rather than a custom
YAML implementation. Add PyYAML as a justified locked dependency for this input.
Reject custom tags, anchors/aliases, duplicate mapping keys and unsupported
structures before constructing an importable model. Accept only the documented
native settings/filter/tab shapes covered by fixtures; do not accept arbitrary
Python YAML object constructors or arbitrary settings dictionaries.

Normalize into the same explicit overview model, never into a decoded DAT blob.
Use native order arrays for their documented purpose; do not use dictionary
construction where order or duplicate entries would be lost.

EVE intentionally omits built-in filter bodies from native export
(`GetPresetsInUse:883`, `ShouldAddPreset:892`). Native-only exact Jotunn
external overview/bracket references are allowed; apply revalidates them and
requires supported context plus available saved recipient bodies verified by the
public canonical fingerprints. Missing/noncanonical saved bodies refuse; never
reconstruct bodies from hashes or fall back to arbitrary recipient customs.
Referenced external names count as imported names for narrow cleanup in both
present unsaved maps: validate affected override shapes, remove only imported
names, and preserve unrelated entries/presence and canonical saved records.
Malformed affected overrides refuse. Full Wingman closure remains strict.

A YAML file with ambiguous repeated ship-label types cannot reproduce the original
label sequence. Require the user to explicitly choose **Keep my ship labels** to
import its other supported configuration; otherwise block Apply and recommend a
Wingman preset. No silently dropped labels or guessed decorator ordering.

YAML has no window grouping in the measured format. Present its tabs as one group
in the primary overview window. Review must state this before apply. Keep the
recipient's primary overview geometry and other non-overview window geometry;
close surplus overview instances in the new copy. This is a visible compatibility
policy, not a claim that source window layout was reproduced.

Missing native options must not be treated as a complete set of explicit values.
Preserve recipient values for absent scalar options and show this policy in the
configuration-only review. A supplied supported aggregate such as a colour/state
configuration replaces that aggregate; an absent aggregate is retained. This is
Wingman's declared compatibility behavior, not an unverified claim about EVE's
native reset semantics.

## Validation and resource limits

Both inputs have a 2 MiB UTF-8 byte ceiling, maximum nesting depth 16 and a total
100,000 parsed-node budget. Enforce the byte ceiling before decoding. Preflight
YAML events for forbidden constructs and depth/node budgets before construction;
for byte-bounded JSON, catch decoder recursion failures and check structural
budgets immediately after decoding, before domain conversion. Do not promise a
pre-allocation JSON node limit the standard decoder does not provide. Error
messages name the violated limit; nothing is truncated. These are parser budgets,
not claimed EVE game limits.

Version 1 is a bounded supported subset: at most 256 filter definitions, eight
tabs and eight nonempty overview groups, 64 label records and 32 layout records.
Reject rather than truncate larger setups; these are Wingman support limits, not
a claim about EVE's maximum capabilities. Require unique logical keys and valid
reference closure. Group/state IDs must be nonnegative signed-32-bit integers,
not booleans; each membership list is capped at 8,192 IDs. Preset `groups`,
`filteredStates` and `alwaysShownStates` retain repeated IDs: client
`ReorderPresets:279` / `ReorderList:92` sorts without deduplication and state getters
return lists. This relaxes only preset membership uniqueness validation, not other
logical-key/ID uniqueness guards; public defaults have no repeated state values.
Names are capped at 512 Unicode code points and individual label text fields
at 4,096.

Geometry's first two saved coordinates must be within -32,768 to 32,768; its four
size/reference-size entries must be positive and at most 32,768. The target-origin
pair must be finite and within 0–1, and the supported integer HUD offset within
-32,768 to 32,768. Unsupported records refuse as a whole; none of these checks
clamps a coordinate or fits it to a display.

Domain validation additionally rejects non-finite values, booleans masquerading
as numbers, lone surrogates/NUL text, unsupported field variants and dangling
references. Supported enum/record variants must be explicit in the pure model
and tested against the real observed shapes and sanitized fixtures. Do not guess field formats from names. Refuse an unsupported
variant instead of discarding it or rebuilding a default configuration.

User text and EVE label markup are rendered with text properties in Wingman's
review, never evaluated as page HTML. No URLs are fetched and no payload can name
an input/output filesystem path or request another profile operation.

## Recipient-local construction and publication

Keep orchestration in `wingman/evesettings/controller.py`, using `ProfilesPorts`.
`ui/api.py` exposes thin bridge delegates. Pure overview/layout adapters and the
portable parser live under the existing `evesettings` package; do not add a generic
preset registry, profile service, framework or competing controller.

Publication sequence:

1. Bind review to the parsed artifact, selected base profile, exact recipient
   account/character files, confirmed association and proposed destination name.
2. Record a source manifest of all base-profile files that will be copied, with
   exact-byte revisions, including local preference files. Identity links alone
   are not proof that the requested local files exist.
3. Under the existing nonqueued mutation lock, fail closed unless EVE is confirmed
   closed. Revalidate the reviewed paths, association, name and manifest.
4. Stage recognized recipient account/character files in a non-discoverable
   directory. Stage the recipient base's `core_public__.yaml` and `prefs.ini`
   byte-for-byte as local preferences, never from the artifact.
5. Refuse creation if either required local preference file is missing or cannot
   be copied safely. Do not synthesize resolution/scaling defaults. Explain that
   a normally initialized recipient base profile is required.
6. Apply the pure model to copies of the selected recipient documents, preserving
   unrelated sections and recipient identities. Verify codec encode/decode
   round-trips before any destination publication.
7. Recheck the complete base manifest, artifact/review identity, destination
   nonexistence and EVE-closed state, then publish the completed directory once.
8. Report creation separately from remembering Wingman's selection or any later
   housekeeping warning. A post-publication failure must not say nothing changed.

Use the established `profilecopy` staging/publication mechanisms where they fit,
with a narrow constructor for this richer local seed. Do not broaden
`tree.file_kind()`, which would change roster, ordinary backup/restore and deletion
semantics. Do not use the existing DAT-only backup format to claim YAML/INI coverage.
No existing profile is modified, so recovery is selecting the old profile rather
than rolling back a half-written multi-file replacement.

Revisions are optimistic checks, not a promise of an atomic compare-and-swap
against arbitrary external writers. Refuse observed changes and require fresh
review; never automatically merge/rebase the reviewed setup onto changed files.

## Page lifecycle and failure behavior

Keep this as a Profiles tool, not a new title-bar destination. Respect the ES5
page conventions, handler allowlist, page-owned confirmations, wrapped controls,
explicit hidden/display rules and the 840x625 logical-pixel floor.

Import candidates remain separate from live profile state. Source/recipient
changes, new pasted text, cancellation and route exit invalidate earlier results.
Use distinct request identity and view generation; stale replies must not select
a profile, enable an old Apply action or show a clipboard success for a new view.
Only the existing owner routes Profiles completion events to the tool.

Malformed data, unavailable codec, unsupported layout dependencies, uncertain EVE
state, stale files, missing local preferences, destination collisions and staging
failures are visible refusals. No partial setup is published. Preserve the input
and review where recovery is possible; Cancel and the route out remain available.

## Acceptance: prove creation, not pre-existing contents

### Automated

- Strict parser budgets, malicious YAML/JSON, duplicate/order handling and unknown
  fields; regress Windows text encoding and oversized pytest parameter IDs.
- Explicit projection excludes identities, histories, unselected data and local
  preferences; ordered labels retain every repeated literal entry.
- Overview references/groups and window-state consistency; stale cached windows
  do not become active; unsupported sender, recipient and mixed stacks refuse
  without mutation, including surplus overview instances being retired.
- YAML compatibility reproduces the measured 42-definition/eight-tab input while
  explicitly retaining the recipient's complete label sequence when chosen and
  disclosing the single-overview-group policy. Do not expect EVE's lossy six-label
  result as a successful Wingman test.
- Preserve all six geometry integers exactly and keep local display-file bytes
  unchanged. No fitting or live-client geometry calls.
- Build from a recipient fixture deliberately different from the sender. Verify
  account/character identity, unrelated settings, defaults and copied local files.
- Native codec round-trips on the modified documents, failed publication, stale
  manifests, concurrent naming, changed identity links and post-publish warnings.
- Runtime page tests for real module execution, cancellation and late replies;
  lexical bridge guards alone do not validate the screen.

### Actual EVE and Windows

1. Create and initialize a genuinely fresh recipient profile through EVE, without
   copying sender DATs into it. Close EVE and capture that fresh baseline.
2. Use Wingman to apply the preset into a new profile based on that recipient.
   Verify the base remains unchanged and the new local display preferences match.
3. Restart/refresh the launcher, verify the new profile is offered, then select it
   explicitly for the test character. Folder existence is not this acceptance.
4. In-game, verify filters, all tabs, the intended overview-window grouping,
   supported window placement/state, target/HUD fields and every ship-label entry.
   Nothing may pass merely because the sender setup was preinstalled.
5. Repeat against a deliberately different initialized recipient. Test a different
   resolution/scale for truthful warning and local-display preservation, not an
   unpromised pixel-identical result.
6. Check real clipboard, keyboard, focus, floor-size review and relevant Windows
   scaling. Record actual results and distinguish EVE startup changes from import.

Native YAML's measured losses are a compatibility limitation, not the acceptance
standard for Wingman presets. The Wingman artifact must preserve the supported
source data through its own export/apply/reload path before this feature is ready.

## Design review and checks

An independent pre-implementation review found no blocking design findings. It
highlighted label multiplicity, recipient-side stacks, protected-definition/cache
classification, the declared YAML fallback, and actual display/launcher behavior
as acceptance gates rather than implementation claims. The checks above include
those cases.

A read-only check of the retained sender reference found all 415 geometry records
for the selected window set within the proposed numeric bounds. The character
files contain duplicated layouts; this is compatibility evidence for that corpus,
not proof of EVE-wide coordinate limits or correct behavior on another display.

The user approved proceeding after an independent second-opinion review returned
SHIP with no findings. No setup importer, GUI or new live profile mutation was
implemented while writing the design or its implementation plan.
