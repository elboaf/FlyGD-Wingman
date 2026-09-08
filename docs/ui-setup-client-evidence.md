# V24.01 client evidence for setup sharing

## Provenance and boundary

The installed public client archive `code.ccp` has SHA-256
`83b376bc2a753f1c93a40506d7aab9f521bd8e3e61644692b24febc7ab1d6bff`.
Its selected ZIP members are zlib-compressed Python 2.7 bytecode. They were
inspected with a cross-version disassembler, **without executing or importing
game modules**, modifying game files, reading process memory or accessing
credentials. Generated disassemblies remain ignored investigation artifacts.
Only independently stated behavior, functional compatibility data and synthetic
tests belong in Wingman; client implementation code is not vendored.

References below identify client functions and original source start lines. This
is stronger evidence than inferring behavior from setting names or codec
round-trips. It still does not replace end-to-end EVE/Windows acceptance.

## Default definitions and supported context

`DefaultOverviews.__init__:11` initializes the shipped `DEFAULT`,
`jotunn_default`. `OverviewPresetSvc._SetupDefaultOverviews:133` does not select a
catalogue through `defaultOverviewID or overviewID`; it records/updates default
metadata. Ordinary tab edits set `overviewID` to null
(`UpdateSettingsByTabID:1249`). The update informer notifies; its inspected path
does not silently replace tabs or select another catalogue.

The public Jotunn YAML in
`eve/client/script/parklife/overview/default/data/jotunn_default.pyj` has SHA-256
`2e89abe9207dd5e166c0c8b2908ccfee07054a7fe4d6af79457c41efc4387185`.
Its exact stored-name domain is the 36 names `DefaultPreset_639431` through
`DefaultPreset_639466`. `GetCustomPresetNames:296` excludes exact catalogue
members. Prefixes, encoding, localized names and case-folded spelling are not its
stored-record classification rule. `IsDefaultPresetName:573` performs a broader
case-insensitive/localized **save-dialog** check; do not conflate the two.

**Wingman support policy:** initially require the recognized
`defaultOverviewID == "jotunn_default"` context and preserve recipient metadata.
Normal absent/null `overviewID` is allowed. This gate is a conservative supported
context, not a claim that the client uses that field to choose the catalogue.
Missing/unknown default context refuses. Stored legacy names outside the active
Jotunn catalogue are custom under the evidenced rule. The configured old pack is
FSD-backed; a seven-name old YAML literal does not prove that FSD catalogue, so
legacy switching is not inferred.

### Canonical protected bodies

`YamlDefaultOverview._do_load:70` and `PresetData.__init__:121` build canonical
functional records: groups sorted, duplicates retained, the two state lists in
supplied order. `Initialize:202` calls `AddDefaultPresetsToAllPresets:226` after
loading/reordering saved data, overwriting built-in records from that catalogue.
An identical but noncanonical saved collision is therefore not sufficient proof
of restart fidelity.

Use versioned public **fingerprints**, not a private profile catalogue or a copy
of the full game data. Fingerprint encoding is UTF-8 compact JSON of exactly
`alwaysShownStates`, `filteredStates`, `groups` in that alphabetical key order;
arrays retain their canonical order and repeated entries. Parent extraction
computed SHA-256 in Python; an independent Node SHA-256 calculation using an
explicit three-field object verified all 36 results.

`ReorderPresets:279` calls `ReorderList:92`, which sorts without deduplication
for `groups`, `filteredStates` and `alwaysShownStates`; the state getters also
return lists directly. Wingman therefore relaxes uniqueness validation for all
three preset membership lists and preserves their sequences and repeated entries.
This is not removal of a deduplication step. The public default dataset has no
repeated state values, so support for repeated states rests on client code, not
fixture evidence. Unrelated logical-key and ID uniqueness guards remain intact.

Check affected protected records only. Without reconstructable canonical bodies,
missing/noncanonical source dependencies, noncanonical incoming protected bodies
or noncanonical protected recipient collisions refuse specifically. Unused
built-ins need not become a universal gate. Differing custom definitions may be
replaced under the explicit configuration-replacement policy.

### Native omitted built-in dependencies

`GetPresetsInUse:883` passes the default-name exclusion list to
`ShouldAddPreset:892`, intentionally omitting built-in bodies from native exports.
Native-only normalization accepts external overview/bracket references in the
exact Jotunn stored-name domain. This is not permission to borrow arbitrary
recipient custom definitions or to infer bodies from fingerprints. Full Wingman
artifacts still require all named bodies, apart from the exact bracket sentinel
and null.

Application revalidates native references, requires the supported Jotunn context,
and resolves each external dependency only against an available saved body that
matches the public canonical fingerprint. Missing/noncanonical saved bodies
refuse, even if an unsaved override is canonical. Referenced external names count
as imported names: validate affected override shapes and remove those names from
both present unsaved generations, so effective-unsaved state cannot silently
substitute another filter. Malformed affected overrides refuse; unrelated entries
and map presence remain untouched. Canonical saved records retain their original
encoding/body, and unchanged saved maps retain their timestamps.

## Unsaved overrides

`_GetUnsavedPresets:253` prefers a present `overviewProfilePresets_notSaved2` over
`overviewProfilePresets_notSaved`, using the latter only as an absence fallback.
A present empty second map wins; there is no union. `IsUnsavedPreset:751` and
`GetPresetFromKey:323` consult this effective map. Current
`GetUnsavedPresetName:748` returns the ordinary name unchanged; legacy tuple-name
handling is separate and must not be invented from a guessed tuple shape.

Export all supported custom definitions plus tab dependencies, using effective
unsaved bodies and the planned warning/count. Refuse unsupported custom records
rather than silently omit them. Application removes imported-name overrides from
both present maps, preserving unrelated entries and map presence.

## Topology and real tab order

`GetTabIDsByWindowInstanceID:1169` defaults absent grouping to one group of all
saved tab keys (`_GetDefaultTabIDsByWindowInstanceID:1190`). This is now
source-proved, not a proposed interpretation. Malformed explicit groups are not
absence. Entirely missing tab records still require actual default/localized
records; do not synthesize names.

Outer group positions determine overview-window ordinals. `GetTabIDs:1193`
**sorts physical tab IDs**; `OverviewWindow.ReconstructTabs:737` passes that order
to tab construction. Map encounter order and group-member encounter order do not
determine displayed order. Earlier native map-order checks proved transport
fidelity only, not this EVE behavior.

**Ordered-preset implementation policy:** export effective tabs sorted by
physical ID, normalizing each group's member order accordingly. Apply artifact
IDs as local references: allocate dense physical IDs `0..n-1` in portable tab
sequence order and remap groups. Refuse contradictory ordering promises when a
group's order disagrees with its subsequence of the ordered tabs. Do not silently
choose one ordering. Sparse physical IDs work in some client read paths, but the
editor/exporter assumes a bounded slot domain; dense output is conservative.
Wingman's eight-tab limit remains distinct from the client's 20-tab limit.

## Selection and precise cache invalidation

Every overview window uses tab-group settings ID `overviewTabs`.
`TabGroup._FindAutoSelectTabIDx:897` tries the truthy `_names` label first, then a
truthy numeric **per-window ordinal**, then the first enabled tab. Zero takes the
first-enabled fallback. `Tab.Select:339` reaches `SaveSelectedTabIndex:442` and
`SaveSelectedTabName:445`; auto-selection updates the number without clearing the
name. Labels can include color markup and stripped whitespace, not just raw tab
names.

When replacement changes selection meaning, remove the exact
`tabgroups.overviewTabs_names` override and set `overviewTabs` to integer zero
(or remove both overrides). Preserve unrelated tab-group records. Resetting the
number alone leaves name precedence intact. Retain unchanged records only where
meaning is demonstrably unchanged; do not validate the number as a tab ID.

`activeOverviewPreset` is last-loaded overview state. Tab selection reads that
tab's own assignment; it does not replace all tabs with one persisted global
filter. Preserve valid recipient references/absence where possible; a necessary
reset must use the deliberately selected imported tab, not an arbitrary
filter-list entry. Only window instance zero drives brackets in the inspected
`LoadTab:424` / `IsBracketFilterDictatingWindow:446` path.

`OverviewWindow.ConstructScroll:247`, `OnTabSelected:846` and
`SortHeaders.GetSettingKey:396` establish real tuple cache keys
`("overviewScroll2", physical_tab_id)` in character `ui.SortHeadersSettings2`
and `ui.SortHeadersSizes`. For reused/reassigned imported tab IDs, remove only
those exact entries. Preserve other scroll IDs, unrelated tabs and unrelated
settings. Do not fabricate caches when absent or sweep a whole section. Retired
unused IDs do not reopen windows and need no speculative purge.

## Surplus retirement

`GetWindowInstanceIDs:1154`, `GetWindowID:1163` and
`overviewWindowUtil.OpenOverview:14` derive active windows from groups.
`OverviewWindow.ReconstructTabs:737` closes an ordinal no longer represented.
This supports replacing groups, setting established surplus `openWindows`
entries explicitly false, and retaining inert geometry/history/other state.
Check every included/new/surplus affected stack before mutation; never detach a
mixed stack or infer activity from cached `overview_N` rectangles.

The selected modules do not establish every base-window startup timing detail.
Transient reopen behavior remains live acceptance, not a reason to delete more
state or retain a universal retirement refusal.

## Brackets, columns, labels and target-origin representation

- `LoadBracketPreset:483` / `GetTabBracketPreset:1317` establish nullable bracket
  assignments and the exact `_BracketFilterShowAll` sentinel. Exempt only that
  sentinel and null from named-definition closure. Preserve their actual values.
  `showAll`, `showNone`, `showSpecials` are load-bearing per-tab flags, default
  false; show-all takes precedence over show-none. Include supported forms rather
  than silently discard them.
- Physical per-tab columns are `tabColumns` and `tabColumnOrder`; global keys
  are `overviewColumns` and `overviewColumnOrder`. Missing per-tab visible
  columns fall back to account visible columns, then
  `[ICON, DISTANCE, NAME, TYPE, VELOCITY]`. Missing per-tab order falls directly
  back to the known `ALL_COLUMNS`, **not** account global order
  (`GetTabVisibleColumnIDs:1325`, `GetTabColumnOrder:1339`). Materialize effective
  full-export values; keep deliberate partial-native omissions distinct.
- Basic label types and `linebreak` are distinct; null is not linebreak.
  Preserve ordered multiplicity, optional formatting presence and observed
  nullable/special records without inventing defaults. Native conversion uses
  type-keyed dictionaries and preserves repeated order only for linebreak;
  retain the explicit ambiguous-native Keep policy.
- `TargetMgr.LockOrigin:181` and `UnlockOrigin:177` write account
  `ui.targetOriginLocked` as integer 1/0. Portable booleans map to those physical
  integers. `OnOriginMU:253` writes a two-float target-origin tuple; preserve it
  without fitting. No universal fallback coordinates are synthesized.

## Implementation and acceptance ruling

Implement the source-proved behavior and narrowly stated support policies in
Task 4b, with meaningful regression tests, public-data provenance and independent
review. Keep current model limits unless an observed supported variant requires
an explicit compatible extension. Tests must distinguish Boolean values from
integer formatting flags where exact representation is promised.

These findings supersede earlier uncertainty gates and incorrect map-order
interpretation. They do not authorize live-profile writes, launcher activation,
publication before controller guards, unsupported FSD migration, arbitrary
formatting, or claiming native transport tests prove EVE rendering. End-to-end
acceptance still checks tabs/groups/order, primary brackets, windows, labels,
local preferences and launcher visibility.
