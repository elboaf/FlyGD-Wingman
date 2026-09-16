# Remaining Local Combat Model Implementation Plan

**Status: contract reviewed; implementation/lane/platform/deployment gates remain.**

> **For agentic workers:** Core Tasks 1 and 4 and row-lifetime fencing are implemented, reviewed and integrated; do not redispatch them. Remaining tasks require the revised shared validation contract and coordinator lane authorization. This publication alone authorizes no new implementation.

Core evidence: `docs/fleet-combat-model-core-verification.md`; original commits `10271167` / `3571bd0e`, integrated as `0d3cac89` / `e85d7dff`. Full core verification: 13,466 passed, 13 expected Windows skips; independent reviews/polish clean. All six shared-contract findings are addressed and independently reviewed; implementation/lane/platform/deployment gates remain.

**Goal:** Expose ten-second directional DPS, thirty-second local combat activity, and independently expiring incoming NEUT/POINT/SCRAM observations without changing Alerts or collection rosters.

**Architecture:** Keep `FleetMetrics` as the single mutable, serialized owner. Add immutable local observation values and pure deadline readers; transport and presentation consume them later. No new worker, clock service, package, persistence or identity lookup.

**Tech stack:** Python dataclasses, injected UTC/monotonic clocks, pytest, uv, Ruff.

**Authority:** updated `docs/fleet-telemetry-v2-design.md` §§2–4 approves the breaking shared-fleet cutover; sibling `fleet-telemetry-v2-contract.md` proposes the single required API/limits. Earlier proposals/reconciliation are supporting evidence only where consistent. No old-wire or mixed-version support is required.

## Review decisions and authority

- **Approved:** DPS `(now−10s, now]`, fixed denominator ten, Decimal half-up; row/effect visibility requires `now < deadline`, maximum thirty seconds from accepted event time.
- Damage in either direction counts even when rounded DPS is zero. Misses, chatter, discovery, snapshots and hydration never renew activity. Preserve parsed literal-zero damage acceptance rather than introduce a new rejection; retain zero-GJ incoming NEUT.
- Preserve damage's existing >2s future rejection/diagnostic and ≤2s clamp. Preserve EWAR's existing cap-only future behavior; do not silently unify the policies.
- Independently retain each POINT/SCRAM name; NEUT is unnamed. One unnamed bucket per kind coalesces unknown and unretained sources without a count or completeness claim. Damage/new named sources cannot refresh another bucket.
- **Closed foundation handoff, independent-review gate:** `fleet-telemetry-v2-contract.md` §4.1 and scratch `fleet-combat-v2-profile.json` own all limits/Unicode rules. C installs byte-identical W `wingman/data/fleet-combat-v2-profile.json` and A `src/core/fleet-combat-v2-profile.json`; C owns pure W `wingman/combatprofile.py` / A `src/core/fleet-combat-profile.ts` and shared `tests/fixtures/fleet-combat-v2.json`. M imports `LIMITS`, `normalize_observed_name`, `validate_observed_name`, `observed_name_key` from `wingman.combatprofile`; never transport or host Unicode. W Python3.11 uses Unicode14, so profile consumption must not require the Unicode16 generation runtime. C/I own primitive fixtures and package-data/frozen-resource verification. Derive capacities; no independent constants.
- Keep safe extraction conservative: known separated pilot/ticker markup can yield a name; unresolved `Doran Velk  Proteus` yields `None`. An unseparated bare `<b>` source also yields `None` initially, including the NPC fixture; do not introduce a player/NPC classifier to resolve ambiguity.
- Preserve positional dataclass prefixes and every existing parsed `source` value byte-for-byte after UTF-8 encoding. Fleet attribution is additive; no change to Alert mappings, victim gate, NPC filtering, hold, cooldown or focus behavior.
- Stable accepted-observation identity and its immutable local deadline are required handoffs. Server origins, anchor renewal, session recovery continuity and retained clock-origin maps belong to transport, not this lane.

## Evidence and file boundaries

- `telemetry/model.py`: append after all existing fields of `ParsedFact`, `CombatFact`, `FleetRow`, `FleetSnapshot`; existing constructors are positional.
- `telemetry/metrics.py`: `_consume_roster`, `_consume_source`, `_consume_fact` already enforce source/session/sequence admission; `_ingest_damage`, `_ingest_ewar`, `_refresh_activity`, `snapshot` currently couple tags to one deadline.
- `telemetry/parsing.py:parse_line` gates tackle by `_extract_target`/`_target_is_character`; `_extract_source` also feeds Alerts. Do not change these existing helpers or their alias contract.
- `telemetry/gamelogs.py:GameLogStream._read_source` explicitly copies parsed fields; additive attribution needs a copy here, not a tailer redesign.
- `telemetry/coordinator.py:_process` fans original `source` into `AlertEvent`; its snapshot publication preserves fields with `replace`. Read-only integration boundary.
- Complete snapshots underpin settings and duplicate suppression (`ui/api.py`, documented in model proposal). Never remove quiet, unbound or hidden roster members in metrics.
- Preserve timing PR #246 and its scheduling invariants. Transport owner replaces the wire projection with the required new contract; this lane has no wire, controller, UI, consent, schema, source-lifecycle policy or Alert production edits. Dropping wire compatibility does not authorize unrelated internal refactoring.
- Remaining M ownership: modify `wingman/telemetry/{model,parsing,gamelogs,metrics}.py` only for fact attribution/effects and their named tests below; extend existing `tests/test_telemetry_combat.py` for appended fact fields. `wingman/telemetry/combat.py` and its core tests already exist; no recreation. C owns the foundation helpers/profile/fixtures; I owns packaging/hot-file integration. Reuse existing gamelog fixtures unchanged. Other tests are read-only gates.

## Internal handoff — core implemented, attribution still pending

The values/readers below are implemented internal Python interfaces, not wire DTOs. Only the appended `observed_name` fact fields remain to add in Task 2; do not recreate the core classes/readers.

```python
# model.py; frozen dataclasses. No evidence/overflow/read-result wrappers.
ObservationId = tuple[UUID, int]  # opaque source-lifetime token + accepted sequence
# Append observed_name: str | None = None to ParsedFact and CombatFact.
EffectObservation(kind: str, expires_at_mono: float,
                  observation_id: ObservationId, name: str | None = None)
CombatActivity(expires_at_mono: float | None = None,
               observation_id: ObservationId | None = None,
               observations: tuple[EffectObservation, ...] = ())
# Append combat: CombatActivity | None = None to FleetRow.
# Append sampled_at_mono: float | None = None to FleetSnapshot.

# combat.py; reads retain original deadlines and identities, never resample UTC.
def read_combat(row: FleetRow, *, now_mono: float) -> CombatActivity | None: ...
def combat_row_visible(row: FleetRow, *, now_mono: float) -> bool: ...
def next_combat_transition(rows: tuple[FleetRow, ...], *, now_mono: float) -> float | None: ...
```

`combat=None` means absent internal combat evidence, never fresh activity or a supported old wire row. Preserve that default for existing positional/internal constructors; model-produced inactive rows carry `CombatActivity()`. Pure visibility requires unexpired activity and available metrics; no old-format display policy exists. `read_combat` filters expired observations without changing the original row deadline/ID or renewing survivors. Local availability means either directional measurement is non-None; this is not a remote DTO predicate. The existing internal `ewar` summary still uses the old shared EWAR hold until Task 5 replaces its producer, in SCRAM, POINT, NEUT order.

Allocate a fresh opaque lifetime token on initial state/source establishment and each actual source/session invalidation; preserve it across unchanged active rebinds. Retain `(token, sequence)` with whichever accepted event supplies a strictly later deadline. Equal/older deadlines retain their identity; rejected facts change neither. Effect and row IDs may reference the same fact; consumers distinguish row versus `(kind, normalized-name-or-None)` slots. Reset/recreation cannot reuse a lifetime token. No native identity, raw line, source path, token or sequence is authorized on wire.

Transport can key its retained origin map by character, slot and this ID, retaining the original local deadline. Repeated snapshots/reads must present identical keys for surviving evidence. Losing transport continuity must not prompt this model to issue replacement IDs for cached observations. Stale snapshot admission and clock-origin persistence outside restarted transport owners remain transport responsibilities.

## Ordered TDD tasks

For each task after implementation authorization: write the specified regression first; inspect a behavior-specific RED; implement minimally; rerun GREEN; inspect diff and commit only owned files after review. Existing positional/Alert controls may already pass and must not be reported as RED evidence. This draft revision executes none of those actions.

### 1. Immutable values and non-renewing read contract — COMPLETE

Implemented in `model.py`, `combat.py` and `test_telemetry_combat.py`. The 35 cases cover immutability, preserved positional defaults, absent/inactive evidence, strict 30/40/50 transitions and stable ordering/identity. Both review verdicts passed; included in full core verification. Fact attribution fields were explicitly deferred to Task 2 below.

### 2. Safe additive tackle names with unchanged Alert sources

**Files:** modify `wingman/telemetry/model.py`, `wingman/telemetry/parsing.py`, `tests/test_telemetry_parsing.py`; extend positional-prefix coverage in `tests/test_telemetry_combat.py`; reuse gamelog fixtures unchanged.
**Interfaces:** append `observed_name: str | None = None` to existing `ParsedFact` and `CombatFact`; add `_extract_observed_name(line: str) -> str | None`. Only victim-proven incoming tackle populates the parsed name. The shared-contract foundation owns the canonical validator/profile; this task consumes it rather than creating another.

- [ ] RED: `player_scramble.txt` yields `Talia Renn`; exact existing source remains `Talia Renn [KVOS] Taranis`. `player_unresolved.txt` POINT remains present with name `None`, source `Doran Velk Proteus`; `npc_scramble.txt` remains unnamed with source `Emergent Preserver`.
- [ ] RED with Alert regression controls: assert `.source.encode("utf-8")`, `patterns.match_line` results and `patterns.is_likely_npc` decisions against explicit baseline expectations, not only two paths calling the same changed parser. Cover player/NPC damage, misses, drone possessives, decorated NPC-like names, malformed amount/timestamp and NEUT (still no Alert).
- [ ] RED: safe Unicode accepted at reviewed scalar/byte boundaries; overflow, surrogate/control/format characters, empty/ambiguous markup become unnamed without truncation or loss of the effect. Reject forbidden characters before whitespace collapse can hide them; obtain exact validation vectors from contract owner.
- [ ] GREEN: extract only from established name/ticker/hull separation after existing victim admission. Preserve `_SOURCE_RE`, `_extract_source`, `_TARGET_RE`, fallback greediness and `_target_is_character`; bound extraction using the reviewed contract, not a whole-line rejection that changes Alerts.
- [ ] Run: `uv run --no-sync python -m pytest tests/test_telemetry_parsing.py tests/test_alerts_patterns.py -q`; review/commit parser change.

### 3. Carry attribution through the existing source boundary

**Files:** modify `wingman/telemetry/gamelogs.py:GameLogStream._read_source`, `tests/test_telemetry_gamelogs.py:TestCombatFactParsing`.
**Interfaces:** copy `ParsedFact.observed_name` into the appended `CombatFact.observed_name`; all other fields retain their existing meanings.

- [ ] RED: append the real named-tackle fixture through `_stream`/`_log`/`_collect`; emitted fact carries the safe name, unchanged source bytes, original timestamp and matching source generation/ID. Stream-only assertion must fail before the copy is added.
- [ ] RED/controls: same named-victim line read by bystanders/outgoing owner emits no incoming tackle; split UTF-8 still preserves text; ambiguous source keeps effect unnamed. Existing truncation, retirement and restart/rebaseline tests must remain unchanged and green.
- [ ] GREEN: add only the one field copy; do not alter collection, replay prevention, decoding or lifecycle behavior.
- [ ] Run: `uv run --no-sync python -m pytest tests/test_telemetry_gamelogs.py tests/test_telemetry_coordinator.py tests/test_alerts_patterns.py -q`; review/commit stream handoff.

### 4. Independent row activity and directional ten-second metrics — COMPLETE

Implemented as the core's Task 2 in `metrics.py` and `test_fleet_metrics.py`: 49 deterministic cases, real RED/GREEN and an incoming-refresh mutation control. Includes real snapshot sampling, zero/rounded-zero and delayed activity, correction sequences, complete rosters and row-token lifetime/reset/rebind fencing. Both task and final core reviews passed; included in full verification. Existing EWAR tag hold deliberately remains for Task 5.

### 5. Independent effect buckets, bounded retention and lifetime fencing — REMAINING EFFECT WORK

Core row-token allocation/reset/rebind fencing already exists. Extend those same paths to the new effect map; do not introduce another lifetime token or reimplement completed row activity.

**Files:** modify `wingman/telemetry/metrics.py:_CharacterState`, `_ingest_ewar`, `_consume_source`, `_consume_roster`, `reset`, `snapshot`; modify `tests/test_fleet_metrics.py`.
**Interfaces:** private `(kind,observed_name_key(name)-or-None)` observation map exports immutable `EffectObservation` tuples; same accepted-deadline/ID rule as row activity.

- [ ] RED: SCRAM A at 0, SCRAM B at 10, damage at 20 → A expires 30, B 40, row 50. Same attacker POINT 0/SCRAM 5 remain independent. Incoming NEUT (including zero GJ) renews only NEUT; damage never renews an effect. Replace only old tests asserting outgoing damage prolongs prior tags.
- [ ] RED: unknown at 0/B at 10 → unnamed expires 30/B 40; retain reviewed maximum existing names, coalesce further unknown/overflow into one independently expiring unnamed bucket. Refreshing a retained name cannot renew it. Expired names free capacity before admission; first safe spelling stays stable while a casefolded key lives; no counts are inferred.
- [ ] RED: delayed older evidence never shortens or re-identifies newer bucket/row authority. Repeated snapshots and monotonic reads, UTC changes during reads, or unrelated events preserve survivor IDs/deadlines. Genuine later evidence changes only affected IDs; two reset/recreated owners cannot collide.
- [ ] RED: reset, retirement then same-source rebind, source replacement, client-session replacement and roster removal clear observations/IDs. Delayed old envelopes cannot resurrect them. Repeated unchanged roster/bind preserves live evidence; quiet/NO LOG rows remain complete.
- [ ] GREEN: prune observations on ingestion and snapshot, retain each bucket's own deadline, renew unnamed only from unnamed/unretained incoming evidence. Derive existing internal summary tags from surviving observations; remove old tag-set/shared-EWAR coupling and update its obsolete explanatory docstrings.
- [ ] Run: `uv run --no-sync python -m pytest tests/test_fleet_metrics.py tests/test_telemetry_combat.py tests/test_telemetry_coordinator.py -q`; review/commit final model.

## Verification and integration gates

Execute from the assigned implementation worktree; these commands are planned, not claimed run:

```sh
uv sync --locked --extra dev
uv run --no-sync python -m pytest tests/test_telemetry_combat.py tests/test_telemetry_parsing.py tests/test_telemetry_gamelogs.py tests/test_fleet_metrics.py tests/test_telemetry_coordinator.py -q
uv run --no-sync python -m pytest tests/ -k alert -q
uv run --no-sync python -m pytest tests/test_fleetsharing_projection.py tests/test_fleetsharing_cadence.py tests/test_fleetsharing_protocol.py tests/test_api_remote_fleet.py -q
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
```

- [ ] Before lane merge: scoped review confirms positional/internal/Alert behavior, bounded unknown buckets, complete rosters, independent deadlines and stable local ID semantics. Run `polish-core --fix`, inspect only authorized edits, rerun gates and produce `change-explainer` handoff; do not fix unrelated failures.
- [ ] Coordinator integrates reviewed commits only; hot files in transport, coordinator and UI remain with their named owners. No push, shared-branch merge, deployment or production changes from this lane.
- [ ] Integrated acceptance requires Node/native-codec prerequisites in `docs/overview-layout-sharing-verification.md`, full `uv run --no-sync python -m pytest tests/ -rs`, Linux/Windows CI, and cross-language new-contract/two-account integration plus separately authorized live two-PC/UI acceptance. Unit tests do not certify rendering or transport age continuity.
- [ ] C/I gates replace old-wire assertions where behavior intentionally changes: required `/api/fleet/v2/*`, JSON `protocol:2`, unchanged `fleet-v1` signing scheme, explicit old-request rejection and controlled cutover fencing. Shared current fixtures exercise incoming-only, NEUT-only, multiple/unknown aggressors, retained origins and 3/10-second transport expiry independently of the 30-second activity hold. Preserve scheduling/admission and primitive crypto regression coverage.
- [ ] Integration verifies updated-client state/credential migration preserves pairings, keys, grants, revision/attempt journals and saved choices without inferring combat or automatic consent; no downgrade matrix or runtime old reader/writer. These are transport/control gates, not model-owned changes.

## Remaining gates and exclusions

**Remaining shared-contract gate:** independent approval and implementation of the exact §4.1 profile/helpers/fixture paths above, plus re-review of transport origin mapping against the implemented local handoff. Names/carry/effects consume that foundation after it is available; no unresolved artifact/import naming remains. Core internal values/readers and row lifecycle have already been approved and integrated. Exact wire ages/rounding, DB clock/failover behavior, pre-session correlation, consent DTOs and reviewed forward migration/cutover remain their owners' authority—not local model definitions. Bound-dependent steps wait for their contract gate; independent local preparation need not wait for unrelated API-detail review.

**Decided, not a blocker:** updated automatic Off/Stop follows the authoritative consent-generation semantics; no old-Stop compatibility question remains. Automatic approval stays independent of combat permission; retain distinct `sourceGeneration` and `consentGeneration` fences. Those server fences are not interchangeable with local accepted-observation IDs. No automatic-consent work, transport clocks, wire/schema implementation, UI filtering, controller edits or runtime/source-policy redesign belongs in this lane.

**Evidence boundary:** completed-core verification is cited above. Remaining-task commands are planned, not passing feature evidence. This update records completed work and accepted review remediation; it adds no further implementation, migration, live call or deployment.
