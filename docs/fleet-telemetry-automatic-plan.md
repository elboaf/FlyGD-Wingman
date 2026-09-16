# Automatic fleet verification — implementation plan

**Status: contract reviewed; implementation/lane/platform/deployment gates remain.** Authoritative automatic, Stop, receipt and pre-session interface: `fleet-telemetry-v2-automatic-contract.md` (accepted findings 4–5). The adjacent `automatic-control-proof.py` is an offline prototype, not an application test. No production/schema/migration/test implementation is authorized by this pass.
**Goal:** one explicit account-owned opt-in maintains verification across restarts and future fleets, with generation-safe Off and no recurring Start/Refresh chores.
**Architecture:** durable consent and bounded candidate state feed the existing authGD fleet worker. Source authority still requires current verified evidence; Wingman submits choices and observes status through its existing signed lane.
**Stack:** TypeScript/Drizzle/Postgres/pg-boss/Vitest; Python/ES5/pytest/Node.
**Authority:** `W/docs/fleet-telemetry-v2-design.md`, especially §§4–6 and Stop acceptance.
**Roots:** W = `/mnt/c/dev/flygd-wingman/.worktrees/fleet-telemetry-coordination`; A = `/home/tng/workspace/authGD/.claude/worktrees/fleet-telemetry-coordination`.

## Settled scope and precedence

- Required-version clients only. The original `automatic-proposal.md`, `stop-compatibility-check.md` and `ui-proposal.md` retain useful source evidence, **not** their superseded v1-support/fallback promises.
- `fleet-telemetry-v2-api-contract.md` owns the shared dictionary; cutover annex §4 owns the ONE state4 schema, cancellation lifecycle and bounded reserve. C owns the shared version/signing/combat contract. `fleet-telemetry-v2-automatic-contract.md` is authoritative for exact v2 automatic/receipt/source-Stop and pre-session DTOs, selectors and correlation; coordinator reconciles references. No independent v1 automatic route or competing signed lane.
- Reject unsupported reads/publications/controls without admitting telemetry or changing consent/authority. No old Stop convergence, GET-based consent mutation, relaxed generation checks or inferred legacy observations.
- Automatic verification is separate from richer-combat publishing approval and this PC's transmission/participation setting. Existing On/source work permission remains unchanged; coordinator-approved browser Off is withdrawal-only on the existing authenticated account surface, not a new capability.
- Account-owned, default Off; old pairings, grants and historical Starts confer no automatic permission. No consent backfill or source rebinding. Manual-source Stop remains source-specific.
- Explicit durable automatic mode **before** guided grant. Existing grant-only callback stays grant-only; current consent plus usable grant is the continuation. No continuation ledger or browser-to-desktop callback transport.
- Global sharing disable overrides all work. Device revocation cannot transfer approval. No new EVE scopes, account merging, key rotation, desktop verification loop, combat history or fleet automation.

## Repository evidence and integration hazards

- `A/src/db/schema.ts:890–958`: immutable source attribution, terminal retry fences and fetch generations; no persistent automatic consent. Source provenance deliberately has no cascading FKs.
- `A/src/services/fleet-source.ts:176–318`: account-owned signed controls; expected source generation checked before ended-source return; 16 live / 256 retained intents per account and 256-character catalogue.
- `A/src/services/fleet-lifecycle.ts:22–45,451–531`: established lock order and outer retries; natural end increments source/fetch generations and withdraws only matching authority/projections.
- `A/src/services/fleet-source-observation.ts`: claim → bind → commit, 30s fetch claim, pre-roster link snapshot, settled-token/expiry checks, independent expected authority generation. Failed candidates never clear another source's slot.
- `A/src/jobs/fleet-source.ts`: bounded 15s upstream budget; token settlement remains owned after HTTP timeout; membership-cache pacing is distinct from active roster refresh. Existing shared ESI limiter must cover discovery too.
- `A/src/worker/index.ts:54–133`, `worker/fleet-source-scheduler.ts`, `services/fleet-source-maintenance.ts`: one retained owner, nonoverlapping 500ms scheduling, bounded 100-row scans, shutdown drains original promises before pools close.
- `A/src/services/fleet-shared-admission.ts:262–383`: current source/device/account/boss/link/evidence checks at every relay admission; initiating source session and publishing participation are deliberately not source-permission requirements.
- `A/src/services/fleet-pairing.ts:733–766`: account lock precedes revocation; consent must be revoked even when no source exists. Revoking a former approver must not disable a newer replacement-device generation.
- `A/src/app/auth/eve/{fleet-read,callback}/route.ts`: targeted single-use OAuth state and current browser account/session checks; `completeFleetReadGrant` does not opt in or Start.
- `W/wingman/fleetsharing/worker.py:1703–1760`: an ended-source observation currently retires Stop and reports acknowledgement. That is specifically **not** automatic-Off settlement.
- `W/wingman/fleetsharing/state.py`: sole-writer journal, origin/device binding and highest attempted signed revision saved before send. Extend this owner, not a second persistence writer.

## Data/control decisions for review

### Durable rows and retention

1. Consent is account-owned, default generation/revision0 Off, with immutable-for-generation approver attribution, safe checked counters, nextReconcileAt/candidateCursor and a durable terminal receipt reservation whenever On. Exact fields/locks are annex §§2–5. No consent backfill.
2. Candidate unique account/character, max256/account. Annex §5 pins every candidate field, reservation/claim binding and source-free ticket type, including the complete positive-source insert mapping and retainUntil; no initiating-session attribution is added. No roster history, credentials or provider bodies in durable candidates/tasks.
3. Add nullable paired `automaticConsentAccountId` / `automaticConsentGeneration` to `fleetSourceIntent`; both null means manual. Check account equality and positive generation. Preserve through terminal retention/deletion of consent; no cascading provenance FK. Partial uniqueness fences duplicate live automatic sources per account/consent-generation/boss/link.
4. Annex §3 replaces the unsafe full-capacity rule: automatic receipts plus current-On terminal reservation <=256/account. New On/reOn requires room for receipt AND successor terminal reservation; a new valid Off consumes that reservation even at saturation. Retention24h; On freshness60s, durable same-CAS Off has no maximum age. Matching already-Off is a correlated read-only no-op with no receipt/revision growth. Never evict live receipts. SourceStop has one separately reserved inline receipt per bounded retained source (§4).
5. Exact retained receipt retry precedes command expiry/CAS/work gates, but not authentication; return immutable result plus current status. Same live UUID/different normalized command conflicts. After receipt expiry, old On remains expired; unapplied same-CAS Off remains executable without timestamp refresh, while already-applied/stale-CAS Off cannot mutate again. Receipt GET selector is the signed literal UUID path segment, empty body/no query. Annex §§1–4 freeze shapes, limits and source receipt lookup.
6. Every newly accepted enable or explicit replacement-device reauthorization increments consent generation; duplicate accepted intent does not. Off increments revision, invalidates claims and stops that generation's automatic sources atomically. Reauthorization also fences predecessor work/sources, never rebinds them.

### Control and Stop transaction

- Use the exact `/api/fleet/v2/automatic-verification` GET/PUT and `/api/fleet/v2/automatic-verification/receipts/:request_id` GET in annex §1, with annex §2 closed DTOs and C's existing five headers/canonical fleet-v1 plus fleet-api-v2 response binding.
- Split work and terminal gates per annex §3. New On/reOn needs current Member/mode and device/session/acknowledged source permission, but no grant/source/participation/combat approval. Off/Stop/status/receipt need authenticated own-account durable device approval, not Member/mode/grant/active source or fresh session acknowledgement. Invalid session is never bypassed: retain pending, recover where permitted, or use the non-destructive Off-only action on existing /account/fleet-devices (same own-account browser-session gate; no Member/mode prerequisite). Never call pending Off settled merely because work is blocked.
- Serialize with the existing account lock. Probe all affected identities/accounts/authority/source/device selectors **before** taking later lifecycle locks; if selectors change, retry the outer transaction. Do not call a consent-wide helper after locking only the target source/device.
- A retained source-directed Stop still checks its expected source generation. Resolve its immutable consent binding; if that consent generation is current, disable it and its automatic siblings before the ended-source early return. Natural termination alone preserves desired On.
- If natural end changed source generation, return conflict without mutation. Updated normal UI uses consent-aware Off, independent of source lifetime. After conflict, only a fresh explicit same-source command may use an observed generation after proving its immutable binding unchanged; attempted command bytes never change and it never retargets newer consent.
- Old-generation Stop may settle its own old source but cannot disable new consent or new sources. Unknown/purged source cannot infer consent. Manual Stop never touches automatic consent or unrelated sources.
- Off races claim/create/activate under the same serialization: either work commits first and Off withdraws it, or Off commits first and work fails its generation check. Persist receipt, consent, invalidation, audit and outbox effects in one transaction.
- Server status is the closed AutomaticStatus, not client pending mutation. Account consent revision orders cross-device desired state; response binding and runtime/identity fences correlate attempts. Historical receipts can settle their original request without replacing newer current consent. Session signed revision is a different counter.
- Global disable/Member loss retain dormant preference and fence claims/authority. Annex §3 explicitly covers current-session Off, mode session deletion, ineligible recovery, and the non-destructive authenticated browser Off using the same consent/receipt transaction. Revoke is separate and optional. Revocation disables only its still-current generation, even with zero sources; no key reset or silent consent transfer.

## Minimal implementation interfaces and worker ownership

The following summary names refer to the fully specified annex §5 exports; that annex owns exact internal task/claim/token/bind/commit fields and the transaction-only authority extraction.

```ts
type Clock = () => Date; // optional at services; production samples DB time after waits
// services/fleet-automatic.ts
readFleetAutomatic(db, signedCall): Promise<FleetReply<AutomaticGet>>;
controlFleetAutomatic(db, signedCall, command): Promise<FleetReply<AutomaticResult>>;
reserveDueFleetAutomatic(db, clock?): Promise<number>;
claimFleetAutomaticDiscovery(db, task, clock?): Promise<AutomaticClaim | null>;
bindFleetAutomaticDiscovery(db, token, fleetId, membershipRetryAt, clock?): Promise<AutomaticBound | null>;
commitFleetAutomaticDiscovery(db, bound, verified, clock?): Promise<AutomaticCommit>;
settleFleetAutomaticDiscovery(db, ticket, failure, clock?): Promise<void>;
// jobs/fleet-automatic.ts: deps reuse FleetSourceDeps (clock, ESI, fetch, JWT, memory, signal)
runFleetAutomaticJob(deps, task): Promise<void>;
```

- Annex §2 defines closed command/status/result/receipt fields, including no-op settlement. Annex §6 freezes every pre-session body and per-attempt X-Fleet-Attempt correlation, preserving immutable initiation IDs and existing proof domains.
- `FleetFetchTicket` really requires a persisted source and is NOT renamed/reused for discovery. Annex §5 supplies distinct source-free AutomaticClaim -> AutomaticToken -> AutomaticBound -> positive commit; I extracts one authority commit helper after all claim/consent/token/link/slot guards. Negative discovery creates zero intents.
- Discovery performs membership lookup and boss-only roster validation without creating an intent for healthy negative results. Capture link epochs and authority generation before roster I/O; postflight recheck consent/approver/ownership/grant/claims/token/evidence and caps before atomically creating a new source and committing proof.
- Reuse the existing authority-CAS/handover implementation rather than duplicating it. Existing valid automatic source of the same immutable binding is reused; a manual source is never relabelled. A future fleet gets a new source ID. Displacing another valid owner requires fresh newer proof and unchanged captured authority generation; failure cannot clear the incumbent.
- Extend the existing scheduler/outbox/dispatcher with a discriminated automatic-discovery task and claim-keyed singleton. Use the same retained owner and shared ESI client; no `runJob` history, cron/admin reruns, provider-error DLQ or second desktop/server lifecycle.
- Prevent queue head-of-line starvation explicitly: retain active `fleet-source` execution capacity; discovery gets a bounded separate queue slot under the **same** owner/scheduler (one concurrent discovery initially). Cleanup and active-source reservation run before bounded discovery admission. Test actual dispatcher/queue behavior, not only sorted task lists.
- Healthy `not_in_fleet`/`not_boss` is a normal negative: reset failure count and retry after 30s plus deterministic bounded 0–3s jitter, no exponential climb and no tombstone allocation. Always take the later valid endpoint cache/pacing deadline.
- Transient network/5xx/timeouts: 30s exponential backoff capped at 15min plus bounded jitter; honor later Retry-After/shared ESI error-limit/rate-limit reset. Invalid/uninterpretable timing uses existing conservative pacing; never manufacture a fresh evidence lease.
- Invalid grant/ownership/approver suspends affected work with a closed recovery action, not endless bad-credential retries. Due account scan discovers newly usable grants without callback writes; no-grant accounts remain bounded 30s checks without network calls.
- Shared provider throttling can legitimately pause active verification; discovery's own negative cadence/backoff must not do so. Do not launch discovery into known shared backoff, or allow discovery backlog to occupy reserved active capacity. Rotate due accounts/candidates fairly; scan at most 100 per pass, enforce 16/256 source caps and existing 8192-link/256-proof bounds.

## Exclusive integration ownership / parallel files

**I = one assigned shared integration owner**, not independent lane edits:
- A schema/migrations: `src/db/{schema,tables}.ts`, generated `drizzle/*` and metadata; generate with `npm run db:generate`, never edit applied migrations.
- A authority/security: `src/services/{fleet-source,fleet-lifecycle,fleet-source-observation,fleet-shared-admission,fleet-pairing,fleet-sharing-mode}.ts`; source network extraction in `src/jobs/fleet-source.ts`.
- A dispatch: `src/{core/fleet-sharing,core/dispatch-plan,services/outbox,worker/index,worker/handlers,worker/dispatcher,worker/queues}.ts`, `worker/fleet-source-scheduler.ts`; shared contract fixtures and `e2e/fleet-run.ts` pins.
- W signed runtime: `wingman/fleetsharing/{protocol,state,client,worker,scheduling}.py`, `wingman/ui/api.py`, bridge contracts and shared setup-controller composition. C supplies wire changes; A supplies consent semantics; U supplies presentation requirements.

After review of the authoritative annex and I/C shared fixtures, independent owners can implement A `src/core/fleet-automatic.ts` (pure cadence/closed state), `src/services/fleet-automatic.ts` (transactions), `src/jobs/fleet-automatic.ts` (owned discovery) and focused tests in separate files. Routes and exports are allocated by the annex; no author invents new selectors/DTOs. U owns setup rendering/return-page copy; no OAuth mutation changes are needed. Integrate shared-file patches serially.

## Six ordered TDD slices

Every slice: add assertions first, run the exact target to observe the stated RED, implement minimally, rerun GREEN; remove only the implementation under test to demonstrate regression sensitivity. New target files below are explicit proposals, not claims of existing coverage.

### 1. Consent, receipts and default-Off schema (I + automatic service owner)
- [ ] Create `A/tests/fleet-automatic-consent.test.ts`; test absent consent despite old grants/Starts, concurrent two-PC On CAS, **new valid Off at full quota**, reOn reserve, already-Off no-growth, exact retry at quota, expired receipt/command, altered UUID payload conflict, old Off after new On, days-offline unchanged Off after restart, browser Off without fleet session, receipt purge/lost response, transaction rollback on receipt/audit failure and no cross-account access.
- [ ] RED: `npm test -- tests/fleet-automatic-consent.test.ts` — missing consent service/schema first; then behavioral assertions must fail with generation/receipt writes removed.
- [ ] Implement proposed rows/checks/indexes, registered test-table cleanup and account-serialized read/control functions. Generate/review migration with I; validate a pre-change populated fixture leaves consent Off and manual provenance null.

### 2. Atomic consent-wide Stop and revocation/admission fences (I)
- [ ] Create `A/tests/fleet-automatic-races.test.ts`; barrier-controlled Off versus claim/activation, natural-end then matching Stop, natural-end stale Stop conflict, old Stop after new On, retained/purged/unknown IDs, manual Stop and multi-source/multi-device consent.
- [ ] RED: `npm test -- tests/fleet-automatic-races.test.ts tests/fleet-source.test.ts tests/fleet-source-lifecycle.test.ts tests/fleet-shared-races.test.ts` — source ends but consent stays On, stale work activates, or newer consent is incorrectly disabled.
- [ ] Integrate immutable bindings before ended return, full selector locking, approver revoke with zero sources and replacement-generation race, and current consent checks in source pre/postflight plus shared admission. Assert DB consent, authority/projection withdrawal, outbox admission and second-device status, not just replies.

### 3. Bounded discovery and honest pacing (automatic core/job owners + I seams)
- [ ] Create `A/tests/fleet-automatic-worker.test.ts`; use injected clock/fetch/JWT and real pairing/acknowledgement. Cases: no-grant no HTTP, healthy negatives over many cycles, grant becomes usable, 401 versus 403/404 classification, transient recovery, cached membership, error-limit/Retry-After, malformed timing, capacity and duplicate deliveries.
- [ ] RED: `npm test -- tests/fleet-automatic-worker.test.ts tests/fleet-source-worker.test.ts tests/fleet-freshness.test.ts` — no automatic source appears after valid proof; negative attempts exhaust intents or incorrectly grow error backoff; active refresh inherits discovery delay.
- [ ] Implement pure cadence, candidate reservations and owned job using extracted bounded upstream machinery; no transaction across HTTP. Assert no authority before current roster proof and no credential/provider data in receipts, tasks, audits or failure output.

### 4. Restart, handover and queue ownership (I + job owner)
- [ ] Create `A/tests/fleet-automatic-scheduler.test.ts`; extend `tests/fleet-source-handover.test.ts` with automatic/manual/cross-account competitors, old consent delayed proof, paused predecessor and new future fleet ID.
- [ ] RED: `npm test -- tests/fleet-automatic-scheduler.test.ts tests/fleet-source-scheduler.test.ts tests/fleet-source-handover.test.ts tests/fleet-source-fences.test.ts tests/fleet-source-flow-cleanup.test.ts` — restart loses discovery, duplicate claim commits, discovery blocks active verification, or shutdown releases pools before token settlement.
- [ ] Wire the same retained owner, discriminated outbox and bounded discovery queue capacity. Recreate scheduler/job memory against retained DB state; expire claims, verify fresh proof recovery, bounded scans/fair rotation and no terminal-source revival. Exercise real queue head-of-line saturation and post-lock clock expiry.

### 5. Updated-client durable Off and mode-before-grant (W integration + U)
- [ ] Create `W/tests/test_fleetsharing_automatic.py`; extend `tests/test_fleetsharing_worker.py`, `test_fleetsharing_state.py`, `test_api_fleetsharing.py`, `test_fleetsharing_hydration.py` and `tests/fixtures/fleetsharing_page.cjs`.
- [ ] RED: `uv run python -m pytest tests/test_fleetsharing_automatic.py tests/test_fleetsharing_worker.py tests/test_fleetsharing_state.py tests/test_api_fleetsharing.py tests/test_fleetsharing_hydration.py -q` — natural end clears pending automatic Off without a receipt; restart loses pending choice; stale status/reply overwrites newer On.
- [ ] Implement the exact state4 automatic/pending/cancel_after_on/last_result fields and capacity algorithm in cutover §4, including queued Off during attempted On and receipt loss beyond retention. Persist exact request/binding/CAS before send on existing one-request lane. Never rebase an old Off onto fresh consent. Recover matching receipt after lost response, show conflict separately, and retain manual Stop behavior. UI automatic action says “Turn off automatic verification”; this PC's sharing may stay Off while verification runs.
- [ ] Grant opens only after durable On settlement; existing grant route/callback stays grant-only. Extend `A/tests/auth-routes.test.ts`, `tests/accounts.test.ts`, `tests/oauth-tx.test.ts` and automatic-worker target: ordinary grant never opts in; Off/revoke/new generation during OAuth is not undone; current On plus successful grant resumes without Start. Run `npm test -- tests/auth-routes.test.ts tests/accounts.test.ts tests/oauth-tx.test.ts tests/fleet-automatic-worker.test.ts`.

### 6. Current-version integration and controlled cutover gates (I/C/U)
- [ ] Extend `A/tests/fleet-mixed-version.test.ts`, `tests/fleet-source-routes.test.ts`, add `tests/fleet-automatic-routes.test.ts`; run `npm test -- tests/fleet-mixed-version.test.ts tests/fleet-source-routes.test.ts tests/fleet-automatic-routes.test.ts`.
- [ ] RED: unsupported old control still mutates, request version is accepted inconsistently, pre-cutover work publishes authority, or a signed route reports Off without durable receipt or the annex's directly correlated no-op settlement. Use C's shared rejection/receipt vectors, not a parallel fixture schema.
- [ ] Extend `A/e2e/fleet-joint.spec.ts` for two updated devices/accounts, restart/later fleet, independent transmission Off, grant return, lost Off response and stale Stop after new On. Explicitly update integrated Wingman pin; run isolated `npm run test:e2e:fleet`. U separately records rendered setup/browser and Windows/WebView2 acceptance.

## Verification, isolation and remaining review gates

- This drafting pass read repository source/docs and verified both supplied paths are linked worktrees. **No application tests, migrations, runtime/live calls or browser checks were run.** Existing design baseline is not new-feature evidence.
- Preserve original proposal's DB safeguards: `tests/helpers/db.ts` migrates/truncates; Vitest uses worktree-hashed localhost:5433 DB unless overridden, serialized files and run lock. Confirm allocation/collisions before execution; no shared DB parallel runners.
- Ordinary/fleet e2e profiles share a worktree DB: never run concurrently. Allocate distinct DB/app/fleet-TLS/upstream ports per isolated runner; keep Playwright one worker, zero retries and scoped resampling for failures.
- `e2e/fleet-run.ts` pins Wingman `911ae540…`, not supplied baseline `62e1645c`; I explicitly updates/adds the integrated pin gate, never bypasses it. Hand-seeded `tests/helpers/fleet-source-lifecycle.ts` is lifecycle-only, not positive authority evidence; use real worker/provider proof for integration.
- Future final gates: A `npm test`, `npm run typecheck`, `npm run lint`, `npm run format:check`; isolated e2e. W focused suites above, `node scripts/js_smoke.js`, bridge/page conventions, Ruff lint/format and full pytest only with Node plus built release settings codec; record actual results/skips.
- Before implementation: independent review and coordinator reconciliation of fleet-telemetry-v2-automatic-contract.md, C combat contract and fleet-telemetry-v2-cutover-contract.md; I owns generated-schema design/shared-file integration. Exact automatic/pre-session routes/types/receipt policy and browser Off are no longer deferred; the withdrawn session-attribution requirement adds no field, fixture or migration gate; use actual source provenance and immutable consent binding. Real terminal permission, transaction/race, pre-source token/authority and queue-capacity tests remain required; offline prototype checks are not those gates.
- Before rollout: server contract and reviewed generated migrations first, unsupported stored/in-flight telemetry fenced, updated-client acceptance complete. Deployment/activation and live two-PC checks require separate authorization; no implicit mode enablement or legacy downgrade promise.
