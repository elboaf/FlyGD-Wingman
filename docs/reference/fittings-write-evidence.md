# Fitting copy evidence and cache reconciliation

Fittings copies are explicit, additive operations, not synchronization. A valid
ESI `201` with a fitting ID proves a successful create. It does not invalidate
all cached GET representations: an empty HTTP `200` arriving later can still
contain content from before that create.

## When success protection ends

Every retained `success` intent protects its character/canonical-content pair
from another create. The controller retires that record only when all of these
conditions hold:

1. A full GET was started at least `contracts.READ_CACHE_SECONDS` after the
   **latest** of the intent's creation, sent and completion timestamps. The
   pinned horizon is currently 300 seconds. Using completion protects delayed
   POST responses; taking the latest timestamp protects a rolled-back clock.
2. The request started no earlier than either persisted snapshot timestamp,
   and the response clock did not move behind request start.
3. The request omitted the ETag and returned a complete, schema-valid HTTP
   `200`. A `304`, transport error or invalid body cannot retire evidence.
4. The replacement snapshot and retired intent set were saved atomically.
   A failed save leaves the old live and persisted protection intact.

At that point the success record becomes expendable and is removed, rather
than retained as diagnostic history. Returned presence protects the fitting
through the ordinary presence model; qualifying absence permits a **new
explicit** copy. Nothing is automatically retried.

Positive returned content establishes presence immediately, even before the
horizon. It does **not** retire early success evidence: another cache could
still return a pre-create empty representation on the next refresh. Unknown
and surviving in-flight intents keep their existing reconciliation and startup
semantics; positive reconciliation still records a success. Success remains
success and does not acquire the unresolved-intent veto on Forget.

A later local HTTP receipt timestamp, elapsed age alone, and missing ETags do
not prove that the remote fitting was removed. Clock-forward jumps and remote
cache behavior exceeding the pinned horizon cannot be proven safe from these
local timestamps; no live ESI verification was performed for this correction.
The repository's original ESI contract was checked with compatibility date
`2026-08-12` in `docs/superpowers/specs/2026-09-03-character-fittings-design.md`.

## Bounded retention and recovery

`contracts.MAX_OPERATION_RECORDS` remains the terminal-record budget (currently
200), not a global cap on all intents:

- Protective successes take priority over failed diagnostic history.
- Failed history fills only the remaining slots, newest first, subject to its
  existing age limit.
- Protective successes are never age-pruned or count-pruned. Existing unresolved
  intents retain their independent exemption from both limits.
- Before **each** durable pre-send transition, execution checks that another
  potentially successful create fits the success budget. Preflight does not
  reserve an entire batch. When full, the pair is unavailable and unattempted;
  neither its in-flight intent nor a POST is emitted.
- Failed or unknown outcomes do not consume success slots. Safe reconciliation
  may convert existing unresolved records into successes, even over the budget;
  no evidence is destroyed to force the count down. Further creates are refused
  until capacity is available again.
- Loading already over-limit valid evidence preserves it, subject to the
  existing hard state-file size limit. The same retention rule applies to
  controller compaction, serialization and load normalization.

Recovery is to wait at least one cache horizon after the latest copy, then
refresh characters with successful copies. A qualifying full refresh releases
slots whether the fitting is present or has been removed. Cached `304` replies,
failed refreshes and detected clock rollback require another qualifying
refresh. Refresh and other safe operations remain available. Forget/authority
cleanup behavior is unchanged.

Deleting a local library entry while it still has protective successes is
refused: deleting the entry would otherwise discard those successes to satisfy
store relationship validation. After qualifying absence retires the records,
local deletion is available again. Ordinary remote-presence deletion protection
continues to apply.

## Compatibility limits

There is no schema migration, wire-contract change or downgrade blocker.
**Unchanged schema does not imply downgrade safety.** Older binaries may prune
protective successes by count or age, or ignore them after a cached response.
Already-evicted evidence cannot be reconstructed locally. This correction
conservatively protects retained success records from older binaries, but does
not recover deleted records or change tolerant recovery of corrupt relationships.

## Verification scope

The lane's deterministic tests use an injected clock, fake ESI transport and
real controller/store operations. They assert actual POST counts, pre-send save
candidates, persisted evidence and restart behavior, including cache/ETag/304
cases, delayed requests, clock rollback, save failure, count and age bounds,
exact-capacity refusal and recovery. No live ESI writes or real user state are
used. Windows/WebView2 smoke testing remains an integration responsibility.
