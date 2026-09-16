# Cutover migration contract — finding 6

Status: **contract reviewed; implementation/lane/platform/deployment gates remain; not rollout authorization**. This
annex closes the choices left open by fleet-telemetry-v2-contract.md §6. Authority is
W `docs/fleet-telemetry-v2-design.md`. W is 67056ac94c9e79cc0f195a903f123b91fceb50e8;
A is a9bfb49cc0424c1d6156ec905ef94b94cb119e16. Paths below use those roots.
The companion Python program exercises classification and a finite operational
model offline; it neither implements nor proves a running database cutover.

## 1. Decisions, boundaries and ownership

1. **Retire all existing manual source authority and all fleet device sessions.**
   Do not merely clear telemetry. Pending, active and paused sources become ended
   with `mode_transition`; already-ended sources retain their original terminal
   facts. Preserve their immutable account/device/boss/owner-hash/link/intent
   bindings. They remain manual forever. Do not adopt or relabel them as automatic.
2. Keep all accounts, linked identities/epochs, device registrations/revocations,
   canonical key-identity rows (including conflict/deleted-binding tombstones),
   grants, encrypted tokens, device capability approvals and device participation
   choice/generation unchanged. No combat permission or automatic consent backfill.
   Recovery uses the same protected key at the same origin; no blanket re-pairing.
3. Finish old proof lifetimes **under closed ingress**, rather than inventing a
   legacy API discriminator on existing pairing/recovery records. Do not rewrite
   their original challenge/request IDs, issue times, expiry or consumption facts.
   Unfinished initial pairing may need a new explicitly approved same-key request;
   a registered device only needs key recovery (plus separate richer-data approval).
4. All old desktop endpoints are rejection-only, including Stop and recovery.
   No compatibility serving pool, v1 success, redirect, downgrade or fallback.
5. One named foundation/integration owner owns A `src/db/schema.ts`, table registry,
   generated `drizzle/*`/metadata, route/admission integration and the release
   manifest. Automatic owner submits schema requirements to that owner; never
   parallel migrations. W state/worker integration similarly has one writer.
   `fleet-telemetry-v2-automatic-contract.md` owns automatic DTOs, response correlation,
   receipt/consent retention and pre-source tickets. Section4 references those exact DTOs when composing the sole state4 shape; no
   alternative endpoint or receipt selector is introduced.

Rejected: preserving live manual authority (would require an extra revalidation
state); a flag-only cutover (old readers can bypass it); fake activity/incoming
backfill; clearing all client journals; broad key rotation; retriable old Stop
rebased against new automation. Longer bounded maintenance is preferable to a
second pre-session compatibility model.

## 2. Evidence and actual state inventory

| Evidence | Load-bearing fact |
| --- | --- |
| A `src/services/fleet-sharing-mode.ts:30–116` | Both disable **and enable** invalidate sources, clear proof, delete sessions, eligibility, leases and telemetry. Gate CAS and READ COMMITTED are mandatory; current waits are 2s lock / 5s statement. This is not telemetry-only cleanup. |
| A `src/services/fleet-lifecycle.ts:22–30,258–300,451–531` | Global lock order; only non-ended sources selected; end increments source and fetch generations; matching proof generation increments and clears; retention extends through at least end+24h. |
| A `src/services/fleet-source.ts:176–318` | Start has a 60s immutable issue-time window; old ended intent cannot restart. Stop CAS precedes ended return; absent Stop with generation 0 creates a cancellation tombstone. Account ownership is not initiating-session ownership. |
| A `src/services/fleet-source-observation.ts:36–45,166–249` | Jobs require persisted source, current source/fetch generation, exact claim expiry and current proof/token/link checks. No old job may create replacement intent. |
| A `src/worker/index.ts:54–133` | Stop admission, schedulers and dispatchers, then owned original callback promises/token settlement, pg-boss and DB pools. HTTP timeout is not callback drain. |
| A `src/db/schema.ts:710–958` | Durable device approvals and participation; pairing immutable requested scope; recovery request fields/attempts; immutable session ceiling; source retry fences. No automatic consent or old API field at rest. |
| A `src/services/fleet-recovery.ts:33–171,223–353`; `src/lib/fleet-recovery-proof.ts:47–63` | Recovery initiation window [issued−60s,issued+60s), challenge 120s, max 4/key/1024 total, cleanup 100; consumed challenges survive to expiry. Reconnect copies D into new C, K initially empty, not new D. |
| A `src/services/fleet-pairing.ts:101–106,415–564,933–965` | Pairing 10min; session 30min; same-key completion unions D but new C is this request scope. Renewal extends the same session, not C. |
| W `wingman/fleetsharing/state.py:27–103,203–392,526–554` | Versions 1/2/3, exact parsers, sole writer, atomic 64KiB bound; no raw signed request or per-source attempted flag. Session salvage currently loses unusable metadata, so migration must retain the original document separately. |
| W `wingman/fleetsharing/worker.py:1401–1499,1533–1867` | Pre-send revision and participation/pairing attempt saves; recovery has no attempt flag; old Stop rereads/rebases source generation and ended GET retires it. That algorithm must not process migration archives or automatic Off. |
| W `tests/test_fleetsharing_state_v2.py`, `_v3.py`; `tests/test_fleetsharing_worker.py:680–850` | Real old-shape fixtures, exact keyset checks, no-write migration, expired recovery preservation, lost Start/Stop/participation/pairing recovery and same-key behavior. Inspected, not executed here. |
| A `tests/fleet-sharing-mode.test.ts:106–279`; `fly.toml:7–8` | Existing held-reader/registration-preservation tests; release command automatically migrates **before** ordinary app replacement. Default deployment therefore cannot supply the required prior drain. |

### Exact legacy shapes (JSON, not inferred request records)

- V1 allows only `version`, `identity`, `relay_origin`, `session_id`,
  `last_revision`; fields other than version may be absent. Opaque valid session
  spellings remain evidence, not proof of a current registration. No pending
  operation can be reconstructed from V1.
- V2 requires all V3 keys below except `pending_pairing`, `pending_participation`,
  `auth_pause`; those three alone default to null. No absent authority is backfilled.
- V3 requires `version` plus **exactly**:
  `identity relay_origin session_id last_revision device_id session_expires_at
  feature_enabled approved_capabilities session_approved_capabilities
  acknowledged_capabilities observed_participation pending_recovery
  pending_source_commands pending_pairing pending_participation auth_pause`.
- `identity={protected_private_key_b64,public_key_spki_b64}`.
- `pending_recovery={request_id,issued_at,challenge}`; challenge is null or
  `{challenge_id,request_id,nonce,expires_at}`. There is **no completion_attempted**,
  original session, device ID, signature, capability scope or response receipt here.
- Source journal entries are exactly
  `{operation:"start",source_id,character_id,character_link_epoch,intent_created_at,
  expected_generation:0}` or `{operation:"stop",source_id,expected_generation}`.
  No per-source attempted flag, request revision, source creation session, automatic
  consent binding or Stop issue time exists. Start→Stop replaces the entry; the
  superseded Start cannot be recovered from that Stop. Max 256 distinct UUIDs.
- `pending_pairing={mode,pairing_id,approval_url,expires_at,completion_attempted}`;
  mode initial/upgrade/fresh. Last three nullable URL/expiry/ID form a bound tuple;
  no ID implies no completion attempt. Requested capabilities are **not** stored
  in this journal; do not infer them from the new client constant.
- `pending_participation={intent_id,enabled,expected_generation,attempted}`;
  expected generation may be null. Local UUID is **not** a server receipt ID.
- `observed_participation={enabled,generation}` is an observation, not Settings.
  `auth_pause={result,retry_not_before}` retains only proven outcomes
  device_revoked/device_key_conflict/account_ineligible/retry_later.
- `last_revision` is the highest attempted signed revision for the top-level
  session, not the last committed revision or an association with any one command.
  Renewal and acknowledgement have **no separate pending journals**.

## 3. Operational state machine — one explicit forward sequence

These are required future operator gates, not commands to execute now. An
operator manifest pins artifacts, schema hashes, cutover ID, expected mode CAS,
instance/process inventory, DB post-lock fence instant T, expiry barrier H and
completed phase receipts. It contains counts/hashes, never tokens or private keys.
It is an operations record, not another runtime consent table.

| Phase | Required action and exit proof | Failure/interruption |
| --- | --- | --- |
| CLOSED | Close every public/direct desktop route and fleet-related browser approval/grant mutation path at ingress; suppress autoscale/restarts/cron/admin enqueue. Take all old web instances out of service, including non-fleet handlers that can mutate account/link/device state. Keep a static maintenance responder only. Record full inventory, not a routing weight. | Reopening is unauthorized. A process restart does not remove this external fence. |
| DRAINED | Stop **all** old web and worker processes; stop queue/scheduler/outbox admission. Drain admitted requests, original source HTTP/token-settlement promises, both pg-boss and app pools. Account for idle-in-transaction, held row/advisory locks, prepared transactions if enabled, and disconnected request callbacks. Prove zero old DB backends/transactions and no restartable old owner. | Timeout is not drain. Remain closed; explicit operator termination/rollback requires proof of zero residual transactions before continuing. Never race schema against a held request. |
| FENCED | Under closed/drained conditions perform the reviewed READ COMMITTED exclusive-mode CAS disable transition, even if already disabled. Sample DB time after locks, not app time. Preserve key-identity readiness; pending/conflicted reconciliation is a separate gate, never bootstrap a nonempty database. Commit source/fetch/proof/session reset together with mode revision+1 and audit. Inventory retained pairing/recovery deadlines and persist H below before resuming any cleanup. | Unknown commit: inspect phase receipt and exact gate revision/invariants; do not blindly repeat or decrement CAS. Partial transaction rolls back; no schema work until committed fence is proven. |
| SCHEMA | Sole owner applies the reviewed generated forward migration to the **empty** telemetry relation. Remove old dps/ewar/check, add the sole combat payload/origins/bounds from combat annex. Preserve identity/provenance indexes and empty durable authority slots. Automatic tables start empty/default Off; old source automatic bindings are null/manual. No activity/sample/backfill and no dummy DPS. | Verify migration metadata plus actual catalog. Stay closed after partial/nontransactional DDL. A new reviewed forward repair, never an edited applied migration or old schema restore into service. |
| VERIFIED_CLOSED | Install only updated web/worker artifacts with admission still closed; disabled jobs do not create authority. Verify image digests, exact schema, v1 rejection-only routes, v2 current-client/correlation/consent gates, source job replay rejection and retained identity hashes. Wait out H; bounded cleanup may now purge expired recovery records. Run future isolated integration gates before this rollout. | Failed checks keep admission closed. A database/code rollback does not restore old serving permission. |
| AUTHORIZED_REOPEN | Require distinct operator authorization. While ingress/worker admission remain closed, invoke reviewed **enable** CAS on updated code; it again clears sessions/projections and invalidates sources. Then verify postconditions and pin the resulting mode revision. Only now admit updated workers and v2 ingress. v1 stays rejection-only permanently. | A crash after mode enable but before ingress reopening leaves service externally closed; inspect revision and inventory. Recheck all gates before reopening, never infer authorization from enabled=true. |

Existing release-time migration in `fly.toml` must be subordinated to CLOSED and
DRAINED first; ordinary rolling deployment is not this procedure. No release
script may automatically enable sharing. Mode operator timeout/INT4 generation
exhaustion is a refusal requiring reviewed repair, not overflow/reset.

### Source/proof/session postconditions

For each non-ended source at T: state=ended, generation=old+1,
fetchGeneration=old+1, nextFetchAt=null, endedAt=T, terminalReason=mode_transition,
retainUntil=max(old retainUntil, intentExpiresAt+24h, T+24h). Existing lifecycle
code leaves fields such as fetchClaimExpiresAt/enqueueUntil as inert history;
**do not claim they are cleared**. Old generation/state checks fence them.
For each occupied authority slot: sourceId/sourceGeneration=null,
authorityGeneration strictly advances once for that withdrawal,
linkedCharacters=[], verifiedAt/expiresAt=null. Already empty slots retain their
monotonic generation; never delete/reset slots. All telemetry, publisher leases,
fleet device sessions and legacy eligibility are empty. Device participation
counter and durable approvals are unchanged. Already-ended source facts remain.

Retain queued old outbox/pg-boss deliveries as inert tasks or explicitly cancel
only identified old source tasks; do not purge unrelated jobs. On delivery, absent
or ended source / wrong generation must return without creating a replacement or
proof. A job with an old fetch ticket fails even if every old provider call later
returns positive. No scheduler may scan ended history as automatic candidates.
Only an explicit new automatic consent plus annex-defined fresh ticket/proof can
create new automatic authority. Session recovery and grant callbacks do not Start.

### Pre-session barrier (avoids invented legacy fields)

At drained fence T, read the maximum original expiresAt of **all retained** pairing
requests and recovery challenges (consumed included). Define
`H=max(T+120 seconds, maxPairingExpiry, maxRecoveryExpiry)` and retain that bound in
the cutover manifest before cleanup. Do not reopen until a post-lock DB sample
`N >= H` on the same coherent DB clock domain. Expected maintenance is at most
about ten minutes after drain; unexpectedly distant deadlines or clock regression
refuse this gate pending investigation, not forced timestamp rewriting.

This simultaneously expires all old pairing completions, old recovery completions
and all old initiation proofs that could pass the ±60s freshness check at T.
The 120s term is essential: issuedAt=T+60s is accepted at T and remains valid
until T+120s, even if no challenge row was retained. T+60s alone is insufficient.
Recovery challenge cleanup remains bounded 100/pass and never frees unexpired
consumed rows. Pre-cutover v1 body/signatures cannot mint new sessions after the
barrier by changing only a route/envelope. New v2 key proofs use a fresh request
only after the old proof lifetime is terminal. V2 availability after the server barrier
is the admission boundary; the client does not invent an H response field or trust
a local wall-clock estimate of the operator manifest. This is authentication renewal,
not replaying a disclosure/automatic consent. The crypto v1 domain labels remain.
No source generation alone can fence pre-session pairing, hence this separate gate.

## 4. Exact forward client migration core: state 1/2/3 → 4

Disk version 4 is independent of API2/signing1. **This is the single final state4
shape**, including automatic controls, not a migration core plus reserved TODO.
W integrator implements it once in the existing sole-writer `state.py`; no second
journal/file/writer. The automatic annex owns referenced wire DTOs, not another
disk schema. V1/V2/V3 gain no invented attempt flags during migration.

### 4.1 Closed root and migration

V4 has the exact V3 root keys listed in §2, `version:4`, plus exactly `cutover`
and `automatic`. All keys required, duplicate/unknown keys refused. On migration,
identity/origin/device/D/auth_pause retain validated observations; current session,
expiry/C/K, feature_enabled/observed_participation and active recovery/pairing/
participation journals become null, last_revision=0, pending_source_commands=[].
Original old values, including old revision, remain immutable below. No new key,
consent, acknowledgement or attempted flag is inferred.

```text
cutover = null | {
  original: exact decoded state1/2/3 document,
  outcomes: [{selector: Selector, status: Outcome}]
}
Selector = "session" | "pairing" | "recovery" | "participation" |
           "source:" + lowercase ExistingUuid
Outcome = "fenced" | "superseded_session" | "recovered_identity" |
          "observed_choice" | "expired_unproven" | "dismissed"

automatic = {
  observed_consent: Consent|null,
  pending: PendingAutomatic|null,
  last_result: AutomaticCompletion|null
}
PendingAutomatic = {
  command: AutomaticCommand, attempted:bool,
  cancel_after_on: CancelAfterOn|null
}
CancelAfterOn = {request_id:U, intent_created_at:T}
AutomaticCompletion = {
  pending: PendingAutomatic,
  outcome:"receipt"|"already_off"|"observed_off"|"rejected"|
          "superseded_unknown"|"cancelled_unsent",
  receipt: AutomaticReceipt|null
}
```

Initial automatic is exactly all three values null, never false-consent proof.
Selectors occur exactly once for each original extant item, in session/pairing/
recovery/participation/source-array order, <=260 entries; initially all fenced.
Source selectors have only fenced/expired_unproven/dismissed outcomes: §5 chooses
unknown history, not unexposed original-intent proof. Superseded_session applies
only to session; recovered_identity only pairing/recovery; observed_choice only
participation; expired_unproven only pairing/recovery/Start (not a dateless Stop).
Dismissed is explicit unknown-history acknowledgement, never successful mutation.

Original decoded values (old spellings, nulls and absent V1 keys) never change or
enter signed work. V4 parses idempotently; no nested archive. Unknown versions or
malformed non-session identity/origin/journals quarantine without overwrite. Only
invalid session metadata may be salvaged for same-key recovery; invalid values
stay in original and never enter headers. Foreign/corrupt DPAPI stays untouched.
Original identity/origin must agree with the active identity/origin while archive
exists. Explicit identity replacement requires informed archive removal, not a
silent rebind. No default origin, plaintext-key backup or repeated history append.

### 4.2 Active-field validators — no implicit version substitution

Identity uses the actual `_identity` public-key canonicalization/protected-base64
rules, origin uses `canonical_origin`. Device IDs use ExistingUuid; current V4
session IDs use Token. last_revision is N and must be0 without session; expiry/C/K
must all be null without session. Nullable session expiry, feature_enabled bool,
D/C/K capability arrays and observed_participation retain their existing unknown
semantics; arrays use the two-right common vocabulary, not software-supported
rights. Observed participation is exactly {enabled:bool,generation:N}.

All active dates use T; state load **retains expired valid timestamps**, it does
not perform admission/retry. The new active fields are exactly:

- pending_recovery=null or {request_id:Token,issued_at:T,challenge:null|{
  challenge_id:ExistingUuid,request_id:Token,nonce:Token,expires_at:T},
  completion_attempted:bool}. Challenge request_id equals outer request_id;
  completion_attempted implies challenge present. This flag is NEW V4 only.
  Save it true before one-use HTTP completion. Restart/response loss with true
  retires that challenge and begins a fresh initiation after applicable proof/
  retry boundary; never repeat completion. Begin retries retain request/time and
  proof, with fresh in-memory X-Fleet-Attempt. No attempt token is persisted.
- pending_pairing=null or {mode:"initial"|"upgrade"|"fresh",pairing_id:ExistingUuid|null,
  approval_url:string|null,expires_at:T|null,completion_attempted:bool,
  requested_capabilities:Capabilities}. Capabilities are immutable for this NEW V4
  request; never inferred from an archived V3 pairing. The three nullable fields
  are all null or all present; attempted requires present ID. Validate/bind URL
  using automatic §6 and canonicalize accepted relative URLs to the same-origin
  absolute URL before storage, retaining max2048 scalars. Save completion_attempted
  before each completion/poll. Restart or lost possibly-successful completion
  uses same-key recovery, never resets the flag on coarse409 to repeat completion.
- pending_participation retains exactly {intent_id:ExistingUuid,enabled:bool,
  expected_generation:N[0..2147483646]|null,attempted:bool}; attempted requires
  nonnull CAS. Explicit new On with null CAS waits for current observation and
  fresh user confirmation; no automatic rebase. Restart unknown attempt first
  reads current state; matching value is observation, not its receipt. A contrary
  newer choice needs fresh explicit action. Local Off inhibits publishing at once.
- pending_source_commands is an array <=256 of the exact SourceStart|SourceStop
  **wire DTO including protocol:2**, unique source UUID ignoring case. Stop includes
  new request_id/T/expected_automatic, never copied from legacy Stop. No extra
  per-source attempt flag; after restart outcome is unknown. Exact Start may retry
  only within its original60s window; Stop first seeks its receipt, then exact
  immutable retry only within60s. SourceStart has no receipt UUID. A valid source
  response settles current new Start, not an archived old Start. Expired/unprovable
  new Start/Stop stays journaled for explicit dismissal/new same-source action;
  never refresh timestamp/CAS or overwrite on ended GET as automatic-Off proof.
  Unrelated sources/automatic choices/recovery are not blocked. Same-source new
  action requires the user to acknowledge retiring the unknown previous intent;
  atomically replace only after the old in-flight attempt drains. No new unbounded
  source completion history is stored. Ordinary automatic UI uses durable Off,
  not this short-lived troubleshooting Stop.
- auth_pause retains exactly {result:"device_revoked"|"device_key_conflict"|
  "account_ineligible"|"retry_later",retry_not_before:T|null}; deadline present iff
  the latter two. Generic transport/HTML/error never writes a proven auth pause.

Any pending work requires valid identity+origin. Automatic observation/pending/
last_result additionally requires device_id; it is bound to that same origin/key/
device, not to a fleet session. Session replacement retains it; a mismatching
recovered device fences it, never rebinds it. Observed consent uses the exact
Consent validator and monotonically merges revision after bound response only.
Equal revision requires identical Consent. Readiness/rosters and server receipts
other than the one last automatic completion are not persisted caches.

PendingAutomatic command uses the exact six-field AutomaticCommand validator;
attempted is strictly boolean. cancel_after_on is allowed only with enabled=true
AND attempted=true; its UUID differs from the On UUID and survives restarts. No
CAS in this cancellation: it is authorization to cancel ONLY that On's proven
result, not whichever On is current. Receipt completion requires nonnull exact
matching automatic receipt, all other completion outcomes require receipt=null.
already_off/observed_off require original enabled=false; cancelled_unsent requires
attempted=false. `rejected` records definitive refusal, not a transport error.
The one bounded last_result preserves that command/cancel intent and classification,
not arbitrary strings/raw HTTP bodies. Explicit admission after a prior completion
acknowledges replacing that single visible result; not an unlimited history log.

### 4.3 Complete automatic command/cancellation lifecycle

1. Fresh user action captures the currently authenticated observed generation AND
   revision, UUID and T. No unknown CAS can submit On/Off. Persist pending with
   attempted=false before acknowledgement; reserve the future terminal shape below.
   Before HTTP save attempted=true and the session's next attempted revision in
   ONE write. Body fields and deterministic JSON serialization never change on
   retries; only signed session/proof/revision and HTTP attempt correlation change.
2. With no contrary choice, restart or response loss schedules receipt GET first
   for attempted command. Matching receipt/direct bound result settles historical
   outcome while separately merging current status. receipt_not_found proves no
   retained receipt, not noncommit. On may exact-retry within original60s; expired
   On cannot be replayed as fresh. Off may exact-retry without age ceiling while
   its CAS remains current. At INT4_MAX retire current session and same-key recover;
   preserve pending/cancellation and old attempted floor until session replacement.
3. **Off while unattempted On:** since no HTTP was admitted for it, record
   cancelled_unsent. Explicit Off may replace it against the displayed current
   predecessor CAS, never the uncreated successor. A newer On is likewise a new
   explicit command only after cancelling an unsent command; no draft resubmission.
4. **Off while attempted/in-flight On:** save exactly one cancel_after_on UUID/T
   before reporting cancellation queued. Do NOT replace pending On or send another
   On retry; wait for the original attempt to drain and perform receipt recovery.
   Repeated Off clicks coalesce to this exact intent. Ordinary work yields to its
   receipt read/cancellation. Never say server Off while this is pending.
5. Only an exact On receipt (direct result or receipt GET) proves the target. In
   one durable write record the On receipt in last_result and replace pending with
   Off using cancellation UUID/T, enabled=false, expected_generation and revision
   exactly from **receipt.result** (On expected+1/+1), attempted=false and no
   cancellation. This is the one authorized derived command, not a CAS rebase.
   If current status is newer On, the derived old Off must not be sent: retain it
   for superseded_unknown/fresh user confirmation, or recover its own receipt if
   already attempted. No newer status may change its target. If current is Off,
   retire derived Off as observed_off, not its own commit. On receipt remains
   historical; late replies never overwrite current consent.
6. Lost On receipt beyond24h: current generation alone cannot identify which
   competing device won that generation. NEVER derive Off from that status, even
   if it equals expected+1 or names this device. Keep pending On+cancel intent
   fenced as unknown and expose fresh explicit Off/On against current status.
   Before admitting that action, drain old HTTP, atomically move old pending to
   last_result as superseded_unknown and admit the new confirmed command. Unknown
   older On cannot commit after its original60s admission window; when superseding
   an attempted On without its receipt, first obtain a bound device DB-time anchor
   proving N>=intent_created_at+60s and wait for the old HTTP attempt to finish.
   Receipt-not-found alone is insufficient. This finite wait applies only to its
   possible On, not unrelated key recovery or migration history.
7. Other supersession of attempted work also requires old HTTP drain and explicit
   acknowledgement of unknown history. An old attempted Off retains its old CAS;
   a subsequent explicit On changes generation if it wins, fencing that Off. Never
   silently retry/refashion the old command after supersession. A queued
   cancel-after-On may be explicitly cancelled by the user, but original attempted
   On still needs settlement or the expiry/drain rule before new admission.
8. Current Off can converge a pending Off as observed_off with unknown own outcome.
   An attempted On carrying cancellation without its receipt cannot be labelled
   applied or On-confirmed from current Off; retain the unknown On until explicit
   dismissal/supersession. An old Off receipt may settle its original command while
   newer On remains displayed. Completion clears pending atomically into last_result;
   completing a derived Off may replace its preceding On completion (one bounded
   chain, no loss of the unresolved command). Stop/ended-source GET never settles
   automatic Off. Grant navigation starts only after On receipt, never while its
   cancellation exists. Browser Off is separate and learned by signed status.

### 4.4 Exact byte partitions and future terminal reserve

Canonical V4 disk serializer is compact JSON (separators comma/colon), finite
numbers, UTF-8 with only lone surrogates escaped where immutable original evidence
requires it (existing `_compact_utf8` semantics). No pretty/ASCII choice that can
change reserve arithmetic. Old file raw input bound remains65536; its original
compact representation must also fit65536 or quarantine without overwrite.
Total V4 bound262144, with disjoint upper partitions:

| Partition | Bytes |
| --- | ---: |
| cutover.original | 65536 |
| cutover.outcomes | 32768 |
| active V3-named root fields (including version, excluding cutover/automatic) | 147456 |
| automatic | 8192 |
| cross-object framing and unused safety headroom | 8192 |

Check every partition and whole document, never trade away the archive to admit
work. Active source commands each <=400 compact UTF-8 bytes (maximum closed DTO
is below this), <=256; reserve every unused source slot as400 bytes before new
admission. Reserve all non-source active fields at simultaneous maximum within
32768 bytes, including future pairing URL, both capability rights, recovery flag,
new session/revision max and participation CAS. Thus256*400+32768 plus array/key
framing (<1024) fits147456. Existing source entries remain immutable; size is a
refusal before admission, never eviction/truncation. A new source/pairing/On cannot
consume future terminal capacity.

Automatic has fixed one pending+one last_result+one observed Consent. Each closed
PendingAutomatic <=512 bytes (including attempted On+CancelAfterOn), each Consent
<=512 and each AutomaticReceipt <=1024; last_result<=1792. Reserve all three at
these maxima **on every state admission/save**, even initially Off/no pending:
512+512+1792 plus framing fits8192. This includes later derived Off, retained On
receipt, cancellation and checked Gmax widths, not a reserved TODO. The proof
constructs their maximum-width fields and the simultaneous archive/source/journal
stress shape. Server H+R<=256 reserve is independent; both must hold.

Use existing atomic writer/0600/DPAPI policy. Validate and size full detached
candidate, then one atomic replacement. Parse/reserve/write failure leaves prior
file and pending intent intact; no send or success acknowledgement. Settings never
reset. V4 load validates only, never clears journals because expired; runtime owns
explicit transitions above. No proof reads/writes actual user state.

## 5. Forward operation outcomes (all rows preserve original bindings)

Unattempted describes only the current saved binding, never erased predecessors.
Participation attempted=false marks the current saved CAS as unattempted, but the
old worker may already have replaced a preceding CAS. Pairing false is weaker:
`worker.py:1843–1854` resets it after coarse HTTP 409, so it cannot prove no
completion was ever sent. A journal merely existing does not prove an attempt. Attempted-unknown means it may have committed.
Committed-known requires a validated response persisted before the crash or a
retained exact server receipt/binding; a counter increase or current desired state
is not a receipt. Expired/purged/absent does not prove never committed. Offline
fixtures can stipulate server evidence, but the migration does not invent it.

| Legacy operation / versions | Unattempted or no attempt proof | Attempted / outcome unknown | Committed-known; expired/purged/unprovable | Updated recovery/user action |
| --- | --- | --- | --- | --- |
| Pairing / V3 only | No ID means no completion is selectable, but may hide a lost begin response. With an ID, completion_attempted=false means no currently marked outstanding attempt, not never sent: coarse 409 resets it. Retain mode/key/origin/ID/URL/expiry. | true: may already have registered/upgraded same key. Do not repeat one-use completion. | A saved successful completion normally clears journal; durable device registration/approvals survive cutover. Expired ID or generic 401/409 cannot establish revocation or noncommit. | Wait proof barrier, then same-key v2 recovery. Successful recovery resolves identity, **not proof of the old requested capability upgrade** (not stored). Refresh D/C/K; richer scope needs explicit approval. Only genuinely unregistered initial key needs explicit new same-key pairing. Fresh key setup only after proven revoked/conflict or explicitly acknowledged key-unavailable recovery, never cutover alone. |
| Recovery / V2,V3 | Without challenge, begin may have been sent; no attempted flag exists. With challenge, initiation was observed but completion status is unknown. | Preserve request_id/issued_at/exact challenge nonce+expiry, no timestamp rewrite or cross-origin replay. | Saved success clears journal; its now-retired session is superseded. Consumed/expired challenge cannot return its lost session. | After H fresh key-proven v2 recovery at original origin, same key. Archive old challenge as expired_unproven then recovered_identity after bound success. Auth pauses retain existing reasons/backoff. Generic error is no key rotation authority. |
| Renewal / V1,V2,V3 | No journal; cannot infer pending renewal from last_revision. | Highest attempted floor only, possibly for any signed call. | Saved expiry is observation, not an enduring session. | Archive old session/floor and mark superseded_session on valid replacement. No old renewal replay. New-session renewal preserves C/K; recovery creates C=D,K=[] without broadening D. |
| Acknowledge / V2,V3 observations; V1 unknown | No pending ack journal or old requested list beyond observed K. | Do not interpret software support as a submitted consent. | Saved K belongs only to retired session. | Fresh v2 ack only for independently validated D∩C. Shared-only remains shared-only; old ack never authorizes combat or automatic intent. |
| Participation On / V3 | attempted=false describes only the current saved CAS; earlier rebased attempts are not recoverable. Null expected_generation lacks restart-safe fresh consent. | attempted=true retains original intent UUID/choice/CAS; no server receipt by UUID. Never reset attempted or rebase original CAS. | A saved success clears journal. Current desired value is observed_choice, not original commit. Newer generation with opposite choice is conflict; unavailable observation is fenced. | Read current device after recovery. If On currently proven, preserve observation but publish combat only with explicit combat D∩C∩K. Otherwise show Review sharing choice and require a **new explicit action**, leaving old binding archived. No migration auto-On. |
| Participation Off / V3 | Preserve exact choice even while Settings is Off or telemetry absent. | Same immutable UUID/expected generation/attempted; inhibit local publishing immediately. | Proven current Off settles observed_choice only; a current On/newer generation cannot be overwritten by old Off. | Read current state. If still On, show Unresolved previous Off; user can issue a new explicit Off against displayed current CAS. Do not silently apply the old worker’s rebase. Unknown remains fenced; local inhibit persists until resolution/new explicit user choice. |
| Start / V2,V3 | **No attempted flag**, even if last_revision=0 (journal can survive session replacement). Never call it unattempted from disk alone. | Preserve source UUID, character/link epoch, original intent_created_at and expected_generation=0. No new timestamp/UUID/signature from this intent. | Even same-UUID manual+ended view lacks original-intent provenance. Keep fenced; after the immutable Start60s horizon classify expired_unproven, never noncommit/ready. | No legacy Start is sent on v2. Source reads are troubleshooting observations only; show Prior Start retired by update, outcome unknown. Future verification requires explicit automatic opt-in, never inferred from Start or grant. |
| Stop / V2,V3 | **No attempted flag or issue time**; source UUID and CAS only. expected_generation=0 is cancellation intent, not proof of never sent. | Never change original expected_generation, retarget UUID or synthesize automatic consent binding. | No exposed view proves the original retained pre-cutover binding; same-UUID ended/manual remains unknown. Absent/purged source is likewise unprovable; do not use absent-ID generation-0 creation to recreate authority/history. | Read only to reconcile. No legacy Stop mutation is resent. Retain unresolved status when binding cannot be proved; a new explicit Off uses the current automatic annex control, independently confirmed. An old Stop never disables newer opt-in, even if the character/device is the same. |
| Signed revision / all versions | No per-command mapping, signature or canonical bytes is stored. | Preserve highest attempted bound with old session; do not allocate it to a guessed command. | New session means a new revision space, not proof old commands failed. | One serialized lane. Persist new session+floor atomically, next signed revision before every send, including reads. Retired archive never enters that lane. |

Version 1 has none of the four pending-operation fields or auth_pause; no invented pending operation
is created. V2 lacks pairing/participation/auth_pause only. V3 has all exact fields.
The new SourceView adds automatic:null for manual provenance but has no original
intent time/link/device creation binding or pre-cutover creation proof. A reused
manual UUID after purge is indistinguishable. **Chosen outcome: unknown/fenced**
for old Stop, and expired_unproven for old Start only once its original60s horizon
is known elapsed. Neither automatic:null nor same-UUID/ended proves history. No
proven_pre_cutover_manual field, new lookup, provenance column or assumed offline
fixture evidence is permitted. The scratch resolver receives the actual closed
SourceView and deliberately cannot produce observed_terminal. Existing server-side
immutable source fields do not magically cross that API boundary.

Source command attribution to a retired session **cannot be reconstructed**: the
root session is a counter binding only. The server does not persist an initiating
source session either. Original source account/device/owner/link attribution,
where retained server-side, must never be replaced by current-session guesses.

### Fenced unresolved state and retention

- The resolver starts independently of telemetry/Settings On and uses the existing
  serialized recovery/read lane. It may read after reconnect, not mutate automatic
  consent while resolving old work. All responses use combat/automatic annex
  request/pre-session binding checks; stale/malformed replies leave fenced status.
- Unresolved archive outcomes have no wall-clock deletion timer. Keep the one
  bounded original document until each item is explicitly resolved or the user
  dismisses its uncertain history. Dismissal says outcome unknown, not sent/Off.
  Do not collect successive archives: a V4 load is idempotent. No credentials or
  Settings reset accompanies archive retirement. Keep the archive until explicit
  user removal even after all outcomes are terminal; no unbounded history append.
- Same-key reconnect must not be blocked by an unrelated unknown old Start/Stop.
  Only local publication/control that could contradict unresolved participation
  remains inhibited. A new explicit user action is separately journaled and may
  supersede UI inhibition, never mutate the old original record.
- Server manual source bindings survive existing retainUntil, including at least
  24h after cutover end; cleanup does not accelerate it. After purge there is no
  promise of an exact old outcome. Session old revision evidence stays on the
  client; server sessions are deliberately deleted. Pairing/recovery retain their
  existing original expiry/consumption bounds; no indefinite pre-session authority.
- Automatic source-to-consent provenance/receipt horizons are solely those in
  `fleet-telemetry-v2-automatic-contract.md`; old manual sources have no consent association.
  Any future automatic source with unknown/purged provenance cannot control current
  consent. Annex horizon/capacity verification is a final integration dependency.

## 6. Offline proof and future implementation gates

`cutover-migration-proof.py` uses the actual legacy in-memory validators/serializer
without loading/saving user state, unprotecting keys or constructing a worker.
Synthetic, documented fixtures cover all three versions, source/participation/
pairing/recovery shapes, malformed journal rejection and 256 retained controls.
Its V4 adapter/classifier is a specification only. Its finite model rejects schema
transition with held web/worker/transaction work, checks occupied/empty generation
fences, proof-barrier equality and separate reopen authorization. Route inventory
is read from A files; rejection handlers are **modeled**, not production handlers.
Counterexample probes intentionally weaken drain/Stop safety and must fail checks.

Before release, implement real isolated tests for DB-held old readers/writers,
non-fleet lifecycle writes, token-settlement after timeout, interrupted fence and
migration, queued task delivery after reopen, exact database preservation hashes,
all v1 methods nonmutating, same-key v2 recovery after lost initial/upgrade completion,
atomic V4 persistence failures and bounded terminal-control capacity. Run those
only with separately allocated test resources/authorization. This pass neither
runs those tests nor generates a migration. Source clock/integer ceiling, the merged state4 transitions and reserved terminal
capacity require independent review before code or operational approval.
