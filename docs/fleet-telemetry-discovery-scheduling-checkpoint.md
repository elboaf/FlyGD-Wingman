# Backend discovery/scheduling — bounded coordinator acceptance

Accepted implementation checkpoint on authGD `feat/fleet-v2-backend`:
`0e7f902b31b0c9d370018a1b0acaeb28467318df`. Source remains on that stopped, clean
lane; this document neither integrates nor activates it.

Exact reviewed lineage from accepted suspension checkpoint
`2a0c65cfc1168f5c4847ccbd0fc14061b00e6fa8`:

| Commit | Scope |
| --- | --- |
| `59f48cb3324bf19911fc1c16f1b33d32de54d9bd` | Guarded positive commit through the shared authority-proof writer |
| `bc9cb5a1a0e3b017acd8acc8fcd2d4a0fdc7f928` | Real bounded reservations and durable reconciliation preserving suspension |
| `0e7f902b31b0c9d370018a1b0acaeb28467318df` | Complete automatic job and retained scheduler/outbox/queue integration |

Normative automatic/suspension contracts were read from Wingman coordinator
`9b933da3be049e03e05ce0766ea0fdaa1c5a60b4`. No contract, schema or migration
amendment was inferred from implementation convenience.

## Accepted implementation

- Manual and automatic positive proofs use one transaction-only authority writer.
  Automatic admission retains its independent consent, approver, claim, owner/link,
  settled-token, JWT, authority-generation, newer-observation and post-lock-time
  fences. Source creation, displacement, proof and candidate pointer commit atomically;
  typed refusal rolls back before separate exact-claim settlement.
- Actual reservation reconciles binding state under a bounded account/candidate budget,
  retained cursor/capacity and strict leases, atomically persisting the exact outbox
  task. Same-binding suspension, pacing and exhausted counters survive consent-only
  changes. No retained identity is deleted to manufacture capacity.
- The full automatic job awaits guarded positive commit for `UNCOMMITTED`; it cannot
  finish by discarding positive evidence or claiming success before persistence.
- The existing scheduler, ESI instance, memory, abort signal and retained original
  owners remain shared. Active roster capacity is reserved independently of discovery.
  Outbox selection reserves class capacity and keeps its bounded total.
- Sequential discovery batches of at most 100 retain one original admission owner.
  Errors do not silently discard a valid suffix. Both Fleet queues stop accepting
  work before original promises drain and pools close; framework expiry does not
  transfer ownership away from unresolved original token operations.

The lane independently reproduced starvation with batch size one: 18/50 and 19/50
claims after 90 deliveries. The corrected finite cohort reaches 50/50 real claims/
negative settlement, and restoring the old batch size reproduces starvation. That
is bounded finite-cohort evidence, not unrestricted throughput certification.

## Evidence and attribution

Coordinator independent review `d6c03d78-0063-420`: **ACCEPT, bounded static audit**,
no actionable correctness/security/scope finding in this pass. It inspected all 11
changed production files, relevant existing dependencies and selected substantive
assertions across seven changed test files. It did not rerun tests or contact a DB.
Its original report remains separate from coordinator conclusions in local evidence.

**Lane-reported runtime:** 2,246 tests across 44 distinct files in two serialized
runs: 922/31 affected files and 1,324/13 disjoint files, no failures/skips. The lane
also reports typecheck, lint, formatting and diff checks passing. These are not
coordinator-rerun DB results or a backend full-suite claim.

**Fresh coordinator execution:**

```text
TEST_DATABASE_URL=postgres://authgd:authgd@127.0.0.1:1/authgd_unavailable \
  npm test -- tests/fleet-api-v2-fixture.test.ts tests/fleet-api-v2.test.ts \
  tests/fleet-v2-basic-codecs.test.ts tests/fleet-combat-profile.test.ts \
  tests/dispatch-plan.test.ts
1122 passed / 5 files / 12.49s
npm run typecheck -- --incremental false             PASS
git diff --check 2a0c65cf..0e7f902                    PASS
```

The normal unavailable-DB setup attempts the explicitly selected port 1. This is
pure-test coverage, **not DB transaction coverage or zero-socket execution**. Neither
occupied/default 5433 nor the lane's disposable 55462 database was accessed by this
coordinator verification. No queue, worker or deployment was activated.

Exact three-commit lineage and clean status were verified. Protected database,
migration, approved fixture, generic token/ESI/verifier and ingress paths are unchanged.
The frozen wire fixture still hashes to
`cde5318e54d46ad2b6e9769f65685831e9f23bf429dad9a49b8e8a8d9c1877fc`.

## Limits and next boundary

The new suites declare 123 cases (55 commit, 44 reservation, 24 runtime); review was
selective at the assertion/fixture level, not exhaustive reading of all test lines.
Historical mutation evidence was inspected, not rerun. P2's future-kind dispatcher
exclusion was deliberately superseded by P3 and is not a final-HEAD invariant.

Shutdown of an already-owned batch suffix after abort is supported by code inspection,
not a newly established dedicated suffix regression. Restart tests rebuild worker
resources, not an OS process. Defensive reuse uses the disclosed restored-row fixture.
Finite-cohort progress does not bound arbitrary arrivals/provider latency or allow
abandoning an indefinitely pending token CAS.

Still open: backend integration, current-client/joint E2E, original-target ingress
normalization, platform/hosted CI, backend full-suite/live-provider acceptance and
operational cutover. The measured 47,022,137-byte GET at 6.812s/~287MiB still exceeds
the unchanged five-second admission; this checkpoint neither remeasures nor waives it.
No schema change, rebase, amendment, push, merge, live call or deployment occurred.
