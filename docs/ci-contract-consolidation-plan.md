# CI contract consolidation — proposed first tranche

**Status: proposal for review; not authorization to edit or delete tests.**
Builds on [Phase 1 results](ci-test-strategy-phase-1-results.md) and the
[contract-consolidation rules](ci-test-strategy-design.md#case-consolidation-process).
Discovery source: `9a5380057b01a19bb68b540c69c7f5db560f9543`.
PR #196 is still open at drafting time. Keep this proposal separate from that PR;
implementation should start from its merged result, or an explicitly approved
stacked branch, with source identities and collected cases refreshed first.

## Intended outcome and scope

Remove avoidable fixture/harness work, then propose only demonstrably equivalent
case reductions. Preserve distinct user, trust-boundary, ownership, persistence,
platform and regression contracts. **There is no test-count reduction quota.**

This is a bounded first tranche over:
- `tests/test_ui_setup_controller.py` and its test-fixture seams;
- `tests/test_new_screenshots.py` / `tests/fixtures/screenshot_pages.cjs`;
- `tests/test_ui_setup_yaml.py` and independently authored input fixtures.

It does **not** promise the five-minute required-CI ceiling. The global ceiling
remains, but these files alone cannot credibly close the measured gap.

## Decisions requiring review — highest risk first

1. **No distinct contract may disappear.** Equal exceptions, shared production
   helpers, or similar parameter names do not establish equivalence. Compare
   entrypoint, normalized result/error, side effects, authority transition,
   platform/encoding semantics and incident ownership. Record every proposed
   removed node ID against retained coverage and a targeted mutation result.
2. **Keep the large create-boundary matrix initially.** Admission refusal is
   synchronous; worker/publication refusal consumes authorization and emits a
   correlated completion; publication also owns staging cleanup. These are not
   interchangeable phases. Slow-probe, final-hash and late-deletion races stay.
3. **Overhead work precedes deletion.** The first implementation slices retain
   every existing pytest ID. Minimal fixtures must still reach the intended
   validator, not merely fail earlier. No global fake filesystem, disabled
   `fsync`, shared mutable controller, or shared profile directory.
4. **Keep real input boundaries.** Preserve YAML and JSON reader distinctions,
   actual 100,000/100,001-node cases, 2 MiB/+1-byte UTF-8 cases, actual depth
   limits, preconstruction refusal, complete native fixtures and independent
   nested ownership. Do not lower production limits to make tests cheap.
5. **Reuse only test infrastructure.** Screenshot improvements stay in test
   doubles/fixtures and reuse `NodeScenarioWorker` if process reuse is justified.
   Production page modules and `scripts/shoot_screens.py` remain unchanged;
   do not replace their waits with no-ops or mock the behavior being verified.
6. **Keep full serial CI on both platforms.** Preserve `checks`,
   `test (ubuntu-latest)`, `test (windows-latest)`, mandatory Node/release codec,
   and release/build-owned full pytest plus Cargo. No markers or platform slicing.

## Evidence and budget

The Phase 1 serial sample has ten green attempts, Windows pytest median/p95
**496/575s**, and required-path median/p95 **561/642s**. These hotspot figures are
Windows JUnit case sums at that source, not independently measured file wall time:

| File | Cases | Median case sum | Maximum case sum (= sample p95) |
|---|---:|---:|---:|
| Setup controller | 250 | 52.668s | 83.873s |
| New screenshots | 55 | 32.792s | 35.334s |
| Setup YAML | 164 | 29.702s | 31.274s |

Compute the combined budget within each attempt, **not by adding file p95s**:
median **115.520s**, maximum **147.895s**. The two 642s required-path attempts
contain 143.992s and 147.895s in these files. Even the unrealistic accounting
exercise of making all their recorded case work free leaves about **498/494s**.
This is not a timing forecast: collection, shared fixtures and host contention
can change. It rules out promising that this tranche alone reaches 300s.

Important constraints established by source inspection:
- Controller setup already replaces **only `codec._run`** with a lossless fake
  (`tests/setup_fixtures.py:108–152`; controller test fixture:35–50). Most cases
  do not spawn the codec. JSON verification, hashing and real atomic filesystem
  work remain. Four native-transport parameter cases intentionally use the real
  transport (controller tests:963,1810). Do not mislabel all 250 cases native.
- Screenshots have **44 Node runtime cases and 11 Python-only cases**, not 55
  Node launches. `_run` rebuilds inputs and starts Node; cleanup-test sleeps are
  already patched. The DOM double repeatedly materializes descendant arrays
  (`screenshot_pages.cjs:54–85`); its runtime share is not yet measured.
- The YAML 100,000-node `[yaml]` case alone costs **12.142s median**, versus a much
  cheaper JSON counterpart. Real parsing and fixture serialization must be
  measured separately before attributing that cost to redundant tests.
- YAML enters through `setup_sharing.parse_text()`, with separate JSON/YAML
  readers converging at `overview_yaml.normalize()`. Native omission retains
  state; full Wingman omission clears it (`setup_documents.py:725–750`).
- New tests or source changes since the recorded revision invalidate hand-carried
  counts. Derive inventories from pytest collection; these numbers are snapshots.

## Initial contract inventory

These are review group IDs, **not pytest markers**. The named tests are anchors,
not a claim that one example covers every member. Expand each group to exact
collected IDs and outcome/effect records before proposing any deletion.
`C`, `S`, `Y` abbreviate the three test modules listed in Scope.

| Contract ID | Representative anchors | Must remain protected |
|---|---|---|
| SETUP-CATALOG-SAFE | C `test_catalog_reads_are_read_only_and_project_errors`; `test_catalog_diagnostics_are_safe_and_read_only`; `test_catalog_bridge_arguments_refuse_at_reader_boundary` | Read-only/error projection, valid offer preservation, invalid arguments before I/O, no private-path/text leakage |
| SETUP-LOCAL-PAIR | C `test_context_refuses_fallback_or_untrusted_bases`; `test_pairs_require_unambiguous_confirmed_links_and_real_local_files` | Trusted context, unique confirmed owner, real local regular single-link files; offline second owner remains ambiguous |
| SETUP-REVIEW-OFFER | C `test_review_binds_original_selection_and_distinct_sibling_without_effects`; `test_admitted_review_clears_offer_before_parse_and_success_gets_fresh_uuid`; `test_busy_requests_return_without_effects_or_clearing_offer` | Original selection versus browsed base, fresh authorization, busy request cannot clear it |
| SETUP-CREATE-AUTHORITY | C `test_create_revalidates_authority_and_complete_base`; `test_create_requires_positive_closed_at_every_boundary` | Independent admission/worker/publication checks, refusal class, offer consumption, correlated terminal result, unchanged live files |
| SETUP-LATE-AUTHORITY | C `test_create_does_not_trust_authority_from_before_slow_closed_probe`; `test_create_rechecks_authority_after_final_manifest_hashing`; `test_create_late_deletion_during_manifest_cannot_consume_or_restore_offer` | Slow work cannot renew stale authority; deletion/cancellation need not own the mutation lock |
| SETUP-WORKER-OWNERSHIP | C `test_create_start_failure_restores_only_still_valid_offer`; `test_create_inline_completion_cannot_restore_or_double_release`; `test_create_terminal_exits_release_mutation_without_replay` | Conditional restoration, inline completion ownership, exactly-once release/completion |
| SETUP-PUBLISH-PERSIST | C `test_create_codec_failure_never_publishes_partial_profile`; `test_create_publication_survives_housekeeping_failures`; `test_create_external_writer_during_staging_or_final_publish_is_not_overwritten` | New-only complete publication, external writer protection, publication success distinct from selection persistence |
| SETUP-REAL-TRANSPORT | C `test_native_transport_review_and_real_staging_on_distinct_synthetic_base`; `test_create_real_native_transport_profile_from_distinct_synthetic_pair` | Real codec path; full/native semantics; recipient preferences, labels and layout preserved as required |
| SETUP-FILE-BOUNDARY | C `test_file_read_refuses_legacy_encoding_or_oversize`; `test_file_read_bounds_io_before_decoding`; `test_file_save_validates_full_json_and_writes_atomically` | Bounded UTF-8 read, validation before dialog, failed-save preservation |
| NATIVE-SCHEMA | Y `test_duplicate_mapping_and_keyed_pairs_refuse_before_last_wins`; `test_native_shape_and_field_allowlists_are_not_generic_dat_passthrough`; `test_supplied_native_null_is_not_absence_or_full_reset`; `test_claimed_wingman_input_is_never_rescued_by_yaml` | No last-wins ambiguity, generic DAT passthrough, null-as-absence or malformed-envelope rescue |
| NATIVE-RESOURCE-OWNERSHIP | Y `test_forbidden_yaml_events_refuse_before_any_document_construction`; byte/depth/node boundary tests; `test_native_repeated_preset_groups_preserve_the_supplied_sequence`; `test_each_native_parse_owns_its_nested_values` | Preconstruction safety, actual limits, repeated memberships/order and independent nested values |
| SCREENSHOT-ISOLATION | S staging, fittings-detail, live-control, late-dialog/parser, terminal-operation and cleanup-failure groups | Real module execution; no live bridge/clipboard calls; settled named detail; state restoration; cleanup after every failure phase |

## Ordered implementation slices — after plan approval

### 1. Establish the executable inventory and attribute cost

- Collect exact node IDs, outcomes and skips for the three modules and relevant
  companion tests at the implementation baseline; map groups to the table above.
- Split pytest setup/call/teardown durations. Profile test-owned DOM traversal,
  repeated parsing/serialization, file seeding and process startup separately.
  Diagnostic instrumentation is temporary and must call through to real behavior.
- Record same-machine repeated before timings and commands. Keep normal runtime
  temp/cache locations: Phase 1 reproduced WSL anonymous-tempfile failure when
  `TMPDIR` was redirected onto `/mnt/c`; that is not a product/test regression.
- Deliver a compact per-group ledger: owner/incident, inputs, result/error, effect
  trace, authority boundary, format/platform, cost, and proposed action. No new
  generalized manifest framework or manually maintained case-count gate.

### 2. Remove screenshot harness overhead, without deleting cases

First assess a direct preorder traversal and short-circuit ID lookup in the test
DOM, rather than recursive construction of subtree arrays. Differential tests
must preserve selector semantics, document order, dynamic insertion/removal and
first-match duplicate-ID behavior. Do not cache mutable DOM query results.

Measure before choosing the next change. If startup/immutable-input work remains
material, precompute markup/expression inputs and migrate the 44 runtime cases to
existing `NodeScenarioWorker` conventions. Preserve every original pytest ID,
per-scenario timeout/diagnostics, fresh VM/DOM/handlers/bridge queues/timers, and
both existing in-scenario repetition passes. Keep all 11 Python-only cases.
Compare old/new outcomes temporarily, including forward/reverse/seeded order and
A→B→A, then retain bounded representative isolation checks rather than recurring
exhaustive duplicate work. No production screenshot-wait or verifier changes.

### 3. Remove YAML input-construction overhead, without deleting cases

- For malformed-field tests, use minimal independently authored positive inputs
  and change only the targeted field. Check the intended refusal, not merely
  `ValueError`; an earlier missing-dependency error must not mask the target.
- Reuse immutable fixture text or deep-copy decoded templates where measurement
  supports it. Never derive expected native input through the adapter under test;
  preserve complete-fixture, ordering, repetition and ownership tests.
- Profile large-boundary `safe_dump` separately from parser work. A deterministic
  test-owned text builder is eligible only if independently checked node/byte
  counts and intended syntax are unchanged. Keep acceptance and one-over refusal
  for both formats, including rejection before document construction.

### 4. Narrow only controller fixtures whose contracts do not need profile I/O

Start with the 12 catalog-diagnostic and four malformed-catalog-argument cases:
their reader is replaced or must refuse before lookup, so full source/recipient
DAT seeding may be irrelevant. Prove their read-only, safe-error and no-authority
side-effect assertions still execute. Keep the real-catalog authorized-offer case.
Do not globally change `seed_profile`, suppress atomic writes/hashes, share mutable
settings/controllers, or shortcut creation/publication fixtures. Expand to other
fixture callers only through a separately reviewed, measured proposal.

### 5. Propose small case reductions only where evidence earns them

No deletion is established as safe by discovery. Initial candidates for review:
- **Normalizer-only YAML/JSON crossings:** some nested keyed-pair/allowlist classes
  reach the same normalizer. Shared code alone is insufficient; retain reader-level
  root duplicates, malformed fallback, scalar typing, null, booleans, exponents
  and Unicode distinctions, plus cross-format wiring representatives.
- **Spawn/start × stale-offer crossings:** both pre-entry failures can reach the
  same restoration block. Retain both collaborator failure points with valid and
  stale offers, and inline-completion ownership, before considering any reduction.

The 60-case create-authority matrix, screenshot control endpoints/verifier clauses,
EVE palette mappings and defensive worker-manifest tests are **not default deletion
candidates**. A supposedly impossible state needs proof covering construction,
old persisted data, external input and concurrency—not an assertion of reachability.
Each deletion proposal gets its own reviewable before/after ID mapping and rationale.

## Proof required before a deletion

Run isolated, temporary production mutations; never commit weakened behavior.
First show the original suite detects the mutation, then show the proposed retained
suite detects the **same failure at the intended boundary**. Restore source and
verify clean behavior. If evidence is ambiguous, retain the cases.

| Proposed equivalence | Required mutation examples |
|---|---|
| Shared native normalizer | Admit an unknown field at each relevant nested `_record` site; remove keyed-pair duplicate rejection; treat supplied null as absent |
| Reader overlap | Independently restore last-wins JSON/YAML construction; permit claimed-envelope fallback; allow forbidden YAML alias/tag construction |
| Resource limits | Change `>` to `>=`; omit mapping-key nodes; move the check after construction; count characters instead of UTF-8 bytes |
| Authority/phase crossings | Omit one phase's check, ignore an unselected manifest file or one preference file, miss a final generation change or case-folded destination collision |
| Worker restoration | Restore unconditionally after spawn/start failure; restore after inline completion; release or complete twice |
| Screenshot equivalence/reuse | Remove one endpoint/continuation/verifier guard; accept an older operation ID; reuse mutable VM/input state or retain a timer across requests |

**Later refusal can mask a missing earlier guard.** Eventual failure and unchanged
files alone do not prove the admission/worker/publication boundary still owns its
check. Establish a boundary-specific oracle or retain the original case; do not
misreport a surviving mutation as proof of equivalence.

## Verification, rollout and stop points

- Each overhead slice: run its affected module(s), compare complete original node
  sets and outcomes, retain no Node/codec skips, and compare repeated uninstrumented
  before/after timings. A regression in isolation/diagnostics blocks the slice.
- Each approved reduction: report exact removed→retained mappings, killed mutations,
  preserved incidents and per-platform behavior. Do not combine unrelated groups
  merely to hit a desired count. Keep useful failure granularity.
- Check shared-fixture callers before changing helpers. Run native integration and
  controller suites when a seam could affect them; keep all actual native cases.
- Before tranche publication: locked dev sync, Node, release codec build/install,
  full `pytest tests/ -rs --durations=30 --junitxml=...`, JS smoke, Cargo,
  Ruff lint/format and whitespace checks, following repository prerequisites.
- Use per-slice focused measurements; **do not spend ten hosted runs per mechanical
  edit**. After a verified tranche, request authorization for one frozen ten-run
  hosted serial comparison against a comparable baseline. Preserve failures and
  skip inventories; use API elapsed critical path, not sums of file/case p95s.
- If gains are within noise or the needed proof is unavailable, keep the cases and
  reconsider that slice. If the ceiling still misses, return a newly ranked,
  bounded proposal; this plan does not authorize expansion to the rest of the suite.

## Alternatives, exclusions and approval boundary

Directly pruning the biggest matrices is rejected: they contain different authority
phases, parsers and side effects. Doing nothing preserves confidence but leaves
known avoidable harness work. A narrow overhead-first tranche, followed by explicit
contract proposals, offers reviewable progress without treating deletion as success.

Out of scope: shipped production changes (temporary mutation probes are verification
only); dependencies/frameworks; xdist adoption; fixing
or increasing the timeout of the fittings test that failed in Phase 1; coverage
percentage gates; markers/classification; Windows selection changes; release-gate
weakening; PR #196 changes; new hosted runs or implementation in this planning task.

**Approval requested:** the ordering and preservation rules above. Approval of this
plan may authorize overhead implementation, but individual case-deletion mappings
still require review. A fittings/xdist diagnosis is a separate work item.
