# Curated complete-setup content

## Admission record — 2026-09-08

The bundled library contains contributor-approved **complete Wingman UI setups**,
not upstream overview-only YAML, synthetic examples, or recommendations for
particular gameplay roles. The contributor personally arranged both layouts at
**3840×2160 with 150% EVE UI scale** and chose **FlyGD Wingman** as the layout
credit. That credit is separate from the original overview authors below.

The Import setup page shows the setup description and intended display context,
not the provenance record. Source URLs, author credits, revisions, licensing and
validation evidence are maintained here and in `THIRD-PARTY-NOTICES.md`; the
original notices and license files still travel with the bundled artifacts.
Removing that material from the form does not change content admission or imply
packaged WebView2/live-EVE acceptance.

Only the two deliberately supplied portable exports were inspected and copied.
Their bytes were not normalized, repaired, reformatted or replaced with an older
public export. No raw DATs, account/character identities, local preference files,
private capture receipts or personal paths are included. Text review of every
filter/tab name and label found generic pack names, EVE formatting and canonical
default references; no personal names, paths, URLs or credentials. Numeric
memberships are overview group/state IDs, not recipient identities.

### Exact artifact binding

These hashes are admission facts, independent of the manifest. Filenames are
resolved from the validated catalog ID and revision. Both revisions are **1**;
manifest format is `wingman-setup-catalog` version 1 and both artifacts retain
`wingman-preset` version 1, type `ui-setup`.

| File under `wingman/assets/setup-presets/` | SHA-256 | Bytes | Filters | Tabs | Overview groups | Ordered labels | Layout records |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `iridium-default-r1.json` | `6b212cdc34a8ed8b2a65b53a69e1f4b95d9d1f66abf1e504da18beace24be8a2` | 43447 | 38 | 9 | 3 | 7 | 12 |
| `zs-default-r1.json` | `4c894d18da520457d9622ac4474ae0e08eeaf40574dca1e6cde607b6505e1bb3` | 62577 | 57 | 6 | 3 | 7 | 12 |

`tests/test_setup_catalog.py` binds this table and manifest to independently
pinned candidate hashes, validates every entry through the public catalog/parser,
and rejects orphaned assets and synthetic fixture content. Changing content
requires a deliberate new admission/revision, not simply recomputing a checksum.

### Arrangement and display are different facts

- **Iridium — Wingman layout** (`iridium-default`): ordered window groups
  `[[0,1,2,5,6,7],[3,8],[4]]`; primary overview geometry
  `[1994,327,566,509,2560,1440]`.
- **Z-S — Wingman layout** (`zs-default`): ordered window groups
  `[[0,1,3,5],[2],[4]]`; primary overview geometry
  `[1994,266,566,570,2560,1440]`.

The arrangements also differ in secondary overview placement, Selected item,
Probe scanner and Watch list placement, filter bodies and ordered label content.
Both preserve all seven label records, including the disabled ship-name record,
linebreak and null-type record. These are useful saved arrangements from the
contributor, not renamed copies of a test fixture.

**Geometry stays as saved.** All non-null geometry records carry a **2560×1440**
reference. The advertised 3840×2160/150% describes the contributor's display,
not replacement coordinates or recipient preferences. Wingman neither rescales
these records to 4K nor fits them to a recipient's display. Null geometry/state,
target-origin/lock and HUD-offset fields retain the existing full-setup clear
semantics. Recipient resolution, UI scale, monitor and other local preferences
remain in the recipient's own files. No running EVE window is moved or resized.

## Iridium overview provenance and rights

- Original overview author/copyright: **IridiumOps**.
- Public source: [pinned Iridium tree](https://github.com/iridiumops/overview/tree/afb001962f5458dee1f21be00c20dc80121ecffb),
  `releases/iridium_overview_20260728-v3111_main.yaml`, **v3.11.1 main**.
- All **38** candidate filter memberships (`groups`, `filteredStates`,
  `alwaysShownStates`) match that public main YAML. This claim concerns those
  filter bodies, not whole-file identity: upstream has **13 tabs**, while the
  contributor intentionally arranged **9**. The Wingman JSON adds its own full
  supported window arrangement and carries the contributor's ordered labels.
- [Pinned `license.md`](https://raw.githubusercontent.com/iridiumops/overview/afb001962f5458dee1f21be00c20dc80121ecffb/license.md)
  makes v2.1.0 onward available under **MIT OR BSD-3-Clause**. Wingman elects
  **MIT**. `Iridium-MIT.txt` retains the exact upstream MIT copyright, permission
  and warranty text and the upstream EVE copyright notice. No upstream code is
  vendored. The downloaded `license.md` is 3492 bytes, SHA-256
  `129d6b97901cab1a7c609b8c52e0cb39cdce6ba5b953f16724d0570e8a7a02ba`.

## Z-S overview provenance and rights

- Original overview credits in the published README:
  **Zirio — YAML Coding, Pack Maintenance & Long Term Updates**;
  **Deuce Syundai — Design & Text Formatting**.
- Current pack maintenance: **Kismeteer**. Sources:
  [Kismeteer's overview page](https://www.wckg.net/home/kisover) and the original
  author's [2026 Customizer README](https://github.com/Arziel1992/Z-S-Overview-Customizer/blob/03537e87941296176ace73cda96a60ca78af817a/README.md).
  The latter explicitly describes Kismeteer as the volunteer maintaining Z-S.
- **v10.07.29** is the contributor's identification of the **in-game obtained
  release**. It is not inferred from the historical git trees or from a hash
  match to a public v10 export.
- Historical original source: [GitLab project 7160548](https://gitlab.com/Arziel/Z-S-Overview-Pack),
  master commit `594b37af9f91714ed7f0a41169bef810d2a983a6`.
  [GitHub mirror](https://github.com/Arziel1992/Z-S-Overview-Pack/tree/9c7dd4564f6db633dad44d3078d862dcc4ee0708),
  commit `9c7dd4564f6db633dad44d3078d862dcc4ee0708`.
  These 2019 trees document v9.00.0347, credits and the published **GPLv3**
  pack notice. **Neither is an exact v10.07.29 export source.**
- **Contributor attestation accepted for admission:** after being asked whether
  GPLv3 covers redistribution of this in-game release, the contributor confirmed:
  “in-game it provides the licsense approval for redistrubition”. This records
  the contributor's confirmation of the in-game redistribution approval; it is
  **not a claim that Wingman independently read the in-game notice**, and the
  quotation is the contributor's statement, not verbatim licence text.
- `Z-S-GPL-3.txt` preserves the original published GPLv3 declaration, README
  Notice (including the historical SaraShawa-origin statement), EVE copyright
  notice, original author credits, and complete upstream `LICENSE.md`. The
  downloaded [pinned licence](https://raw.githubusercontent.com/Arziel1992/Z-S-Overview-Pack/9c7dd4564f6db633dad44d3078d862dcc4ee0708/LICENSE.md)
  is 35141 bytes, SHA-256
  `589ed823e9a84c56feb95ac58e7cf384626b9cbf4fda2a907bc36e103de1bad2`.
  The editable portable JSON is distributed alongside its licence. This is a
  contributor-arranged full setup, not an unchanged upstream YAML release.
- **No Customizer AGPL code or data is bundled.** Its v10.06.09 data was not
  substituted for this export. Its AGPL licence is not transposed onto the
  separately obtained Z-S pack; the README serves only as maintainer evidence.

## Verification and its limits

Strict parsing and text/privacy inspection passed on both exact artifacts.
Earlier engineering work exercised their real Windows native-codec
review/create/re-export paths on **invented recipients**; see
[the verification record](../curated-preset-library-verification.md) and
[physical preset compatibility](setup-preset-compatibility.md).

The shipped-library regressions in `tests/test_ui_setup_integration.py` obtain
bytes through real `Api.eve_settings_setup_catalog` / `_entry` facades and call
the existing review/create pipeline with the real release codec. The recipient
fixtures have distinct filters, label order, four overview groups, geometry,
identities and local preference bytes. Assertions inspect decoded output directly:
all imported filter bodies and tabs, ordered labels including multiplicity and
formatting types, every supported geometry/state record, clear fields, retained
identities/non-owned sections, unchanged source/base and unselected files,
single-use publication, and stale-recipient-review refusal. Literal group,
filter, label and geometry facts supplement selected-artifact comparisons; an
exporter round trip or summary is not the sole oracle.

Package-data and PyInstaller collection include the manifest, artifacts and
licences. The post-freeze build gate validates source entries and compares the
actual `_internal/assets/setup-presets` inventory and bytes against source.
Tests execute that gate on temporary bundle trees with missing, altered and
extra files. **Executing the snippet is not a PyInstaller build or an installed
app test.**

**Packaged-library WebView2, launcher discovery and live-EVE acceptance remain
unperformed.** Parser/native-codec evidence is not gameplay validation or a
promise of fit on other displays. Content admission does not authorize release,
installation, live-profile writes or OS settings changes. Operator-authorized
manual gates remain in [the smoke checklist](../smoke-checklist.md).

## Community admission, not a publishing service

Propose a deliberately exported, privacy-reviewed **full** setup with an
arrangement, intended display context, contributor credit, source/version
references and redistribution evidence for every overview source. Preserve
original notices and distinguish firsthand evidence from contributor
attestations. Admit exact bytes and record their hash, revision and actual test
results; reject incomplete, synthetic or unapproved content. Add native tests
against a distinct invented recipient and leave unperformed manual checks open.
The library is bundled with releases, not fetched over a network. Import creates
an independent local copy: a later library update never rewrites existing copies.
There is no in-app publishing or automatic subscription to upstream changes.
