# Local fleet integration checkpoint — partial acceptance

## Scope and lineage

Branch: `integrate/fleet-v2-runtime`, linked worktree
`.worktrees/fleet-v2-integration`. Accepted transport base:
`9156263fe7ecf3e58d5f60103b558f4f9e664eb4`. Implemented source/test checkpoint:
`9135cb25186c3465911d92cde08653dc4b29597e`.

The normative runtime admission annex and plan are the versions at coordinator
`9b933da3be049e03e05ce0766ea0fdaa1c5a60b4`, not older lane-local copies.
This branch starts directly from the accepted transport lineage; no foundation,
model, fixture or metrics precision correction was replayed. The coordinator and
transport lane branches remain unchanged. Nothing was pushed, merged or deployed.

**Accepted here:** C1–C3, the safe I1 composition subset, and I2 offline real-client
proofs. **Not accepted:** complete control/UI composition or a green full runtime.
The full suite still has 17 failures in the deferred control/reservation area.

| Commit | Bounded change |
| --- | --- |
| `7716cfba243086bc44e0eb8b8e98ae9d2ef39ff0` | C1 immutable source tickets and bounded authority |
| `436203be26219a8fdd1139b71e18cf05966c0e23` | C2/C3 original producer provenance and dispatcher application |
| `45d611e884e5262d481d2d3e60930b3e367f2d53` | Actual startup reset-cut handshake and bounded custom-only ingress |
| `dc7965ef71cc5091e25f523c7ade8d925797fb3d` | Safe I1 clock/context, admitted subscription and remote adapters |
| `8fcc242e9d182530be6fbf6e922875893747c329` | Protocol-valid timestamp in privacy regression fixture |
| `da026ea2d95e174e36428ebdca41d66d931f2910` | Post-persistence settings projection without display restamping |
| `9135cb25186c3465911d92cde08653dc4b29597e` | I2 real producer → signed-client tests and honest fixture migrations |

## How the implemented path works

`wingman/telemetry/admission.py` owns three fixed provenance lanes. Concrete
producers capture original operation order before work and reserve invalidation
before mutating authoritative source state. Immutable sidecars accompany detached
callbacks; the serialized coordinator distinguishes successful model application
from receipt acknowledgement. Old stream evidence that actually reaches metrics
poisons publication. A demonstrably skipped stale full roster does not.

Tickets retain the exact computed snapshot and original authority token. Snapshot
computation is outside the leaf lock, between frontier capture and checked sealing.
The existing non-consuming `admit_start` port guards both real client start and
bounded completion effects; no current-token wrapping or payload restamping exists.

Poison recovery requires an existing legitimate reset and complete, associated
roster/source/control restatement. A reset-bound full restatement can supersede a
failed delta gap without falsely acknowledging the failed delta. Reset-completion
cuts include operations begun during reset; later contamination defeats recovery.

The existing dispatcher signals successful startup reset completion before
producer startup, without waiting for ticket readiness. The signal is tied to its
original activation and dispatcher lifetime. Reconcile remains the lifecycle owner;
there is no new executor. Failed resets do not certify sharing, timed-out owners
remain retained, and final source close is irreversible. Custom-only input retains
the original bounded mailbox rather than adding an unbounded empty-wrapper queue.

`wingman/__main__.py` retains one timing context and elapsed callable. Initial/lazy
telemetry, metrics, sharing and presentation use that domain. `wingman/ui/api.py`
keeps local raw subscriptions but sends only genuinely admitted tickets to sharing.
Source admission closes before subscription/native teardown, outside Api locks that
could otherwise wait against provider lifecycle work.

Timed remote payloads enter the existing store directly. Directional DPS preserves
unknown versus zero. Effect/name expiry affects semantic presentation revisions,
without treating receipt IDs or deadlines as display changes. Display/revision/deadline
capture uses one clock sample. After roster persistence, settings are projected from
the post-acknowledgement authority; the display is not silently resampled under an
old revision. No new page, renderer, expiry worker or public telemetry model was added.

## Review findings and corrections

Independent review findings remain preserved separately from coordinator conclusions
in `.superpowers/sdd/fleet-v2-integration/` (ignored local evidence):

- Preflight: receipt completion alone does not prove uncontaminated metrics.
  Original operation order, reset cuts and actual-application poisoning were added.
- C1 review: a reset needs a narrow full-restatement completion rule across failed
  stream/control predecessors. C3 implements and tests it.
- First C2/C3 review: startup could poison before its first usable publication;
  custom-only associated wrappers bypassed bounded ingress. Both corrected at
  `45d611e8`, with actual threaded reset barriers and connected producer pressure.
- I1 review: capturing settings before roster persistence pushed stale `seen` and
  evicted offline characters. Two genuine RED cases preceded `da026ea2`; independent
  rereview closed the finding.
- Final whole-branch review: PASS for the bounded implemented subset, not control/UI
  completion or platform acceptance. It inspected actual production dependencies and
  the real-client tests. This was static review, not independent test execution.

Polish covered general correctness, silent failures, types/interfaces and comments.
The type-role pass was source-only because its report/annex reading hit its budget;
separate task and whole-branch reviews inspected the contracts. No additional
concrete blocker was established. Review findings were not rewritten as coordinator
opinions. The safe high-confidence settings fix was verified before the final run.

## Verification actually performed

Fresh parent full-suite run at `9135cb25`, with Node and the checkout native release
settings codec present:

```text
TMPDIR=/tmp uv run --no-sync python -m pytest tests/ -q -rs --tb=short \
  --junitxml=.superpowers/sdd/fleet-v2-integration/parent-full.xml
17 failed, 16160 passed, 13 skipped in 688.76s
```

All 13 skips require Windows junctions, WinDLL/DPAPI, window stations/message pumps
or the Windows tray backend. **No Node/native-codec skip was accepted.** Failures:
16 in `tests/test_api_fleetsharing.py`, one in
`tests/test_fleetsharing_reservation.py`. Exact names/messages are retained in
`remaining-failures.json`; the full log/XML remain alongside it. These failures were
not hidden, xfailed, removed or classified as successful coverage. Comparing the
original 44 failures: 17 retain failing node identities, 24 now pass with identical
node identities, and three have explicitly migrated parameter IDs (v2 original-origin
ages and same/new-publication reobservation), whose test families pass. There are no
new failing node identities in this full run; the comparison is recorded separately.

Other fresh parent checks:

```text
uv run --no-sync ruff check .                       # PASS
uv run --no-sync ruff format --check .              # 500 files formatted
node scripts/js_smoke.js                            # all page modules PASS
cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml
                                                    # 1 passed, 0 failed
git diff --check 9156263f..9135cb25                   # PASS
```

Earlier parent gates: provider 554 passed; settings correction 346 passing test
selections (the two new cases were explicitly selected as well as their containing
module). Those are not disjoint coverage totals. Implementer reports additionally
record focused/repeated gates and isolated in-memory mutation checks. Two earlier
broader implementer runs timed out and are not credited as passing; the subsequent
parent full run above completed without implying a green suite.

I2 includes 19 cases using actual file-backed gamelogs, producers, metrics,
coordinator, tickets, worker, state4 file persistence and `FleetRelayClient`.
Scripted HTTP checks real signatures, digest, correlation and persisted revision
before transport. Positive publication, before/after-start retirement, Off during
save/signing, actual leaf-lock contention, late completion, retained restart,
poison with independent terminal controls and slow full-client returns are covered.
The 6.812-second tests advance the injected clock during response reading: they
prove refusal, not improved maximum-body performance. No live backend was contacted.

## Pending decision and remaining risks

Existing On/Stop page calls do not carry the exact displayed consent/source CAS and
retained intent being confirmed. Filling missing arguments from the newest cached
state could authorize unseen state. The coordinator has requested approval for a
narrow change to existing confirmation payloads rather than inventing that policy.
No On/Stop behavior or web files were changed here. Completion also must preserve
honest unresolved/expired-intent history and existing pairing/browser boundaries;
not every remaining test is itself a new public-interface decision.

Until that control composition and its regressions are complete, this is an
**unfinished integration branch**, not suitable for merging/release. The source
Stop adapter still has failing required-argument integration paths. The safe status
projection strips internal saved commands; it does not fabricate terminal success.

Separate unaccepted gates remain: maximum GET performance (the previous
47,022,137-byte body measured 6.812s/~287MiB and still fails the unchanged 5s
admission), real Windows suspend-inclusive clock/platform behavior, native shutdown,
rendered UI/two-PC testing, backend positive automatic scheduling, current-client
cross-repository E2E, original-target ingress normalization and operational cutover.
A shared clock callable is not elapsed-continuity or DB-restore certification.
No old-context timing latch was cleared and no live/deployment action was taken.

## Reviewer knowledge check

1. Why can an old receipt be ignored while its actually applied payload must poison admission?
2. How does a reset-bound full restatement recover a missing delta without acknowledging failed work?
3. Why must startup wait for the real reset cut rather than a fully ready ticket?
4. Why are post-save settings refreshed while the captured remote display keeps its original sample?
5. Which pending control decision prevents this passing local path from constituting full-runtime acceptance?
