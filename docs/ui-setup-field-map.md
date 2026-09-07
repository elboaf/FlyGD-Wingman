# UI setup field map and synthetic fidelity contracts

Status: **representation evidence and preparatory fixtures only**. No exporter,
importer, protected-definition classifier or publication path is implemented here.
The [approved design](overview-layout-sharing-design.md) owns product behavior;
[discovery](overview-layout-sharing-discovery.md) owns the original experiment's
limitations. **The publication proof gate remains closed.**

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
fixtures are synthetic. User text/markup in a future artifact is text, not HTML
and not automatically anonymized.

### Evidence levels

- **Observed:** the retained bytes decode to this representation, or values match
  across retained inputs. This is not live-EVE write/reload proof.
- **Policy:** Wingman's approved behavior, not a claim about EVE's native defaults.
- **Unproven:** a rule required before enabling the affected operation. No guessed
  cache reset, name-prefix classifier or silent unsupported-value conversion.

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
| `overviewProfilePresets` | Map of `bytes:`/`utf8:` names to dictionaries with `bytes:groups`, `bytes:filteredStates`, `bytes:alwaysShownStates`; each a list of integers, empty state lists occur | `overview.presets`: ordered `{name, groups, filteredStates, alwaysShownStates}` records. Export custom definitions plus tab dependencies only after classification/closure is proved. Map encounter order alone is not an EVE semantic ordering claim. |
| `overviewProfilePresets_notSaved` | Same definition shape, empty maps or one named entry; all 11 observed nonempty entries resolve to saved definitions | Overlay valid entries on saved definitions in the **export copy**; warn/count them. On replacement remove stale unsaved overrides only for imported definitions; preserve unrelated entries. No write to sender. |
| `tabsettings_new` | `int:<tab index>` map. Each record has `bytes:name`, `overview`, `bracket`, `color`, `tabColumns`, `tabColumnOrder` | `overview.tabs`: ordered `{id, name, overview, bracket, color, tabColumns, tabColumnOrder}`. Numeric tab IDs are artifact-local, not account/character identities. |
| Tab `name`, `overview`, `bracket` | Encoded strings; bracket additionally observed null. Every non-null reference in the corpus resolves to a saved definition | Names/references retain exact text. A null bracket's behavior is **unproven**, not permission to invent a sentinel. Fixtures use fully closed named dependencies. Missing dependencies refuse. |
| Tab `color` | Null or **three-float list** (RGB), not tuple/RGBA | Preserve as null or three-number array under explicit validation. No CSS colour-name conversion and no fabricated alpha. |
| Tab `tabColumns`, `tabColumnOrder` | Lists of `bytes:` enum strings | Preserve columns and ordering independently; do not derive one by sorting the other. |
| `tabsByWindowInstanceID` | List of nonempty lists of integer tab IDs; three groups covering eight tabs in 11 sender references; absent in native result | `overview.windowGroups`: ordered lists of tab IDs. Each included tab exactly once. Primary ordinal is `overview`, then `overview_1`, etc. Geometry cache keys do not create groups. |
| `shipLabels` | Ordered list of dictionaries, including repeated null-type records and both field encodings described below | `overview.shipLabels`: ordered records; never a dictionary keyed by type. |

The native YAML's 42 definitions match all 42 saved custom entries in 11 sender
references and the populated native result; all eight result tab records match.
The effective unsaved definition differs from that saved-data export. The wire
fixture deliberately gives `Synthetic Fleet` saved groups `[25, 26]` but effective
export groups `[25, 27]`, with distinct recipient saved/unsaved definitions.
These are preparatory expectations, not an implemented projection test.

### Labels: fidelity and explicitly unsupported variants

Observed in the nine-entry sender sequence: seven four-field `utf8:` records and
two expanded `bytes:` records. Native YAML has nine entries/four null types but
its result has six entries/one null type. YAML sorting and repeated nulls in
`shipLabelOrder` do not establish a unique original sequence.

| Field | Observed representation | Fixture contract / limitation |
| --- | --- | --- |
| `type` | Null, or encoded `pilot name`, `corporation`, `alliance`, `ship type`, `ship name`; additional `linebreak` in three other account references | Nine-entry fixture covers the first six alternatives. **`linebreak` is recorded but unsupported by this preparatory wire subset**; see nullable fields below. No arbitrary label-type strings. |
| `pre`, `post` | Encoded strings, including empty strings; markup lives in text | Preserve exact text. The additional `linebreak` records have null `pre`/`post`; do not convert null to empty text silently. |
| `state` | Integer 0 or 1 in ordinary records; null in `linebreak` records | Fixture retains integer state, not a type-keyed boolean dictionary. Null-state variant remains unsupported. |
| `bold`, `italic`, `underline` | Expanded records have boolean false. Other observed variants have integer 1 for bold/italic | Fixture contains the boolean-shaped fields explicitly. Integer formatting flags are **not silently coerced**; broader support needs explicit model tests/decision. |
| `fontsize` | Null in expanded nine-entry records; integer 11 or 12 in other references | Null supported by fixture contract. Non-null values are inventoried, **not evidence for accepting arbitrary integers/ranges**. Refuse unsupported non-null font variants until explicitly modeled/tested. |
| `color` | Null in expanded nine-entry records; RGB **three-float lists** in other references (white and a yellow shade) | Null supported by fixture contract. Non-null formatting colour support remains gated; do not infer RGBA from state colours or accept unknown formats. |

Other observed key sets are four-field `bytes:` records and partial combinations
adding only `fontsize`, only `italic`, `color` + `fontsize`, or `bold` + `color` +
`fontsize`. The retained evidence proves those shapes exist, not a rule that all
formatting properties are interchangeable or absent properties mean false.
Optional supported fields stay optional. The synthetic recipient uses plain
four-field `bytes:` labels. Unknown keys, type enums and non-null unsupported
formatting variants must refuse rather than be dropped or generalized.

Native ambiguous labels require the explicit **Keep my ship labels** choice;
its lossy six-entry result is not a success criterion for Wingman.

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
| Account `ui.targetOriginLocked` | Integer zero or absent in this corpus | `layout.targetOriginLocked`: fixture false; other persisted nonzero/type variants require evidence/explicit support, not generic truthiness |
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
| Supplied native tabs | One primary group, retain primary geometry; retire surplus overview instances | Native YAML has no layout/grouping. Exact safe retirement/cache reset remains gated. |
| Native filter-only input | Preserve tabs/groups and absent aggregates | Missing named dependencies cannot bind to arbitrary same-named recipient filters. |
| Matching incoming definition | Replace custom exact-name definition; preserve unrelated saved definitions and unrelated unsaved entries | Requires protected-definition classification and valid cross-references first. |

Absent entire overview configuration, absent grouping, missing/malformed required
maps, dual aliases, unknown enums and unsupported stack relationships are not
permission to synthesize arbitrary defaults. A validated full wire document still
does not authorize publication when these internal dependency rules are unproved.

## Default definitions and selection/cache gate

### Proved observations, not a classifier

There are 36 `DefaultPreset_*` definitions in every sender account document and
the populated native result. These maps are identical across those documents and
are absent from native export. Separate `defaultoverview.defaultOverviewID`,
`defaultOverviewInformedOfUpdate` and `overviewID` exist; `overviewID` can be null.
This supports a built-in/default association, **not an exhaustive protection
rule**, collision policy or proof that a custom definition cannot share the prefix.

`DefaultPreset_SyntheticBuiltin` in both fixtures is invented. It is merely an
identical-definition preservation/conflict probe for future tests; no test or
helper classifies it as protected. Its omission from the hand-authored wire is not
an implemented export rule. Do not infer a classifier from this fixture name.

### Exact observed references and unknown dependencies

| Location | Observed inner shape/correspondence | Current authority |
| --- | --- | --- |
| `overview.activeOverviewPreset` | Encoded name; resolves to saved definition in all 14 sender accounts and populated native result | Selection dependency candidate. How global selection interacts with multiple overview groups is not proved; no reset recipe. |
| `tabgroups.overviewTabs` | Integer, resolves to a saved tab ID in every populated account | Candidate selected-tab reference; ordinal vs ID semantics under regrouping require observation. |
| `tabgroups.overviewTabs_names` | Encoded text; agrees with a saved tab name in only 5 of 14 sender accounts, agrees in native result | A concrete mismatch, not proof the cache is disposable. Authoritative field and invalidation order are unknown. |
| `overview.alwaysShow`, `filterOut`, `unfiltered` | Stamped null in sender references, absent from native result | Names suggest filter caches; null-only data cannot establish what non-null values mean or whether deletion is safe. |
| `overview.presetHistoryKeys` | Composite-key map of dictionaries | History excluded; never wholesale delete to force refresh. Inner history semantics not owned. |
| `overview.restoreData` | Dictionary containing text, long and dictionary values | Restore data excluded; no proven deletion/reset. |
| `ui.overviewProfileName`, `overviewProfileNameInExport` | Stamped encoded strings | Local export/profile metadata, not a portable setup field or known invalidation target. Preserve pending evidence. |
| `tabgroups.overviewfilterTab`, `overviewsettingsTab`, `overviewstatesTab` and matching `_names` keys | Integer/text pairs | Settings-dialog selection candidates, not proven active-configuration dependencies. No reset permission. |
| `windows.stacksWindows`, `preferredIdxInStack3` | Cross-referencing maps described above | No wholesale stack deletion, detaching, or sender stack-ID copying. |

**Required gap:** there is no proved exhaustive protected-definition classifier,
no proved safe selection/cache update after replacing definitions/tabs/groups,
and no proved saved-state recipe for retiring surplus recipient overview windows.
No complete export/apply publication may be enabled merely because these synthetic
fixtures round-trip through the codec. Preserve unsupported data; refuse the
affected operation instead of choosing an arbitrary imported selection.

### Minimal safe observations needed (authorization required)

1. **Default classification:** initialize a genuinely fresh disposable recipient
   through EVE, close it and retain baseline bytes; then in that isolated profile
   choose a default overview and save one clearly invented custom definition.
   Close and capture after each single operation. An authorized schema reference
   or isolated custom-name collision observation must establish whether prefix
   names can be user-created and what identifies protected definitions. Do not
   try destructive conflicts in an ordinary profile or treat prefix repetition
   alone as proof. A no-change startup/shutdown control separates initialization.
2. **Selection/cache and retirement:** on a disposable deliberately different
   setup with two or more overview groups, record closed snapshots around one
   selected-tab change, one rename/filter replacement, and one secondary-window
   close/group retirement at a time. Include a no-change reopen/control. Compare
   only the candidate fields above (and report unexpected changed-key shapes).
   Verify which references EVE reloads, including a stale `_names` case and
   surplus-window stack refusal; do not pre-delete caches to make a test pass.
3. **Additional record variants:** if support for null bracket, `linebreak`,
   non-null label formatting or a locked target origin is needed, toggle just
   that option in an isolated profile and capture closed before/after/reload.
   This can establish exact values and absence behavior without widening enums
   or guessing resets from a name.

These are requests for narrow future observations, not instructions executed by
this task. Fresh-recipient Wingman creation/reload, deliberately different
recipient replacement, local display preservation, launcher visibility and UI
smoke acceptance from the design remain separate later gates.

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
saved/unsaved definitions, different labels/geometry/default identity and private
sentinels. Unrelated windows/sections exist to detect future over-broad copying.
History/private sentinels intentionally have invented opaque inner shapes; they
are not additional EVE schema evidence.

Tests use independent expected literals and mutate returned nested values to
check fresh copies. Codec-boundary tests use all four documents, verify exact
readback and input nonmutation, and can run with the existing native-codec seam.
A native binary's success proves **transport fidelity only**, not EVE recognition,
default classification, cache invalidation, window layout or publication safety.
The lexical/fixture tests are not feature acceptance and test no runtime importer.
