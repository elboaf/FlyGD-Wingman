# Duration scaling correction — implementation checkpoint

Additive repair base: `a484d9ce9998f5285f9150861033873241efd2c7`, over fixed `ab06a6efde9ade0f40791d812d922356e8e6c16f`. Preserve prior commits and untracked evidence. Coordinator E-IMPLEMENTATION-REVIEW.md holds acceptance for E-P1/E-P2; source scope remains controller.py only.

## Test-first confirmation

Before production edits, the four deterministic scaling cases failed and three new publication-error persistence cases passed: `scaling-red-output.txt` (4 failed, 3 passed, 59 deselected in 13.35s). Work counts instrument VideoInfo identity-field reads and RowSnapshot serialized rows/resolved IDs, not helper names or elapsed-time thresholds.

| Exercise | Identity-field reads | Serialized rows | Resolved IDs |
| --- | ---: | ---: | ---: |
| Warm 1,000 | 1,526,500 | 2,000 | 0 |
| Warm 2,000 | 6,053,000 | 4,000 | 0 |
| Queued 250 | 348,875 | 62,500 | 62,500 |
| Queued 1,000 | 5,520,500 | 1,000,000 | 1,000,000 |

Local no-I/O supporting timings on a484d9ce, excluding setup: warm 1,000/2,000 = 0.121879/0.439579s; queued 250/1,000 = 0.380019/5.653652s. `scaling-benchmark.txt` is a preserved lane-local harness, not an implementation commit or a CI threshold. It uses real controller/rows/infos/cache, no-op ports, inline queued probes, and disables only the timed drain's disk save. No network/user-state/native effects.

## Bounded repair and lifetimes

- Group weakly tracked live VideoInfos by exact identity once per accepted scan. Producers use an invocation-local grouped snapshot, built lazily after admission and replaced after committed scan installation/rename. Read live probed/answered flags within each relevant group rather than freezing verdict values across producer interleavings.
- Keep a bounded CURRENT path-to-row-ID index, no strong VideoInfo history. Replace it from the actual accepted installation IDs before publication, including an empty install. Resolve only the incoming current ID and same-path IDs per result. Full row rendering remains presentation, never per-result ownership discovery.
- Advance a publication-owned topology revision after installation and rename. Check it inside publication after each probe/queue read. Rejected scans do not alter indexes; cancellations still fail existing run admission before context creation; each drain invocation starts a new local context. Foreground context lasts only its selection, never a controller/run field.
- Rename maintenance must account for ALL paths actually moved by the existing weak-object transition. A deleted stale destination can leave two current IDs at one path; a subsequent rename can repoint both VideoInfos. Rebuild the bounded current index from its known IDs after the full rename transition, not merely by moving the requested ID. Do not expand this repair into changing existing rename display semantics.
- If any same-path installed identity conflicts, refuse an old cache write; do not choose an arbitrary last-row owner. All matching installed objects still change via set_duration; only detached objects are assigned directly. Keep cache dirtiness/publication/save ordering and no new retries/pruning/schema.
- Multi-result rename/installation tests cover context invalidation, including newly retained intermediate scan objects. A deleted-destination/second-rename case verifies duration updates reach all actually moved installed objects through set_duration. Existing stale-scan/run, folder-switch, rename/path-reuse, captured-duration, URL and WorkGate tests remain. RowSnapshot._replace's existing linear row search remains out of scope; do not claim all drain processing is linear.

## Initial green results and measured work

All 70 lifecycle cases passed after the repair (4.41s), including all original 21 behavior cases, four scaling guards, three publication-error persistence guards and four multi-result/index-lifetime cases. Foreground/background publication exceptions propagate the original exception object while accepted duration, flags, frozen cell and reloaded disk verdict remain coherent. Retained-winner hydration persists its admitted cache entry before publish_rows raises. These three exception-order cases also passed before the scaling repair; no exception suppression/retry policy was introduced.

The same metadata/serialization/resolution instrumentation used by the guards, exercised by the lane harness on the repaired controller:

| Exercise | Identity-field reads | Serialized rows | Resolved IDs |
| --- | ---: | ---: | ---: |
| Warm 1,000 | 27,000 | 2,000 | 0 |
| Warm 2,000 | 54,000 | 4,000 | 0 |
| Queued 250 | 7,500 | 0 | 250 |
| Queued 1,000 | 30,000 | 0 | 1,000 |

Warm hydration retains only its normal two complete payload renders, not repeated winner scans. Queued duration reconciliation no longer constructs any full rendered row payload or resolves every installed ID for each result. Relevant groups/current IDs are examined per result; the whole weak registry is grouped once per batch/topology revision.

Comparable no-I/O timings without counting enabled: warm 1,000/2,000 = **0.018054/0.037292s**; queued 250/1,000 = **0.003319/0.024876s**. Before/after outputs and harness remain local (`scaling-timings-before.txt`, `scaling-timings-after.txt`, `scaling-counts-after.txt`, `scaling-benchmark.txt`). These support the deterministic work counts; they are not wall-clock CI assertions.

Committed-range polish and the final full suite are pending at this initial checkpoint. No acceptance/integration/native claim is made.
