# Fittings clipboard format — approved conventional-import contract

**Task 1: approved, source-backed contract.** No production feature code is
included. User approval supersedes the earlier strict lossless-import gate:

> normal EFT import behaviour: Interpret drones/fighters as bay contents and
> preserve explicit cargo quantities. Show review warnings when loaded-ammo
> selection or offline state cannot be retained. Refuse exports that would
> misrepresent stored content.

Import is deliberately a **disclosed conventional interpretation**, not recovery
of every producer inventory/simulation detail. Export has the stricter obligation
of preserving existing canonical content or refusing before clipboard delivery.
The exceptions below do not authorize unknown-item skipping, mutation loss,
invented quantities, remote character writes or moving stored exported items.
One fit, local library only, browser-owned clipboard, unchanged schema,
fingerprints and scopes; no SDE/runtime dependency or fitting-legality simulation.

## Provenance and limits

Research checkout: `286596bef45ede12ffc28e301a59d602f3a02ae8` (`version bump`).
Public requests were captured on **2026-09-15 UTC** with the existing application
User-Agent and `X-Compatibility-Date: 2026-08-12`, plus `Accept-Language: en`.
No authentication or user clipboard was accessed.

Pinned reference:
[pyfa-org/Pyfa, service/port/eft.py](https://github.com/pyfa-org/Pyfa/blob/8b04f3b271e614b3e103853b44a7851a63d79d0e/service/port/eft.py),
commit `8b04f3b271e614b3e103853b44a7851a63d79d0e`.
The public commit API reports commit time `2026-07-31T21:45:06Z`; a released
producer version was **not established**. Retrieved source SHA-256:
`6a20ab1cb79857265d3930566796093d7d51b83fe9b3279b8427e54dbf9dc9ae`.
Pinned `eos/const.py` supplies slot/state enums; `service/const.py` supplies
`PortEftOptions`.

Fixtures in `tests/fixtures/evefittings/eft/` are **source-derived authored
examples, NOT live EVE or live Pyfa captures**. For the original examples,
AST-selected exporter functions were exercised with small authored fit/item
doubles and pinned enums; market sorting was stubbed. Added normalization/refusal
examples have explicit per-case authored provenance, not an exporter-run claim. No Pyfa application, game database, or simulation ran.
`cases.json` records the exact method and hand-authored model rows. A terminal LF
was added for readable fixture files. These examples do not prove in-game fit
viability or current EVE client import/export behavior.

`esi-evidence.json` contains projected **real public ESI responses**, request
method/URL/body, headers shared by the probes, capture timestamp, status and
original response-body hash. It deliberately omits unrelated name categories,
descriptions, attributes and most response headers; hashes identify original
bodies, not the projections. No EVE producer/version or live client capture is
available. Live Windows/EVE/Pyfa acceptance remains final smoke, not an implementation gate.

## Evidence retained — why import and export differ

Pinned `exportModules:129–163` writes `Module, Charge` without a quantity.
`ambiguous-inline-charge.eft` has a Republic Fleet EMP S inline selection and
Cargo quantity 100. Existing Wingman content distinguishes rack-charge quantity
1 from 120; those original alternatives remain in `cases.json`. Neither is a
count recovered from EFT or a live Pyfa/EVE capture. Module capacity 0.3 and
charge volume 0.0025 do not establish a supplied count. Approved import validates
the named charge then omits only that unquantified selection, with a warning.
It does not subtract from, add to, or otherwise alter the explicit Cargo stack.
Stored rack-charge rows remain real content and make export refuse.

Pinned `exportEft:67–126` omits absent sections; `exportDrones:166–202`,
`exportFighters:205–219` and `exportCargo:236–240` all emit `Type Name xN`.
The source exercise produced identical bytes for DroneBay/Hobgoblin II/5 versus
Cargo/Hobgoblin II/5, and FighterBay/Firbolg I/9 versus Cargo/Firbolg I/9.
The existing model keeps each pair distinct. Original alternatives/provenance
are retained, not rewritten to suggest lossless recovery. Approved import picks
the dedicated bay by convention and warns that cargo/bay intent is not preserved.

Some intact source sections can disambiguate intent, but the approved import
rule does not vary with section order or number of blank lines. Same-type bay
and Cargo quantity lines therefore become separate rows in the same bay and
aggregate canonically there; warnings accompany each line. This is the approved
interpretation of incoming EFT, **not** permission to relocate stored Cargo
rows during export. Pyfa import also uses category-first homogeneous sections
and merges drones (`importEft:243–372`, `Section:686–724`,
`AbstractFit:806–964`). Its unknown-item stubs, unmatched-line skipping and
fitability filtering remain explicitly unsuitable for Wingman.

## Accepted grammar and normalization

1. Accept one nonempty `[Hull Name, Fit Name]` header, splitting on the first
   comma. Fit names may contain further commas, but not brackets or control
   characters. Trim field edges; preserve fit-name spelling/internal spaces.
   Hull/type names cannot contain EFT delimiters comma, slash or square brackets.
   A second header or any unrecognized bracket directive refuses the whole fit.
2. Normalize CRLF/CR to LF, accept one initial Unicode BOM, and retain original
   one-based physical line numbers (including blank lines). Tabs/spaces may
   surround fields; reject other control characters. Ignore blank lines for
   allocation: they are visual separators, not location authority.
3. A module line is `Type Name`, optionally `, Charge Name`, optionally ending
   in ` /offline` (also accept `/OFFLINE`, as pinned importer does). No other
   state suffix is accepted. A quantity line is `Type Name xN` with an ASCII
   positive decimal integer; it cannot have charge/state suffixes. Reject zero,
   negatives, fractions, malformed suffixes and quantities above 2^31-1.
4. Exact supported empty markers are `[Empty Low slot]`, `[Empty Med slot]`,
   `[Empty High slot]`, `[Empty Rig slot]`, `[Empty Subsystem slot]`,
   `[Empty Service slot]`. Each advances its own rack counter by one and emits
   no item. Each resolved bare module advances its metadata-selected rack
   counter and emits one item at that position. Counters start at zero, never
   reset on blank lines, and never infer rack from section position. Overflow
   refuses; derive valid numbered flags from `contracts.RACK_BY_FLAG`.
5. Resolve English inventory names using NFC + casefold of edge-trimmed text;
   preserve verified ESI display spelling for export. Do not fuzzy-match,
   transliterate, collapse internal spaces, guess aliases or use cosmetic cache
   fallbacks. Require a unique matching inventory ID and matching verified type
   name; reject conflicting normalized bindings, missing results and partial
   metadata. The combined historical lower-case/space-padded probe is evidence
   of one returned Rifter result, not proof of general ESI normalization behavior.
6. Hull must be a published type in category 6 (ship) or 65 (structure).
   A fitted module must be published, category 7/32/66, with exactly one of the
   six rack effects below. Missing/multiple effects or nonmodule category refuse. A named inline
   selection must resolve to published category 8 (charge), even though omitted;
   an unknown name or non-charge is an error, never an omission warning.
7. Quantity lines use published inventory metadata: category 18 -> DroneBay,
   category 87 -> FighterBay, other supported types -> Cargo. Preserve the
   integer exactly. Modules with xN are cargo, not fitted module expansions.
   Unsupported implant/booster category 20 is refused even with xN; mutation
   references/details and any supplied per-instance alteration are refused,
   never replaced by their base type. Unknown/unsupported constructs never
   reach partial candidate persistence. No ship capacity, CPU, powergrid,
   skill, charge-compatibility, subsystem-layout or fighter-squadron simulation.
8. Bound input to 64 KiB UTF-8, 2,048 physical lines and 512 nonempty item
   lines (empty markers do not count as items). Use existing name limit 50,
   512 resulting rows and nonempty-content rule. Count/check before network;
   enforce rack limits during resolution. Check aggregate quantities per
   location/type against 2^31-1 as well, so duplicate lines cannot overflow.
   No truncation, fake bare-hull item or remote fitting ID.

Module row order is input order excluding empties/omitted selections; repeated
quantity lines remain exact rows in that order and canonicalization aggregates
them. A charge contributes no row and no slot advance. Offline contributes no
state or additional row. Warnings are ordered by source line, then charge
omission before offline omission when both apply. A quantity bay line has one
bay warning. Name/header limits and metadata errors refuse the entire fit.

## Required review warnings

Warnings are immutable structured `{code, line_number, message}` records and
are returned/rendered before **Add to library** is available. Every relevant
line receives its own warning; warnings cannot be silently hidden on success.
They belong to the reviewed ticket, not persisted fitting content or identity.

| Code | Meaning the review must communicate |
| --- | --- |
| `bay_convention` | This named quantity is interpreted as DroneBay/FighterBay content; EFT does not preserve Cargo/bay intent. |
| `loaded_charge_omitted` | This resolved inline charge selection is not retained because EFT specifies no quantity; explicit cargo quantities are unchanged. |
| `offline_omitted` | Offline state is not retained; the module remains in the fitting. |

Warnings accompany valid candidates only. Unknown inline charges, invalid
quantities, unsupported implants/mutations and malformed lines are whole-fit
errors, not new warning categories. UI renders warning/error text as text, not
HTML. Editing text invalidates both candidate and warnings; Add commits exactly
the reviewed normalized rows. Empty description; no character presence.

## Import/export decision matrix and executable examples

`cases.json` keeps original `expected_rows` / `alternative_rows` as historical
source evidence. New `approved_import` owns the normalized `items`, ordered
warnings or whole-fit error expected by future codec tests. `approved_export`
states whether that normalized candidate is exportable and independently marks
original alternatives that must refuse. Never derive these expectations from
the new parser. Newly added authored examples state their own provenance.

| Construct | Approved import | Export of stored content |
| --- | --- | --- |
| All six module racks, deterministic empty slots | One module per resolved rack position; holes advance only that rack | Preserve representable exact template positions; canonical round-trip required |
| Explicit cargo charges/scripts/spare modules xN | Exact Cargo count | Exact Cargo count |
| Quantity drones/fighters, including apparent cargo sections | Dedicated bay, exact count, warning per line | Dedicated bay allowed; stored Cargo drone/fighter rows refuse |
| Same type in bay and apparent Cargo sections | All quantity lines use its dedicated bay; warnings, no count loss | Any stored Cargo drone/fighter component refuses, even if same type also in bay |
| Inline module charge, with or without explicit cargo | Validate charge; retain module/Cargo, omit selection with warning | Any fitted charge row refuses; never emit a lossy inline selection |
| `/offline` | Retain module, omit state with warning | No state is stored/emitted |
| Mutation details/references, implants/boosters, unknown or malformed item | Whole-fit refusal | Refuse if unsupported/unrepresentable |
| Invalid-location rows, bare hull, multiple fits, overflow | Whole-fit refusal | Refuse |
| Description/aliases/collections/source provenance | Not part of EFT; import empty description | Saved preferred name only; no provenance leakage |

**Export invariant:** before returning text, `resolve_eft(parse_eft(text),
inventory)` must reproduce the original full `CanonicalContent`, including
ship, type, location and quantity. Digest equality alone is insufficient. Use
one verified snapshot for rendering and internal resolution; no network in the
codec. `EftWarning` does not enter canonical equality: re-imported dedicated bay
text legitimately warns about the convention while reproducing stored bay rows.

Render low/medium/high/rig/subsystem/service racks in that order from the exact
deployment template, ordered by numbered position. Emit required leading/interior
empty markers; omit trailing holes and absent racks. A fitted template row must
be a single supported module in the metadata-matching rack; duplicate occupancy,
non-unit fitted quantities, charge rows, Invalid or absent deployment template
refuse rather than relocate/expand stored rows. Nonrack rows are rendered in
DroneBay, FighterBay, Cargo order, aggregating identical location/type stacks
with checked bounds and sorting by type ID. Use one blank line between racks,
two between major sections, one between drone/fighter subsections, and LF with
one terminal LF. No unescaped/control-bearing type/fit names or fallback labels.
Stored bay/type mismatches and Cargo drones/fighters fail internal equality;
refuse them explicitly before producing actionable text. Never touch clipboard
on an export refusal, and never mutate the stored template during export.

## Public metadata findings

Endpoints were called before tracing shared transport behavior. IDs/names POSTs
are read-only lookups, not character writes. Only `inventory_types` results from
`/universe/ids/` and `inventory_type` rows from `/universe/names/` belong in fitting
resolution: the real names lookup also matched unrelated character/corporation
categories, deliberately omitted from committed projections.

| Representative type | Type ID | Group/category | Slot-effect ID/name |
| --- | ---: | --- | --- |
| Rifter | 587 | 25 / 6 | Hull, not a rack item |
| Damage Control II | 2048 | 60 / 7 | 11 / loPower |
| 1MN Afterburner II | 438 | 46 / 7 | 13 / medPower |
| 200mm AutoCannon II | 2889 | 55 / 7 | 12 / hiPower |
| Small Projectile Burst Aerator I | 31668 | 777 / 7 | 2663 / rigSlot |
| Tengu Defensive - Covert Reconfiguration | 45589 | 954 / 32 | 3772 / subSystem |
| Standup Market Hub I | 35892 | 1321 / 66 | 6306 / serviceSlot |
| Hobgoblin II | 2456 | 100 / 18 | Category selects the approved bay convention |
| Firbolg I | 23059 | 1652 / 87 | Category selects the approved bay convention |
| Republic Fleet EMP S | 21898 | 83 / 8 | Cargo count or disclosed inline omission |
| Astrahus | 35832 | 1657 / 65 | Structure hull for service example |

Type -> group -> category and the **full** `dogma_effects` set are sufficient
for these rack classifications without an SDE. Filtering to `is_default` would
miss ordinary rack effects. This sample is not an exhaustive inventory policy.

Observed failures/edge cases:

- `/universe/types/2147483647/`: 404, `Type not found`.
- `/universe/types/0/`: unexpectedly 200, unpublished `#System`, type ID 0;
  not a valid positive inventory ID for the existing model.
- Unknown input name in `/universe/ids/`: 200 with no corresponding inventory
  result; a successful HTTP status is not complete resolution.
- Object instead of name-list request to `/universe/ids/`: 400. This is a real
  malformed-**request** response, not evidence of malformed successful JSON.
  No malformed successful upstream response was observed or fabricated.

`wingman/eveesi.py` already has unauthenticated `get`/`post`, bounded transport,
compatibility headers, hardened paths and idempotent names/IDs retry admission.
Its generic JSON decode is not inventory-schema validation. Any later resolver
must reject partial/mismatched/malformed metadata without partial library writes.
No transport modification or new runtime dependency is justified by this research.

## Concrete internal interfaces for Tasks 2–3

These are signatures to implement next, not production definitions added by
Task 1. `eft.py` depends only on existing model/contracts and the standard
library. It performs syntax/semantic conversion with injected immutable metadata,
not HTTP. `inventory.py` owns the injected EsiClient, strict boundary validation,
stop checks and bounded caches; imports flow inventory -> eft -> model/contracts,
never back from eft to inventory. Controllers orchestrate these two layers.

```python
# All records below live in eft.py, are frozen dataclasses, and own only
# immutable values. RemoteItem and LibraryEntry come from existing model.py.
@dataclass(frozen=True)
class ParsedLine:
    line_number: int
    kind: Literal["module", "quantity", "empty"]
    type_name: str | None
    quantity: int | None
    charge_name: str | None
    offline: bool
    empty_rack: str | None

@dataclass(frozen=True)
class ParsedEft:
    ship_name: str
    name: str
    header_line_number: int
    lines: tuple[ParsedLine, ...]

@dataclass(frozen=True)
class InventoryType:
    type_id: int
    name: str
    group_id: int
    category_id: int
    published: bool
    dogma_effect_ids: frozenset[int]

@dataclass(frozen=True)
class InventorySnapshot:
    types: tuple[InventoryType, ...]
    name_bindings: tuple[tuple[str, int], ...]

@dataclass(frozen=True)
class EftWarning:
    code: Literal["bay_convention", "loaded_charge_omitted", "offline_omitted"]
    line_number: int
    message: str

@dataclass(frozen=True)
class EftCandidate:
    ship_type_id: int
    name: str
    items: tuple[RemoteItem, ...]
    warnings: tuple[EftWarning, ...]
    verified_names: tuple[tuple[int, str], ...]

class EftError(ValueError):
    def __init__(self, code: str, message: str, *, line_number: int | None = None): ...

def parse_eft(text: str) -> ParsedEft: ...
def resolve_eft(parsed: ParsedEft, inventory: InventorySnapshot) -> EftCandidate: ...
def render_eft(entry: LibraryEntry, inventory: InventorySnapshot) -> str: ...

# inventory.py imports these records from eft.py; eft.py never imports it.
class InventoryResolver:
    def __init__(self, client: EsiClient, *, stopping: Callable[[], bool]): ...
    def for_import(self, parsed: ParsedEft) -> InventorySnapshot: ...
    def for_export(self, entry: LibraryEntry) -> InventorySnapshot: ...
```

### Record invariants and ownership

- `ParsedLine`: module has type_name, quantity=1, optional charge_name/offline,
  empty_rack=None; quantity has type_name and positive quantity, no charge/state/
  rack; empty has empty_rack and all name/quantity fields None, offline=False.
  Retain physical line numbers, not raw clipboard text or a guessed type ID.
- `InventoryType` fields come from verified type/group responses, not invented
  ESI fields. `dogma_effect_ids` is the complete set, including non-default
  effects. Snapshot types are unique, sorted by type_id. `name_bindings` is a
  sorted tuple of unique normalized name keys to verified IDs, including every
  requested hull/module/quantity/inline-charge name and verified canonical name
  key needed to resolve rendered output. Conflicting associations refuse.
- Snapshots are detached immutable request subsets, not views into mutable LRU
  caches. At most 1 + 2*512 types/name keys are required for an import; exported
  stored entries need hull + item IDs. Because aliases/fuzzy matching are not
  allowed, a submitted normalized key must equal its canonical name key.
  Cache eviction cannot mutate a candidate or a retained snapshot. Resolver
  cache remains bounded separately (4,096 type records, bounded related groups).
- `EftCandidate.items` is nonempty, <=512 existing RemoteItem rows; each
  quantity and aggregate is bounded. `verified_names` is sorted/unique and
  contains exactly the hull plus persisted item IDs, at most 513 names. A
  charge-only omitted ID is not needed for the display-cache handoff. Its
  verified name can appear in the line warning after resolution. Warnings are
  at most two per nonempty item line, bounded to 1,024; do not truncate them.
- Controller retains the whole immutable candidate (including names/warnings)
  in its single 15-minute review ticket. Add needs no resolver-cache lookup and
  cannot accept browser-supplied rows. Handoff verified names to TypeNameCache
  for new, duplicate and no-op import before notification/success; cosmetic
  persistence is best-effort, separate from the library transaction.
- `EftError` stores code/message/line_number; it is a whole-fit refusal with physical line_number where
  attributable; error results carry no partial candidate/items/warnings/text.
  No HTTP or mutable mappings are hidden in the pure records. Import metadata
  includes inline charges despite their omission; only parsed inventory names
  or stored inventory IDs go to public ESI, never custom fit names/raw text.

Bridge/controller contracts (new methods, not implemented here):

```text
export_eft(entry_id: object) -> {ok, text, error}
review_eft(text: object) -> {ok, review_id, name, ship_name, items, warnings, existing_entry_id, error}
import_eft(review_id: object) -> {applied, persisted, entry_id, created, error}
locate_entry(entry_id: object) -> {ok, entry_id, workspace, error}
```

`review.items` is an ordered list of `{flag, location, type_id, type_name, quantity}`:
flag/type_id/quantity come from candidate rows, location is the canonical rack or
exact bay, and type_name comes from candidate.verified_names. This is a new review
projection, not a claim about an existing endpoint. `warnings` is an ordered JSON
list of the three-field warning records above.
On refusal, items/warnings are empty, review_id is empty and error is nonempty;
no actionable partial candidate. Successful warnings do not set error. Client-side
presentation is never persistence authority.

## Verification boundary

Task 1 fixtures and public metadata are a source-backed executable contract for
Task 2 tests: compare approved exact rows, warnings and refusal cases; preserve
historical alternatives as export counterexamples. Verify all six effects,
physical line numbers, offline+charge warning order, duplicate bay quantities,
name association, bounds and canonical export equality with injected data.
No parser, resolver, controller, UI or persistent model changed in Task 1.
Real Windows/WebView2 clipboard and EVE/Pyfa live acceptance remain mandatory
final smoke for the shipped feature; they do not block implementation now.
