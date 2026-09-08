# UI setup field map and synthetic fidelity contracts

Status: **implemented pure projection/application and synthetic contracts**.
The [approved design](overview-layout-sharing-design.md) owns product behavior;
[discovery](overview-layout-sharing-discovery.md) owns the original experiment's
limitations. [V24.01 client evidence](ui-setup-client-evidence.md) supersedes the
preparatory assumptions about definitions, ordering, selectors and retirement.
Controller/UI publication and live EVE/Windows acceptance remain separate gates.

## Evidence boundary

Read-only analysis used the authorized retained sender reference (14 account and
41 character documents), supplied native YAML, and retained native-import result
(two account and two character documents, one populated pair). Decoding was through
the existing native stdin/stdout filter, in memory. The retained input and supplied
export were byte-identical. No live settings scan, launcher private-store access,
application manipulation or new profile experiment was performed.

The directory called `before` is a **sender reference**, not a fresh recipient
baseline. The native result has no fresh before/control. Counts include duplicated
layouts and are not independent experiments. Nothing here proves which native
result fields came from import rather than startup or initialization.

Only aggregates, schema names and shapes are recorded here. The committed JSON
fixtures were hand-authored from invented data, not scrubbed copies of decoded
personal files. Account/character IDs, names, history, timestamps and geometry in
fixtures are synthetic. Both fixtures now use the recognized public Jotunn
context; their identities, metadata, history and other preferences remain distinct.
The single `DefaultPreset_639431` regression body and the versioned fingerprint
table are explicitly public shipped compatibility data, not synthetic/private
profile data. User text/markup in an artifact is text, not HTML and not automatically
anonymized.

### Evidence levels

- **Observed:** the retained bytes decode to this representation, or values match
  across retained inputs. This is not live-EVE write/reload proof.
- **Policy:** Wingman's approved behavior, not a claim about EVE's native defaults.
- **Client-proved:** inspected public V24.01 bytecode/data, without execution;
  exact function references and hashes are in the current-client evidence document.
- **Unproven:** variants outside these bounded rules refuse the affected case;
  codec transport still does not prove live rendering/startup/launcher behavior.

## Codec notation, aliases and ownership

The internal JSON envelope is `{"had_crc": boolean, "doc": object}`. Account
sections `bytes:overview`, `bytes:defaultoverview`, `bytes:tabgroups`, `bytes:ui`
and character `bytes:windows` are dictionaries, **not stamped tuples themselves**.
An individual section setting is normally:

```json
{"tuple": ["long:116444736000000000", "VALUE"]}
```

The shown stamp is invented: `formations.filetime(0)`, Windows 100 ns ticks since
1601. Fixtures also use `formations.filetime(1)`. Stamps and CRC/envelope metadata
never enter a portable artifact. Future writes stamp modified setting entries,
not every nested map record; do not reconstruct unrelated settings.

All observed relevant section/setting aliases are `bytes:`. `utf8:` aliases occur
in label **field keys**, named definitions, text values and window-map keys.
`int:<n>` encodes tab-map keys. `json:<JSON>` encodes composite keys. String values
can be `bytes:` or `utf8:` regardless of the containing field key. Strip only the
known codec tag, once; text itself may contain colons or markup. The codec can
transport either string-key encoding; that does not prove EVE treats arbitrary
section aliases identically. Dual aliases of one semantic field and unknown
representations require explicit handling/refusal, not last-key-wins merging.

Ownership is a projection of the exact entries below, never a section clone.
Internal documents and hashes stay in Python/test fixtures, never JavaScript or
the wire. Local `core_public__.yaml` / `prefs.ini` bytes come only from the recipient
base; the fixture files are byte sentinels, not a verified hardware-file schema.

## Account overview: structural map

Every setting in this table is stamped; descriptions refer to its inner value.
Names are case-sensitive exact text. List order is retained.

| Storage under `overview` | Observed representation | Portable field / policy |
| --- | --- | --- |
| `overviewProfilePresets` | Map of `bytes:`/`utf8:` names to dictionaries with `bytes:groups`, `bytes:filteredStates`, `bytes:alwaysShownStates`; each a list of integers, empty state lists occur | `overview.presets`: ordered `{name, groups, filteredStates, alwaysShownStates}` records. Export all supported custom definitions plus named tab dependencies, under the exact Jotunn classification and canonical-body checks below. Map encounter order alone is not an EVE semantic ordering claim. |
| `overviewProfilePresets_notSaved`, `overviewProfilePresets_notSaved2` | Same name/body shape; current references are ordinary encoded strings | `_GetUnsavedPresets:253` prefers a present second map, **even empty**, else the first. Effective bodies win for exported definitions; warn/count them. Do not export orphan cache records. Apply removes imported-name overrides from both present maps, preserving unrelated entries and absence. Unknown legacy tuple references refuse. |
| `tabsettings_new` | `int:<tab index>` map; `bytes:name`, `overview`, optional `bracket`, `color`, `tabColumns`, `tabColumnOrder`, `showAll`, `showNone`, `showSpecials` | `overview.tabs` retains the exact fields (codec tags removed). Export sorts physical IDs, not map encounter order (`GetTabIDs:1193`, `OverviewWindow.ReconstructTabs:737`). Supported source slots are 0–19, with at most eight tabs. Apply allocates dense physical IDs in portable sequence order and remaps every group. |
| Tab `name`, `overview`, `bracket` | Encoded strings; bracket may be null or absent | Exact names retain closure, except null and the exact `_BracketFilterShowAll` bracket sentinel (`LoadBracketPreset:483`, `GetTabBracketPreset:1317`). No blanket underscore exemption. Absent physical bracket is null. |
| Tab `color` | Null or **three-float list** (RGB), not tuple/RGBA | Preserve as null or three-number array under explicit validation. No CSS colour-name conversion and no fabricated alpha. |
| Tab `tabColumns`, `tabColumnOrder` | Optional lists of `bytes:` enum strings | `GetTabVisibleColumnIDs:1325` falls back from absent visible columns to account `overviewColumns`, then ICON,DISTANCE,NAME,TYPE,VELOCITY. `GetTabColumnOrder:1339` falls back directly to `ALL_COLUMNS`, **not** account `overviewColumnOrder`. Full export materializes both. Native omission retains the destination physical slot's override/presence; new or absent slots remain absent. |
| Tab `showAll`, `showNone`, `showSpecials` | Optional booleans, known false defaults | Preserve all three independently; show-all has precedence over show-none in the client. Missing flags normalize false. `overviewSettingsConst:56–67`, `OverviewWindow.LoadTab:424`. |
| `tabsByWindowInstanceID` | List of nonempty lists of integer tab IDs; three groups covering eight tabs in 11 sender references; absent in native result | `overview.windowGroups`: ordered lists of tab IDs. Each included tab exactly once. Primary ordinal is `overview`, then `overview_1`, etc. Missing grouping means one group of existing saved tab IDs (`GetTabIDsByWindowInstanceID:1169`, `_GetDefaultTabIDsByWindowInstanceID:1190`); explicit malformed groups refuse. Export sorts each inner group without changing outer ordinals; portable group order must agree with the tab sequence. Geometry cache keys do not create groups. |
| `shipLabels` | Ordered list of dictionaries, including repeated null-type records and both field encodings described below | `overview.shipLabels`: ordered records; never a dictionary keyed by type. |

The native YAML's 42 definitions match all 42 saved custom entries in 11 sender
references and the populated native result; all eight result tab records match.
The effective unsaved definition differs from that saved-data export. The wire
fixture deliberately gives `Synthetic Fleet` saved groups `[25, 26]` but effective
export groups `[25, 27]`, with distinct recipient saved/unsaved definitions.
The projection tests compare independent expected literals before checking round trips.
The prefix-lookalike `DefaultPreset_SyntheticBuiltin` is custom and is exported too;
its former preparatory omission is not a classifier.

### Labels: fidelity and bounded supported variants

Observed in the nine-entry sender sequence: seven four-field `utf8:` records and
two expanded `bytes:` records. Native YAML has nine entries/four null types but
its result has six entries/one null type. YAML sorting and repeated nulls in
`shipLabelOrder` do not establish a unique original sequence.

| Field | Observed representation | Fixture contract / limitation |
| --- | --- | --- |
| `type` | Null, or encoded `pilot name`, `corporation`, `alliance`, `ship type`, `ship name`; additional `linebreak` in three other account references | Nine-entry fixture covers the first six alternatives; current tests additionally cover the documented `linebreak`/null-field record. Null type remains a literal, not linebreak. No arbitrary label-type strings. |
| `pre`, `post` | Encoded strings, including empty strings; markup lives in text | Preserve exact text. The additional `linebreak` records have null `pre`/`post`; do not convert null to empty text silently. |
| `state` | Integer 0 or 1 in ordinary records; null in `linebreak` records | Retain integer state, not a boolean. Null state/pre/post are allowed only on `linebreak`, not every label type. `ShipsPanel.AddLineBreak:163` constructs a `ShipLabel` with linebreak type; the retained field-map record establishes the supported explicit null fields. Missing required label fields still refuse rather than invent constructor defaults. |
| `bold`, `italic`, `underline` | Expanded records have boolean false. Other observed variants have integer 1 for bold/italic | Booleans supported; bold/italic also accept exactly integer 1, retaining its type. Underline remains boolean. Type-sensitive comparison decides label replacement: Python's True == 1 must not suppress a required write. |
| `fontsize` | Null in expanded nine-entry records; integer 11 or 12 in other references | Accept exactly null, integer 11 and integer 12; no arbitrary font-size range or boolean coercion. |
| `color` | Null in expanded nine-entry records; RGB **three-float lists** in other references (white and a yellow shade) | Accept null or a finite three-number RGB list in the existing normalized 0–1 domain; not RGBA, tuples or colour names. Preserve numeric representation. |

Other observed key sets are four-field `bytes:` records and partial combinations
adding only `fontsize`, only `italic`, `color` + `fontsize`, or `bold` + `color` +
`fontsize`. The retained evidence proves those shapes exist, not a rule that all
formatting properties are interchangeable or absent properties mean false.
Optional supported fields stay optional. The synthetic recipient uses plain
four-field `bytes:` labels. Unknown keys, type enums and unsupported formatting
variants refuse rather than being dropped or generalized.

Native ambiguous labels require the explicit **Keep my ship labels** choice;
its lossy six-entry result is not a success criterion for Wingman.
`OverviewPresetSvc._LoadGeneralSettings:1044` uses type-keyed conversion with
`linebreak` as the sole allowed repeated order slot. A single linebreak body or
representation-identical linebreak records can reproduce repeated linebreak order;
differing same-type bodies (including null literals) remain ambiguous and require
Keep. Formatting presence and integer/boolean differences are not ignored.

## Appearance/state settings

The following is the explicit preparatory `overview.settings` map. It is not a
generic dictionary of account options. Aggregate absence and scalar absence are
kept distinct from explicit false/empty values.

| Wire aggregate | Stamped storage under `overview` | Inner representation |
| --- | --- | --- |
| `flagOrder` | `flagOrder2` | List of integer state IDs |
| `flagStates` | `flagStates2` | List of integer state IDs |
| `backgroundOrder` | `backgroundOrder2` | List of integer state IDs |
| `backgroundStates` | `backgroundStates2` | List of integer state IDs |
| `columnOrder` | `overviewColumnOrder` | List of encoded column enum strings |
| `overviewColumns` | `overviewColumns` | List of encoded column enum strings |
| `stateColors` | `stateColors` | Composite-key map to **four-number tuple** colours |
| `stateBlinks` | `stateBlinks` | Composite-key map to booleans; false is observed, not equivalent to absent |

Composite keys are exactly of the shape
`json:{"tuple":["bytes:background",9]}` or
`json:{"tuple":["bytes:flag",12]}` (numbers here are fixture examples).
The proposed readable records are `{category, state, color}` and
`{category, state, blink}`; categories are explicitly `background` / `flag`.
Tuples become arrays only in the wire; the internal adapter must rebuild known
colour tuples. State colours have alpha; tab and label colours do not.

Observed column enums (all represented by the fixture's column order):
`ALLIANCE`, `ANGULARVELOCITY`, `CORPORATION`, `DISTANCE`, `FACTION`, `ICON`,
`MILITIA`, `NAME`, `RADIALVELOCITY`, `SIZE`, `TAG`, `TRANSVERSALVELOCITY`, `TYPE`,
`VELOCITY`. Unknown columns/categories are unsupported, not passthrough strings.
State/group IDs are numeric domain values, not a small hand-maintained enum.

The exact scalar wire names below map one-to-one to same-named stamped
`bytes:` keys under `overview`:

- `applyToOtherObjects`, `applyToStructures`, `overviewBroadcastsToTop`;
- `showBiggestDamageDealers`, `showInTargetRange`, `showModuleHairlines`;
- `showCategoryInTargetRange_6`, `showCategoryInTargetRange_11`,
  `showCategoryInTargetRange_18` (these three observed keys only, not a prefix);
- `targetCrosshair`, `useSmallColorTags`, `viewTactical`,
  `viewTactical_camTactical`;
- `hideCorpTicker`, `useSmallText`.

Their observed inner values are booleans, except the final two also occur as
integer zero; the fixture illustrates zero-to-false normalization without a
truthiness conversion of arbitrary integers. `viewTactical_camTactical` occurs
only in sender references. Native YAML's `userSettings` supplies **only**
`useSmallColorTags`. The other DAT scalars are not proof of additional native
`userSettings` variants; accepting them from native YAML requires explicit coverage.

### Native colour correspondence (bounded evidence, not CSS)

Every exported state-colour key corresponds to the same numeric tuple in sender
and native result. The observed native names map as follows:

| Native name | Internal RGBA tuple |
| --- | --- |
| `black` | `(0.0, 0.0, 0.0, 1.0)` |
| `blue` | `(0.2, 0.5, 1.0, 1.0)` |
| `darkBlue` | `(0.0, 0.15, 0.6, 1.0)` |
| `green` | `(0.1, 0.6, 0.1, 1.0)` |
| `orange` | `(1.0, 0.35, 0.0, 1.0)` |
| `red` | `(0.75, 0.0, 0.0, 1.0)` |
| `turquoise` | `(0.0, 0.63, 0.57, 1.0)` |
| `white` | `(0.7, 0.7, 0.7, 1.0)` |
| `yellow` | `(1.0, 0.7, 0.0, 1.0)` |

No other native colour name is proved here. Refuse unknown names; do not silently
fall back to CSS colours. Full parser enum tests belong to the later parser task.

## Layout: geometry, seven maps and dependencies

All settings below are stamped. Geometry/state map entries themselves are not
stamped. The approved fixed window set is `selecteditemview`,
`probeScannerWindow`, `directionalScannerWindow`, `droneview`, `fleetwindow`,
`watchlistpanel`, `standaloneBookmarkWnd`, `solar_system_map_panel`,
`primary_map_panel`, plus overview ordinals derived from active account groups.
The future source allowlist must be authoritative; this table/fixture is not a
second runtime registry or permission to accept arbitrary alphabetic keys.

| Storage location | Inner shape | Wire mapping |
| --- | --- | --- |
| Character `windows.windowSizesAndPositions_1` | Encoded window-key map to `{"tuple": [int, int, int, int, int, int]}` | `layout.windows[].geometry`: all six saved values, as-is. Null for absent ordinary-window geometry; required for each active overview. |
| Character `windows.openWindows` | Window-key map to booleans | Window state `open` |
| Character `windows.minimizedWindows` | Window-key map to booleans | `minimized` |
| Character `windows.collapsedWindows` | Window-key map to booleans | `collapsed` |
| Character `windows.compactWindows` | Window-key map to booleans | `compact` |
| Character `windows.lockedWindows` | Window-key map to booleans | `locked` |
| Character `windows.isOverlayedWindows` | Window-key map to booleans | `overlay` (storage spelling is intentional) |
| Character `windows.isLightBackgroundWindows` | Window-key map to booleans | `lightBackground` |
| Account `ui.targetOrigin` | Two-float **tuple** | `layout.targetOrigin`: pair, copied as saved |
| Account `ui.targetOriginLocked` | Integer 0/1 or absent | `TargetMgr.UnlockOrigin:177` / `LockOrigin:181` write exact integer 0/1. Portable false/true maps to those integers, absence to null clear intent; no generic truthiness. |
| Character `windows.shipuialignleftoffset` | Integer, sometimes absent | `layout.hudOffset`: saved integer, not any other similarly named HUD setting |
| Character `windows.stacksWindows` | Window-key map to null or encoded stack identifier | Dependency check only, never portable. Refuse non-null associations on affected windows. |
| Character `windows.preferredIdxInStack3` | Stack-key map to window-key maps of integers | Dependency evidence only. Not `preferedStackPos`, not a flat window flag and not an authorized cache-reset target. |

In the sender corpus, 415 records for the approved window set (excluding stale
`overview_3`) have six-integer geometry within the approved bounds. Adding stale
`overview_3` gives 448 records. Those 33 stale records have **non-null stack
associations**; the selected active windows do not. This is a concrete reason not
to activate all cached geometry or indiscriminately clear stack maps. A recipient
surplus overview being retired is affected and its stack must be checked even
though it is absent from the incoming active set.

Some maps/entries are absent, some false, some true. An absence does not prove
EVE's current rendered default. Geometry's last two numbers vary across cached
windows; they are preserved without guessing coordinate/reference semantics or
performing fitting. Recipient-local display preferences must remain byte-identical.
Never move or resize a live client.

## Missing values, replacement and reset: policy versus proof

| Case | Approved Wingman policy | Evidence limitation |
| --- | --- | --- |
| Full Wingman supported overview override absent | Normalize to clear/reset that supported override, not retain conflicting recipient state | Which absent EVE entry yields which rendered default is not established by this capture. No made-up default values. |
| Native scalar/aggregate absent | Retain recipient value; supplied aggregate replaces that aggregate | Declared compatibility policy, not observed native import reset behavior. |
| Included window has absent state property | Remove only that window's corresponding stored override | Not equivalent to setting false or clearing its whole map. |
| Included ordinary window has null geometry | Clear only that window's geometry override | Full export covers fixed slots even when absent. Active overview geometry cannot be null. |
| Explicit null target pair / target lock / HUD offset | Clear only the respective setting override | Do not copy/reset entire `ui` / `windows` sections. |
| Supplied native tabs | One primary group, retain primary geometry; retire surplus overview instances | Native YAML has no layout/grouping. Replace groups and set surplus ordinal `openWindows` entries false, checking both stack indexes first; retain inert rectangles/history (`OverviewWindow.ReconstructTabs:737`, `GetWindowInstanceIDs:1154`). |
| Native filter-only input | Preserve tabs/groups and absent aggregates | Missing named dependencies cannot bind to arbitrary same-named recipient filters. |
| Matching incoming definition | Replace custom exact-name definition; preserve unrelated saved definitions and unrelated unsaved entries | Requires protected-definition classification and valid cross-references first. |

Absent entire tab records still require localized client defaults and refuse;
missing grouping alone is supported as documented above. Missing required maps,
malformed explicit maps/groups, dual aliases, unknown enums and unsupported stacks
are not permission to synthesize arbitrary defaults. Pure construction is not
publication authority or a substitute for EVE/Windows acceptance.

## Default definitions and selection/cache authority

### Exact public Jotunn domain and fingerprints

`DefaultOverviews.__init__:11`, `GetCustomPresetNames:296`,
`YamlDefaultOverview._do_load:70` and `PresetData.__init__:121` establish the
current supported context and functional definitions. Wingman requires exact
`defaultoverview.defaultOverviewID == 'jotunn_default'`; `overviewID` is preserved
metadata, not a fallback catalogue selector. Ordinary null/absent overviewID works.
Unknown/missing default context refuses rather than guessing the FSD catalogue.

`setup_compat.py` stores only the public SHA-256 fingerprints for exact keys
`DefaultPreset_639431` through `DefaultPreset_639466`, not private bodies or client
implementation. Jotunn YAML SHA-256:
`2e89abe9207dd5e166c0c8b2908ccfee07054a7fe4d6af79457c41efc4387185`.
The normative fingerprint is compact UTF-8 JSON with alphabetically ordered
alwaysShownStates, filteredStates, groups keys. Arrays retain order/duplicates;
canonical groups were sorted by PresetData and state lists retain supplied order.
The table/domain is derived/asserted, not a second manually kept count.

Check exported/affected built-ins only. A protected source dependency needs its
saved canonical body and canonical effective override, if any. Incoming protected
bodies and any protected recipient collision must match the public fingerprint;
two equal but wrong saved bodies are insufficient because initialization overwrites
built-ins (`Initialize:202`, `AddDefaultPresetsToAllPresets:226`). A canonical incoming
body may supply a previously absent recipient record. No missing source body is
reconstructed from a hash. Unused built-ins remain opaque; custom differing bodies
can be replaced, with unrelated definitions preserved.

Legacy names, prefix lookalikes and case variants outside the exact active domain
are custom. `DefaultPreset_SyntheticBuiltin` is explicitly one such invented
custom regression record. Save-dialog localized/case-insensitive restrictions
(`IsDefaultPresetName:573`) do not classify stored data.

### Exact load-bearing references and narrow mutations

| Location | Observed inner shape/correspondence | Current authority |
| --- | --- | --- |
| `overview.activeOverviewPreset` | Encoded last-loaded name | Preserve a valid saved/effective-unsaved reference or absence after override cleanup. When incoming tabs replace an invalid named reference, select the imported primary group's first displayed tab deliberately; filter-only input cannot invent a replacement. Unsupported tuple/null/type variants refuse. `OverviewWindow.LoadTab:424` reads each tab's assignment; this is not one global assignment for every window. |
| `tabgroups.overviewTabs` | Nonnegative integer **per-window ordinal**, not physical ID | `TabGroup._FindAutoSelectTabIDx:897`. On changed physical tab identity/order/group/name/color, set exact integer 0 (first-enabled fallback), even if selector previously absent. No tab-ID closure constraint. Unchanged selection meaning can preserve the old representation. |
| `tabgroups.overviewTabs_names` | Encoded label text, possibly markup/whitespace normalization | This truthy label has precedence over numeric selection. Delete this exact key when resetting the ordinal; do not require equality with raw tab name. `Tab.Select:339`, `SaveSelectedTabName:445`. |
| Character `ui.SortHeadersSettings2`, `ui.SortHeadersSizes` | Stamped maps keyed by codec tuples such as `json:{"tuple":["bytes:overviewScroll2",0]}` | `OverviewWindow.ConstructScroll:247`, `OnTabSelected:846`, `SortHeaders.GetSettingKey:396`. Delete only tuple entries for imported/reused physical IDs, preserve other scrolls and retired unused IDs, and never create absent maps. Do not stringify keys to a different cache format. |
| `overview.alwaysShow`, `filterOut`, `unfiltered` | Stamped null in sender references, absent from native result | Names suggest filter caches; null-only data cannot establish what non-null values mean or whether deletion is safe. |
| `overview.presetHistoryKeys` | Composite-key map of dictionaries | History excluded; never wholesale delete to force refresh. Inner history semantics not owned. |
| `overview.restoreData` | Dictionary containing text, long and dictionary values | Restore data excluded; no proven deletion/reset. |
| `ui.overviewProfileName`, `overviewProfileNameInExport` | Stamped encoded strings | Local export/profile metadata, not a portable setup field or known invalidation target. Preserve pending evidence. |
| `tabgroups.overviewfilterTab`, `overviewsettingsTab`, `overviewstatesTab` and matching `_names` keys | Integer/text pairs | Settings-dialog selection candidates, not proven active-configuration dependencies. No reset permission. |
| `windows.stacksWindows`, `preferredIdxInStack3` | Cross-referencing maps described above | No wholesale stack deletion, detaching, or sender stack-ID copying. |

The source-proved rules close the earlier universal classifier/selection/retirement
refusals. Both stack indexes still gate every affected/new/surplus ordinal before
mutation; full input additionally checks all fixed supported slots. Close surplus
`openWindows` entries explicitly, without deleting their inert geometry, other
state maps or history. Native filter-only input preserves topology entirely.

No live profile/capture access is required to implement these bounded rules.
Fresh-recipient creation/reload, transient window startup behavior, deliberately
different recipient replacement, local display preservation, launcher visibility
and UI smoke acceptance from the design remain separate later gates.

## Synthetic helpers and verification scope

`tests/setup_fixtures.py` provides:

- `wire() -> dict`: fresh hand-authored semantic envelope per call.
- `documents(case='source') -> tuple[codec.Document, codec.Document]`: fresh
  account/character documents, with source CRC enabled and recipient CRC disabled.
- `install_lossless_codec(monkeypatch) -> None`: substitutes only `_run` transport
  and availability; real snapshot hashing, encode/decode verification, backup
  ordering and atomic file publication remain in `codec.py`.
- `seed_profile(tmp_path, *, case='recipient', name='Base') -> ProfileFixture`:
  `root`, `server`, `profile`, `account_path`, `character_path` are `Path` values.
  Recipient files use IDs 20/30; source 10/11. The recognized server folder is
  `c_eve_sharedcache_tq_tranquility`. Seeding uses `codec.write_document`, and
  distinct local YAML/INI byte sentinels include different newline styles.

The source has three groups/eight tabs/nine labels/four null labels, a differing
unsaved override, inactive stacked `overview_3`, mixed geometry reference sizes,
all seven state maps and explicit absent/false cases. The distinct recipient has
four active overview groups (so one is surplus for the source), recipient-only
saved/unsaved definitions, different labels/geometry/default update metadata and
private sentinels. Both use the same recognized public default context, not the
same recipient identity or setup. Unrelated windows/sections exist to detect future over-broad copying.
History/private sentinels intentionally have invented opaque inner shapes; they
are not additional EVE schema evidence.

Tests use independent expected literals and mutate returned nested values to
check fresh copies. Codec-boundary tests use all four documents, verify exact
readback and input nonmutation, and can run with the existing native-codec seam.
A native binary's success proves **transport fidelity only**, not EVE recognition,
default classification, cache invalidation, window layout or publication safety.
The codec checks prove transport fidelity only. Pure adapter and hidden staging
regressions now exercise replacement/retirement, but not live EVE recognition or
controller/UI publication authority.
