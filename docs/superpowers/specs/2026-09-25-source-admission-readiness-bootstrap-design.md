# Fleet source-admission readiness bootstrap — design

## Status

Approved design. Implementation is test-only and requires a separate reviewed
plan. This document authorizes no production, workflow, dependency,
configuration, marker, selector, budget, or shard change.

The change is limited to replacing unconditional fixture warm-up in
`tests/test_fleetsharing_source_admission.py` with bounded semantic readiness,
adding competing-deadline preconditions to two existing permission refusals, and
strengthening the two existing retry parameter identities. All 120 existing
testcase identities, their order, parameters, markers, and test function
signatures remain unchanged.

## Purpose

`publication_rig()` currently calls `drive(worker, mono, 12)` for every one of
its 119 constructions. Most rigs establish the metadata required by their test
several scheduler turns earlier, but continue through unrelated periodic work,
real durable saves, and state reloads before returning.

The approved correction is not a faster fake worker and not pre-seeded state. It
keeps the real worker, scheduler, signed client, JSON journal, filesystem
publication, and timing/source authorities, but stops fixture bootstrap as soon
as an explicit readiness predicate is true. Six phase-sensitive cases opt into
the original exact 12-turn warm-up.

This design makes a structural work claim only until hosted evidence exists:

- worker bootstrap turns change from `1428` to `682` (`−746`);
- real bootstrap `s.save()` calls, including 119 fixture seed writes, change
  from `1469` to `921` (`−548`);
- worker `_save_state` delegations within bootstrap change from `1350` to `802`
  (`−548`);
- whole-file real `s.save()` calls change from `1928` to `1409` (`−519`);
- 119 additional real `s.load(path)` equality checks are introduced;
- the file remains 120 cases built from 119 `publication_rig()` constructions.

No historical 49-second observation and no current wall-clock result is a
claimed speedup. Timing remains an observation to report after implementation.

## Authority and baseline

The source baseline is merged `main` commit
`f6e8ecd5b09889e79aa169ce103b2eb9681cec9f` (`Use native Windows memory
evidence for Fleet resource probe (#289)`). Relevant authorities are:

- `AGENTS.md`;
- `docs/ci-test-budget-redesign.md`;
- `docs/ci-test-budget-fleet-tranche-results.md`;
- `tests/test_fleetsharing_source_admission.py`;
- its unchanged importers `tests/test_fleetsharing_remote_worker.py` and
  `tests/test_fleetsharing_worker_fix1.py`;
- `tests/test_fleetsharing_worker.py` and
  `tests/fleetsharing_timing_helpers.py` for the existing worker/source doubles;
- `wingman/fleetsharing/{worker,state,scheduling,timing,client,crypto}.py`.

`PRODUCT.md` and `DESIGN.md` do not govern this change because it changes no
product behavior or rendered interface.

### Current hosted reference

The current hosted reference is PR #289 run `36147950569`, attempt 2:

| Platform | Source-admission cases | JUnit testcase sum |
|---|---:|---:|
| Windows | 120 | 14.150s |
| Ubuntu | 120 | 2.835s |

These are one current hosted observation per platform. They motivate inspecting
repeated fixture work but do not establish an implementation speedup target.
The current complete collection is exactly 16,609 outcomes.

## Existing bootstrap and why it is excessive

Each `publication_rig()` construction currently:

1. writes `PAIRED_STATE` to a real temporary JSON path with `s.save()`;
2. constructs the real test worker and signed publication client;
3. points `_load_state` and `_save_state` at real `s.load()` / `s.save()` calls;
4. applies any case-specific `configure(worker, client, mono)` callback;
5. executes exactly 12 scheduler turns;
6. asserts only that catalogue, eligibility, and a timing anchor exist.

The fixed count makes ordinary rigs continue after their required metadata is
ready. It is also semantically weak: three final assertions do not establish
that the eligibility proof belongs to the exact accepted eligibility object and
current fence, and watch-enabled rigs do not explicitly require their source and
automatic observations.

The investigation classified the first readiness point for all 119 rigs. Save
counts here are real `s.save()` calls and include each rig's one seed write; the
parenthesized number is the worker `_save_state` delegation count:

| Category | Rigs | Readiness turn | Real saves at readiness |
|---|---:|---:|---:|
| Ordinary | 105 | 5 | 7 (6 delegated) |
| Capability ACK | 4 | 6 | 9 (8 delegated) |
| Source watch | 9 | 9 | 12 (11 delegated) |
| Near-expiry session | 1 | 10 | 12 (11 delegated) |

If every rig stopped at those points, bootstrap would consume 640 turns, 891
real saves, and 772 worker save delegations. Six ordinary rigs deliberately
retain the original phase and continue from turn 5/save 7 to turn 12/save 12,
adding five real and five delegated saves each. That produces the approved
candidate counts of 682 turns, 921 real bootstrap saves, and 802 worker save
delegations.

## Design

### 1. Keep `publication_rig()` as the only fixture entry point

Preserve the existing helper name, return shape, positional argument, callback
ordering, and rights override behavior. Add one keyword-only option:

```python
def publication_rig(
    tmp_path,
    *,
    configure=None,
    original_phase=False,
    **rights,
):
    ...
```

`original_phase` is a strict test-owned boolean. `False` is the default semantic
readiness bootstrap. `True` means exactly the existing `drive(worker, mono, 12)`
behavior, with no early readiness stop.

The name describes why a caller opts out: the case depends on the original
scheduler phase, not merely on “slow” or “legacy” behavior. Do not infer this
mode from a pytest node ID, function name, call stack, request object, source
inspection, global registry, or caller module. Each phase-sensitive call site
passes the option explicitly from its semantic case data.

Do not change the function signatures, decorators, parameter values, IDs, or
markers of the 120 tests. In particular, the parameterized independent-deadline
test chooses the option from its existing `boundary == "proof"` value inside
the unchanged test body; it does not split, rename, or reparameterize the test.

### 2. Add one bounded bootstrap helper

Add a private helper in the same test module named
`_drive_publication_bootstrap`. Its conceptual interface is:

```python
def _drive_publication_bootstrap(
    worker,
    client,
    mono,
    path,
    *,
    original_phase,
):
    ...
```

`publication_rig()` remains responsible for constructing state, client, worker,
and overrides and for running `configure` first. It then delegates warm-up to
this helper. The helper observes whether source watch was requested from the
configured worker; no second caller-supplied watch flag may drift from the
actual configured state.

Behavior is exact:

- when `original_phase=True`, call `drive(worker, mono, 12)` once and then apply
  the common post-bootstrap assertions;
- otherwise, drive exactly one real scheduler turn at a time;
- after each turn, evaluate the explicit metadata-readiness predicate below;
- return on the first ready turn;
- permit at most the current 12 turns;
- if readiness is still false after turn 12, fail immediately with the bounded
  diagnostic below.

The helper must not inspect `worker._work()`, call the scheduler's planning
methods directly, predict which operation is next, or treat the absence of due
work as readiness. `_work()` is production planning, not the accepted metadata
state; inspecting it would couple the fixture to operation ordering and could
perform planning work merely to decide whether setup is complete.

### 3. Define readiness from accepted metadata authority

The default helper is ready only when all applicable conditions are true:

1. `worker._catalogue is not None`;
2. `worker._eligibility is not None`;
3. `worker._timing_context._state.anchor is not None`;
4. `worker._eligibility_proof is not None`;
5. the proof's `response` is the exact current eligibility object by identity,
   not merely an equal value;
6. the proof's captured fence is the exact current worker fence field-for-field,
   including the timing generation that `_Fence` deliberately excludes from
   ordinary dataclass equality;
7. if the configured worker requested source watch, accepted source observation
   exists and the current status exposes it, and accepted automatic status
   exists and the current status exposes it.

The exact-object and exact-fence requirements prevent a stale proof from making
an equal replacement eligibility payload appear current. The watch conditions
prevent catalogue/eligibility readiness from returning before the work that a
watch-enabled caller explicitly requested.

The named existence checks remain explicit for diagnostics even when a later
identity check logically implies them. In particular, exact proof-response
identity implies both proof and eligibility existence, and exact fence matching
implies proof existence. Watched presence checks are not dropped because a bare
identity expression could otherwise accept `None is None`. These redundancies
are intentional diagnostic structure, not a claim that deleting every named
check must change behavior on a valid production flow.

Implement the fence comparison in a small local expression or helper that names
all `_Fence` fields. Do not rely on `_Fence.__eq__`, because its `timing` field is
`compare=False`. Do not compare string representations.

For watch-enabled rigs, the intended observations are the accepted worker and
status objects, not merely evidence that a network method was called:

- `worker._sources` exists and `worker.status().sources` is that accepted
  observation;
- `worker._automatic_observation` exists and
  `worker.status().automatic_status` is that accepted observation.

No publication source is submitted during fixture bootstrap. Readiness does not
require a selectable publication and must not call `_publication()` as a proxy.

### 4. Fail boundedly and diagnostically

A readiness miss after 12 turns is a fixture failure, not permission to continue
until green. The `pytest.fail()` message must include enough detached diagnostic
state to identify the missing authority without another instrumented run:

- turns completed and the 12-turn bound;
- a named true/false result for catalogue, eligibility, anchor, proof,
  exact-response identity, and exact-current-fence checks;
- whether source watch was requested;
- source observation and status-source presence/identity;
- automatic observation and status-automatic presence/identity;
- the proof fence and current fence, including a named list of differing fields;
- `worker.status()`;
- the fake client's ordered operation names or equivalent bounded call summary.

Do not include private-key bytes, signed authorization values, complete request
bodies, or other secret-like material in the diagnostic. The test client uses
synthetic credentials, but keeping diagnostics authority-focused avoids
normalizing unsafe logging practices.

Do not add sleeps, retries beyond the 12 real turns, or a fallback fixed drive.
A timeout or later test assertion is not an acceptable substitute for the
bootstrap diagnostic.

### 5. Assert common post-bootstrap invariants

After either readiness mode stops—semantic readiness or exact original phase—run
one common invariant block before returning the rig. “Post-bootstrap stop” here
means the point where the bounded warm-up loop stops; it does not mean
`worker.stop()` or thread shutdown.

The common block must establish:

- `s.load(path) == worker._state`, using a fresh real file load;
- device bootstrap is complete (`worker._needs_device is False`);
- no publication has been accepted during setup (`client.puts == []` and
  `worker._last_published == ()`);
- the publisher timing context has no evidence associations
  (`worker._timing_context._publisher.associations == {}`);
- `worker._timing_context._next_stage_at is None`.

The fresh equality load accounts for the approved 119 additional real loads.
It is deliberately not replaced by a cached candidate or a captured save
argument. These invariants prove that earlier return did not leave a durable
write pending, accidentally admit a publication, or allocate process-local
publication pins before a test submits its source.

### 6. Preserve original phase for exactly six cases

Exactly these six existing pytest cases pass `original_phase=True`:

| Existing case | Count | Reason |
|---|---:|---|
| `test_original_source_reaches_real_signed_combat_put` | 3 parameter cases | Preserve the original scheduler phase and exact real signed wire timestamps for all three nullable DPS combinations. |
| `test_new_mailbox_does_not_replace_selected_current_ticket` | 1 | Preserve the original selected-ticket phase and its exact wire timestamp while a newer mailbox item arrives. |
| `test_cached_permission_deadline_expires_after_signing_without_utc_renewal` | 1 | Preserve the original cached-proof phase used to move monotonic time after signing while UTC is rolled back. |
| `test_independent_deadlines_are_checked_after_real_leaf_wait[proof-False]` | 1 | Preserve the original proof-deadline phase for the held real source leaf. |

The first four cases must retain their current exact wire timestamp assertions,
including `sampled_at_ms == 1788782405800`. The option is not broadened to the
whole parameterized deadline family: anchor, row, effect, and session rows use
the default readiness bootstrap.

No seventh case may opt in merely because its current timing changes. If another
case requires original phase to stay green, stop and investigate whether the
readiness predicate is incomplete or the test owns an undocumented phase
contract.

### 7. Make the two permission-deadline refusals independently admissible

The cached-permission and held-leaf proof-deadline cases currently refuse at the
intended permission boundary, but a competing sample, session, anchor, row, or
effect deadline could mask a removed proof check.

Before triggering each refusal, add explicit preconditions proving that every
competing deadline remains admissible at the target time:

- the original snapshot sample is still younger than the maximum sample age;
- session authority remains strictly later than the target;
- timing-anchor authority remains admissible at the target;
- every selected row and effect deadline remains strictly later than the target;
- the permission proof deadline is the boundary being crossed.

For the held-leaf `proof-False` row, assert these conditions before starting the
barrier thread and again at the held transition where practical without
re-entering production leaves. For the cached-permission/UTC-rollback case,
assert them before signing mutates monotonic time. The eventual `_Obsolete` must
therefore be owned independently by the permission guard.

Do not change the target timestamps, move the refusal to a different phase, or
weaken the exact UTC-rollback premise.

### 8. Strengthen the two existing retry identities

Strengthen only the existing parameterized identities
`test_original_measurement_retry_retains_wire_origins_across_reauthentication[thread]`
and
`test_original_measurement_retry_retains_wire_origins_across_reauthentication[session]`.
Do not rename the test, change its signature, alter the `restart` parameter
values or IDs, or add a witness test.

Give the submitted source one representative named `EffectObservation` in
addition to its existing sample and row evidence. Before retry, derive the exact
sample, row, and effect association keys from that immutable source. The expected
shapes are the sample `(activation_generation, sampled_at_mono)` key, the row
`(character_id, lifetime, "row", observation_id)` key, and the effect
`(character_id, lifetime, (kind, name), observation_id)` key; use the exact
`Fraction`/accepted ID values carried by the source rather than reconstructed
rounded values. Then assert:

- the publisher association key set is exactly those three keys;
- association cardinality is exactly three;
- the captured sample, row, and effect pins are the exact objects stored under
  their corresponding keys.

After the retry completes—both across worker-thread restart and session
reauthentication—assert the same exact key set and cardinality and assert, key by
key, that every retained association is the identical captured pin object. The
existing exact repeated wire body, retained timing-context identity, cadence
floor, latest-source, and session-change assertions remain.

Qualify this strength with a temporary production mutation that drops only the
effect pin during recovery while leaving sample and row pins intact. Both
existing parameter identities must fail at the exact retained key-set,
cardinality, or effect-pin identity assertion; a changed body, generic retry
failure, or timeout is not the intended failure.

## Preserved lifecycle and test strength

The optimization changes only how long the test fixture waits for accepted
metadata. It preserves all of these real seams:

- `s.save()` / `s.load()` JSON validation and real file publication;
- flush/fsync/replace behavior reached by the state store;
- the signed transport's file revision check before request acceptance;
- durable revision advancement before the real client call;
- scheduler deadlines, retry state, due work, and operation choice;
- timing anchor, source, eligibility, and participation authority;
- process-local timing pins and their exact object identity;
- real threads, events, locks, barriers, recovery, and lock ordering;
- original snapshot, row, effect, session, anchor, and permission origins;
- retry across worker-thread and session reauthentication;
- source uncertainty withdrawal protection;
- exact signed request and wire-body assertions.

There is no cached prepared worker, in-memory state store, direct assignment of
catalogue/eligibility/timing/source metadata, private production seeding,
precomputed signed body, fixture-wide fsync suppression, or mocked scheduler.
Reading private worker fields to define readiness is permitted because this is
already a private integration fixture and the fields are the accepted
production authorities being tested. Writing those fields to skip work is not.

## Structural evidence and claim discipline

The investigation's current-to-candidate inventory is authoritative for the
implementation plan:

| Structural measure | Current | Candidate | Change |
|---|---:|---:|---:|
| Bootstrap turns | 1,428 | 682 | −746 |
| Real bootstrap `s.save()` calls, including 119 seeds | 1,469 | 921 | −548 |
| Bootstrap worker `_save_state` delegations | 1,350 | 802 | −548 |
| Whole-file real `s.save()` calls | 1,928 | 1,409 | −519 |
| Fresh post-bootstrap equality loads | 0 | 119 | +119 |
| `publication_rig()` constructions | 119 | 119 | 0 |
| Source-admission pytest cases | 120 | 120 | 0 |

The readiness-category ledger remains `105 @ 5 turns/7 real saves`,
`4 @ 6/9`, `9 @ 9/12`, and `1 @ 10/12`; each real-save figure includes one seed.
The corresponding worker-delegation ledger is `105 @ 6`, `4 @ 8`, `9 @ 11`,
and `1 @ 11`. The six original-phase cases are six of the 105 ordinary-readiness
rigs; continuing each from readiness at turn 5/save 7 to the original turn
12/save 12 accounts for the candidate totals of 682 turns, 921 real bootstrap
saves, and 802 delegated worker saves.

Implementation must reproduce these numbers with temporary delegated
instrumentation, then remove that instrumentation. The counts are structural
work evidence, not an elapsed-time assertion. Until a successful hosted run is
published, the only accepted claim is that the implementation removes the
listed turns and saves while preserving the contracts below.

## Compatibility and identity contract

### Source-admission file

Preserve exactly:

- 120 collected node IDs;
- existing collection order;
- every parameter value and generated parameter ID;
- every marker and decorator;
- every test function name and signature;
- every exact wire body and timestamp assertion;
- complete collection membership of 16,609 outcomes.

No witness test is added. Qualification is performed through temporary
instrumentation, guard mutations, and invalid-authority fault probes against the
existing 120 identities. Assertion-strength expansion outside the bootstrap
helper and its six existing phase-sensitive call sites is limited to the two
existing permission-refusal identities and the two existing thread/session retry
parameter identities described above.

### Unchanged external callers

`tests/test_fleetsharing_remote_worker.py` and
`tests/test_fleetsharing_worker_fix1.py` import `publication_rig()` and remain
byte-for-byte unchanged. Their default calls receive semantic readiness through
the backward-compatible default option.

Verify the three-file selection in ordinary collection order, reverse file
order, reverse node order, and a recorded deterministic shuffled order. It must
remain exactly 167 cases in every ordering. This proves that early bootstrap does
not leak a process-local timing/source pin or depend on a prior caller having
advanced shared state.

The helper remains importable under its existing name. Adding the keyword-only
option must not require any caller update outside
`tests/test_fleetsharing_source_admission.py`.

## Qualification matrix: guard mutations and fault probes

All qualification edits are temporary and uncommitted. Restore each source edit
and each injected runtime authority exactly before the next probe, record the
permanent test identity and intended assertion, and verify the final diff
contains no mutation support, fault hook, or altered production source.

A guard mutation removes or weakens a check and asks whether an existing valid
flow exposes the loss. A fault probe keeps the check and injects an invalid
state at the observation boundary. They are different evidence and must not be
reported interchangeably. Exact-object, exact-fence, and durable-equality guard
deletions can be equivalent under all valid flows in this file; their strength
is qualified by the explicit fault probes below, not by claiming an artificial
mutation kill. Likewise, the deliberately redundant existence labels described
in the readiness section need not each have an independent kill.

A kill or fault detection qualifies only when the intended boundary assertion
or bounded diagnostic fails. Another expiry, a later generic `_Obsolete`, an
unrelated barrier wait, collection failure, or thread timeout does not qualify.
No `_work()` inspection may be added to force a result.

### Bootstrap predicate and postconditions

Use this matrix:

| Boundary | Qualification type | Intended evidence |
|---|---|---|
| Catalogue, anchor, watched source, watched automatic, device completion, zero publication, empty publisher associations, and no next-stage floor | Independent guard mutations where the existing flow is discriminating | Named readiness diagnostic or common postcondition fails; document any check proved redundant instead of forcing a kill. |
| Eligibility/proof existence | Review plus any naturally discriminating guard mutation | Preserve their named diagnostic booleans even where exact response/fence checks imply existence; no every-check kill claim. |
| Exact proof-response identity | Per-turn invalid-authority fault probe | After every real turn for which a proof exists, temporarily install a proof whose response is equal to but not identical with current eligibility immediately before readiness evaluation. Readiness stays false through the bound and the diagnostic names exact-response identity false. |
| Exact full current fence | Per-turn invalid-authority fault probe | After every real turn for which a proof exists, temporarily install a proof carrying a known stale complete `_Fence`; compare and report every field, including a stale timing generation. Readiness stays false through the bound and the diagnostic names the differing fields. |
| Fresh durable equality | Postcondition invalid-authority fault probe | After readiness stops but before the common invariant, temporarily place a valid state on disk that is unequal to `worker._state`. The fresh real `s.load(path) == worker._state` assertion fails. |
| First-ready thresholds | One-turn-short bound mutation per category | Ordinary, ACK, watch, and near-expiry representatives fail at bounds `4/5/8/9`, establishing first readiness at `5/6/9/10`. |

For each per-turn authority probe, capture the exact proof and related authority,
inject only for the predicate evaluation and final diagnostic, and restore in a
`finally` path before another scheduler turn or probe. The equal replacement
must be a distinct object, not an inequality payload. The stale fence must be a
complete fence from an earlier generation and must be stale in timing as well as
any other changed fields; a synthetic string or partial tuple is not accepted.
For the durable mismatch, preserve the original file bytes/state and restore
them exactly after the expected assertion. Fault-probe saves and restorations
are diagnostic-only and excluded from structural counts.

### Retained publication authority

Temporary production mutations must continue to be detected at the intended
assertions for:

- final source admission before real transport;
- original-source completion installation;
- original-source post-save 401 reset;
- each of the three held combat rights:
  `approved_capabilities`, `session_approved_capabilities`, and
  `acknowledged_capabilities`;
- proof-deadline refusal while every competing deadline is explicitly
  admissible;
- durable save-before-transport revision ordering;
- anchor, sample, session, row, and effect deadline checks;
- uncertain-member prevention of destructive whole-fleet withdrawal;
- retry preservation of original anchor/sample/session/row/effect origins
  across thread and session reauthentication;
- effect-pin retention specifically, by dropping only the effect association in
  recovery and requiring both existing thread/session retry identities to fail
  at their exact three-key/cardinality/identity assertions.

The exact retained tests may be grouped in the future plan, but each mutation
record must name the permanent existing identity and the assertion that went
red. Mutating multiple guards at once to force a failure is not acceptable. The
effect-pin-drop probe is one isolated mutation and may not also drop sample or
row associations.

## Verification

### Local prerequisites

Use Node on `PATH` and the built release settings codec installed in
`packaging/bin`, as required by `AGENTS.md`. No Node, codec, or unexpected native
availability skip is acceptable complete-suite evidence.

### Focused verification

The future implementation must run and record:

1. the exact 120-case source-admission file in normal order;
2. the exact six original-phase cases, proving all use 12 turns and the first
   four retain exact wire timestamps;
3. representative ordinary, ACK, watch, and near-expiry rigs, proving first
   readiness at turns `5`, `6`, `9`, and `10`, real save totals `7`, `9`, `12`,
   and `12` including one seed each, and delegated worker saves `6`, `8`, `11`,
   and `11`;
4. the cached-permission and held-leaf proof cases with competing-deadline
   preconditions;
5. both existing thread/session retry identities with exact sample/row/effect
   pin keys, cardinality, and retained object identity;
6. the 167-case selection consisting of source admission plus the unchanged
   remote-worker and worker-fix1 callers;
7. the same 167 identities in normal, reverse-file, reverse-node, and recorded
   deterministic shuffled orders;
8. relevant Fleet worker, state, timing, client, scheduling, crypto, and remote
   publication tests;
9. the complete `tests/` suite with exact 16,609 outcomes and skip inspection;
10. executable JavaScript smoke, settings-codec Cargo test, Ruff check, Ruff
    format check, `git diff --check`, and changed-path/protected-path audits.

Order runs must use the same identities; no order-specific skip, retry-to-green,
or process restart is accepted.

### Structural instrumentation

Temporary delegated instrumentation must count without replacing real work:

- each call that advances one scheduler turn;
- every real `s.save()` call in the file, including the 119 fixture seed writes,
  classified as bootstrap or later test work;
- each worker `_save_state` delegation during bootstrap, counted separately from
  seed writes;
- each fresh post-bootstrap `s.load(path)` equality check;
- readiness category and first-ready turn/real-save/delegated-save count per rig;
- exact original-phase opt-ins.

It must reproduce `1428 → 682` turns, `1469 → 921` real bootstrap saves,
`1350 → 802` bootstrap worker delegations, `1928 → 1409` whole-file real saves,
and `+119` loads. Instrument `s.save()` itself and delegate to the real function;
wrapping only `_save_state` is insufficient because it misses the 119 seed
writes and cannot substantiate real-save totals. Instrumentation delegates to
real saves and loads and is removed before commit. A count obtained by replacing
the file store, suppressing fsync, or reading only fake-client call logs is not
accepted.

### Hosted verification

A future results document must compare a successful hosted run with PR #289 run
`36147950569`, attempt 2, and record:

- branch head, synthetic merge, base, workflow run/attempt, jobs, and artifacts;
- exact Windows and Ubuntu 120-case source-admission identity equality;
- exact complete 16,609-outcome identity equality;
- pass/failure/error counts and normalized platform skip comparisons;
- source-admission testcase sums and slowest identities;
- job and pytest-step elapsed times as observations only;
- proof that callers, production, workflows, dependencies, configuration,
  markers, selectors, budgets, and shards did not change.

The structural work claim remains valid if hosted timing is noisy. A single
favorable hosted result must not be described as a speedup, and no historical
49-second/current timing claim may be introduced.

## Data lifecycle, failure behavior, security, compatibility, and observability

### Data lifecycle

Every rig continues to create its own `tmp_path / "sharing.json"`, write
`PAIRED_STATE`, load it through the worker, save every accepted durable
transition, and reload it inside the signed transport revision check. The new
post-bootstrap equality check performs one additional fresh load per rig. No
state survives the test's temporary directory, and no state object is shared
between rigs.

### Failure behavior

Readiness is fail-closed and bounded. Missing or stale metadata reports the
component and current authority after at most 12 turns. It does not silently
continue, seed the missing component, accept an equal stale proof, or retry the
whole test. Existing thread and barrier timeouts remain safety bounds, not
readiness mechanisms.

### Security

Production authentication, capability disclosure, signing, revision ordering,
and source admission are unchanged. The helper observes synthetic test authority
only and logs no private key or complete signed request. Exact capability and
permission fences remain covered by the retained mutations.

### Compatibility

The default remains callable by both existing importers. `configure` still runs
before any scheduler turn, rights overrides retain their current precedence,
and the returned `(worker, client, mono)` tuple is unchanged. The keyword-only
option cannot alter positional callers. Pytest identity, marker, parameter, and
signature stability protects external selectors and historical evidence.

### Observability

The bounded diagnostic and temporary structural counters make fixture failure
attributable to the missing authority rather than to a later publication test.
Permanent runtime metrics, logging, JUnit properties, workflow summaries, and
budget files are out of scope.

## Alternatives rejected

### Fixed five-turn bootstrap

Rejected. Five turns cover the 105 ordinary rigs only. Capability-ACK rigs need
six turns, source-watch rigs need nine, and the near-expiry session rig needs
ten. A fixed five would either fail valid cases or require hidden per-case
exceptions without proving accepted readiness.

### Cached or pre-seeded worker state

Rejected. Copying a prepared state, directly assigning catalogue/eligibility,
installing a timing anchor, using an in-memory store, or caching a worker would
bypass the scheduler, durable JSON saves/loads/fsync, signed revision check,
source/automatic observation, and process-local authority that this integration
file exists to verify. It also risks order dependence between tests.

### Inspecting `_work()` for readiness

Rejected. A planned work list is not accepted metadata authority. It couples the
fixture to scheduling internals, can miss stale proof/object relationships, and
would make readiness depend on what the worker might do next rather than what it
has durably accepted.

### Making every case semantic-readiness only

Rejected. Six cases intentionally preserve original phase: four own exact wire
timestamps and two are qualified permission-deadline guards. An explicit option
is clearer and safer than altering their expected timestamps or weakening their
mutation boundaries.

### Selecting original phase by node ID or call stack

Rejected. Pytest IDs, frames, and caller names are incidental strings. They are
fragile under refactoring, invisible at ordinary call sites, and can silently
change behavior when a test is imported or invoked directly. The explicit
keyword documents the semantic dependency.

## Risks and mitigations

### Equal fences can hide timing-generation drift

`_Fence.timing` is excluded from dataclass equality. A plain `proof.fence ==
worker._fence()` would therefore accept a stale timing generation. Compare every
field explicitly and qualify the timing-component mutant.

### Early return can leave durable state behind RAM

A worker can update process state around a save boundary. The fresh
`s.load(path) == worker._state` check is mandatory after the loop stops and is
performed in both modes. Do not compare only the last saved argument.

### Watch setup can return before requested observations

Catalogue, eligibility, and anchor readiness occur before source/automatic watch
metadata. Gate watch-enabled rigs on the accepted source and automatic objects
and their current status projections, which accounts for their nine-turn class.

### Readiness can allocate publication timing state accidentally

Calling `_publication()`, `_work()`, or staging work to test readiness could
create or expose pins. The helper reads accepted metadata only, then asserts no
publisher associations and no next-stage floor before any source is submitted.

### Earlier phase can change exact wire time

Four tests assert exact wire timestamps. Their explicit original-phase option
retains exact 12-turn warm-up. Any timestamp change in those cases is a stop, not
a reason to update expected JSON.

### A different deadline can mask proof refusal

Add explicit competing-deadline admissibility preconditions to the cached-proof
and held-leaf proof cases. Mutation qualification must fail at the proof
assertion, never through sample/session/anchor/row/effect expiry.

### Structural instrumentation can become a fake store

Counters wrap and delegate to the real save/load/drive seams. They may observe
but not suppress filesystem work, fsync, scheduling, or transport. Remove them
before commit.

## Stopping rules

Stop implementation and return to design review if any of these occurs:

1. semantic readiness cannot be expressed from accepted test-visible metadata
   without a production change;
2. any default rig needs more than the current 12-turn bound;
3. any seventh case appears to require `original_phase=True`;
4. any of the six approved original-phase cases cannot retain exact 12-turn
   behavior, or any of the first four changes its exact wire timestamp/body;
5. the readiness predicate requires `_work()`, scheduler-choice inspection,
   direct `_publication()` calls, sleeps, retries, or a call-stack/node-ID switch;
6. durable equality, device completion, zero publication, empty associations, or
   `_next_stage_at is None` fails when the bootstrap loop stops;
7. source-watch readiness cannot establish both source and automatic accepted
   observations and their current status identities;
8. the structural inventory does not reproduce `682` turns, `921` real
   bootstrap saves including 119 seeds, `802` bootstrap worker delegations,
   `1409` whole-file real saves, `119` equality loads, and the `105/4/9/1`
   readiness categories;
9. any of the 120 source-admission IDs, their order, parameters, markers, or
   signatures changes;
10. the unchanged caller selection is not exactly 167 cases or becomes
    order-dependent under normal, reverse, or deterministic shuffled runs;
11. complete collection is not exactly 16,609 outcomes, or Windows and Ubuntu
    identities diverge;
12. an intended guard mutation or fault probe can be detected only by another
    expiry, a generic later refusal, barrier timeout, or thread timeout, or an
    equivalent valid-flow guard deletion is misreported as a required kill;
13. a mutation of final source admission, original-source completion, post-save
    401, any held right, proof deadline, save-before-transport, independent
    deadline, uncertainty withdrawal, retry origins, or isolated effect-pin
    retention survives its permanent retained identity;
14. preserving coverage requires cached prepared state, an in-memory store,
    private metadata seeding, fixture sharing, or suppression of real
    save/load/fsync/signing work;
15. any production, workflow, dependency, configuration, packaging, marker,
    selector, budget, shard, or unrelated test change appears necessary;
16. local or hosted Node/settings-codec availability skips appear;
17. temporary instrumentation or mutation code cannot be restored to an empty
    protected-path diff;
18. evidence supports only an elapsed-time assertion and cannot reproduce the
    approved structural counts.

## Exact committed scope

The complete future tranche may commit only:

- `docs/superpowers/specs/2026-09-25-source-admission-readiness-bootstrap-design.md`;
- a future implementation plan under `docs/superpowers/plans/`;
- a future results document under `docs/`;
- `tests/test_fleetsharing_source_admission.py`.

Within the source-admission test, permanent edits are limited to
`publication_rig()` and its new bootstrap helper, the six explicit
`original_phase` selections, competing-deadline preconditions in the two
existing permission-refusal identities, and sample/row/effect pin assertions in
the two existing retry identities. Temporary instrumentation, guard mutations,
fault injections, and production mutations are never committed.

`tests/test_fleetsharing_remote_worker.py` and
`tests/test_fleetsharing_worker_fix1.py` are mandatory unchanged verification
callers and must not be committed. No file under `wingman/` may change.

Explicitly forbidden without a new design review:

- production code;
- other test modules or shared test helpers;
- `.github/` workflows;
- dependencies, `pyproject.toml`, or `uv.lock`;
- pytest configuration, markers, selectors, budgets, or shard manifests;
- test deletion, addition, rename, reordering, signature change, or parameter
  reduction;
- persistent benchmark or mutation harnesses;
- generated evidence files;
- cached/session fixtures, in-memory state stores, or private state seeding.

## Required implementation self-review

Before publication, the future results document must record a final review
covering:

- **Scope:** only the approved spec, plan, results, and source-admission test are
  committed; external callers and all protected paths are unchanged.
- **Identity:** exact 120 IDs/order/parameters/markers/signatures, exact 167
  unchanged-caller selection, and exact 16,609 complete outcomes.
- **Interfaces:** `publication_rig()` retains its return/callback/rights behavior,
  adds only explicit keyword-only `original_phase=False`, and delegates to
  `_drive_publication_bootstrap`.
- **Predicate:** catalogue, eligibility, anchor, proof, exact eligibility object,
  every current-fence field including timing, and watch source/automatic status
  are all required without `_work()` inspection.
- **Post-bootstrap state:** real durable equality, device complete, zero accepted
  publication, empty publisher associations, and no next-stage floor.
- **Original phase:** exactly six cases opt in, all execute 12 turns, and the
  first four preserve exact wire timestamps and bodies.
- **Deadline independence:** cached-proof and held-leaf proof refusals establish
  every competing deadline as admissible.
- **Structural arithmetic:** `119 × 12 = 1428`; readiness thresholds total 640
  turns/891 real saves including 119 seeds and 772 worker delegations; six
  ordinary cases add 42 turns/30 saves and delegations; candidate totals are
  682/921/802; whole-file real saves are 1,409; equality loads are 119.
- **Lifecycle strength:** real file save/load/fsync, revision-before-client,
  scheduler deadlines/due work, authorities, pins, threads/barriers/recovery,
  and original origins remain exercised; both retry identities retain the exact
  sample/row/effect pin objects under the exact three keys.
- **Qualification quality:** guard mutations and invalid-authority fault probes
  are reported separately; each discriminating probe fails at its intended
  assertion, equivalent/redundant deletions are documented rather than forced,
  no timeout or competing refusal is counted, and all edits/authorities are
  restored.
- **Order independence:** normal, reverse-file, reverse-node, and deterministic
  shuffled 167-case runs are green without retries.
- **Claim discipline:** hosted timings are reported as observations only; no
  historical 49-second or current speedup claim is made.
- **Leftovers:** no placeholder, debug output, cached fixture, generated
  evidence, temporary instrumentation, or mutation remains.

## Follow-up boundary

Successful implementation proves only that this one source-admission fixture can
stop after accepted metadata readiness while preserving six explicit
phase-sensitive cases and all existing durable publication contracts. It does
not authorize production scheduler changes, broader Fleet fixture caching,
test consolidation, workflow selection, budgets, or sharding.
