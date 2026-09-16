# Automatic/control and pre-session contract — accepted findings 4–5

**Authoritative annex for automatic/control and pre-session interfaces.** This
replaces the deferred interfaces and receipt policy in `fleet-telemetry-automatic-plan.md`.
Behavioral authority remains `docs/fleet-telemetry-v2-design.md`; C owns combat,
shared signing and limits; the cutover annex owns migration. **Status: contract reviewed; implementation/lane/platform/deployment gates remain; not implemented
services/schema or release approval.** Bases inspected: W `67056ac9`,
A `a9bfb49`. No live calls or database work is needed to run the adjacent proof.

## 1. Framing, primitives, routes, errors

The shared dictionary is `fleet-telemetry-v2-api-contract.md`: API2 / signing1 / state4, operation-specific sizes and error codes. This annex owns the closed control/pre-session DTOs, not an alternative combat envelope.

Objects below are closed: every listed key is required, null is explicit, no
extras/duplicate JSON keys; bool is never integer. JSON UTF-8, no NaN. `U` =
canonical lowercase UUIDv4 for NEW request/reservation IDs; `ExistingUuid` is the
existing W protocol.uuid/A z.uuid accepted hyphenated UUID (versions1..8 plus
nil/max, case-insensitive comparison, original spelling retained in command
bytes). Existing source/device/character-link/account and pre-session IDs retain
that validator, never force-migrate identities just to canonical v4. `N` = integer 0..2147483647, `N+` = 1..2147483647;
commands expecting a source generation accept at most 2147483646. `G` = safe
integer 0..9007199254740991; automatic generation/revision use G, not the signed
session's int4 revision. `ID` = positive JS-safe EVE ID. `T` = canonical UTC
`YYYY-MM-DDTHH:mm:ss.sssZ` round-tripping to the same valid timestamp. `Token` =
canonical unpadded base64url 32 bytes (43 chars). `Hash` = 64 lowercase hex.
Capabilities = `[]`, `["shared-source-v1"]`, or
`["shared-source-v1","combat-v2"]`; no other ordering or combination.
All counter arithmetic is checked, never wraps. An On is refused before exhausting
space for a later Off (generation < Gmax; revision <= Gmax-2); exhaustion returns receipt_capacity for On,
never wraps or consumes reserved Off capacity. Off may use the
reserved final revision; no-op Off does not increment. Source counters keep their
existing checked int4 boundary. New work must reserve terminal counter space: a non-ended source, outstanding
fetch claim and occupied authority slot may advance for positive work only while
the resulting int4 counter is <=Nmax-1; its final invalidation may consume Nmax.
At that point an ended source/empty slot is never revived or reset. Terminal Off
does not need to increment already-ended sources/empty slots. Legacy counters
already lacking this reserve require the cutover annex's closed repair gate, not
new automatic admission. Candidate/claim safe-integer ceilings are specified in §5.

| Method | Exact path | Request | Success |
| --- | --- | --- | --- |
| GET | `/api/fleet/v2/automatic-verification` | empty | AutomaticGet |
| PUT | `/api/fleet/v2/automatic-verification` | AutomaticCommand | AutomaticResult |
| GET | `/api/fleet/v2/automatic-verification/receipts/:request_id` | empty | ReceiptGet |
| GET | `/api/fleet/v2/sources` | empty | SourcesGet |
| PUT | `/api/fleet/v2/sources` | SourceStart or SourceStop | SourceStartResult or SourceStopResult |
| POST | `/api/fleet/v2/pairing-requests` | PairingBegin | PairingBegun |
| POST | `/api/fleet/v2/pairing-requests/:id/complete` | PairingComplete | PairingCompleted |
| POST | `/api/fleet/v2/recovery-challenges` | RecoveryBegin | RecoveryBegun |
| POST | `/api/fleet/v2/recovery-challenges/:id/complete` | RecoveryComplete | RecoveryCompleted |

All signed operations use C's **same** five authentication headers and canonical
`fleet-v1` scheme, literal v2 path, shared signed revision/read cadence and one
in-flight device lane. No automatic signature scheme/header or parallel transport.
The receipt selector is the literal validated UUID segment, covered by the
canonical signed path; no unsigned selector header, query or GET body. Construct
it from `/api/fleet/v2/automatic-verification/receipts/` + validated U; reject
percent-encoded/noncanonical spellings, extra segments and trailing slash before
service admission, not redirect them. All listed routes reject any query string.
GETs require zero bytes, absent/decimal-zero Content-Length and absent
Transfer-Encoding. Signed PUT limit 2048 bytes; POST limit 2048; automatic and
receipt success limit 16 KiB, sources success 1 MiB, all errors 64 KiB. Bound
streaming input before parse and service values before commit. No truncation.

Each signed 200 has `Cache-Control:no-store` and exactly one
`X-Fleet-Request-Binding=hex(SHA256(UTF8("fleet-api-v2\n") || C))`, C the exact
authenticated canonical request bytes with no appended newline. Require it before
accepting payload or settlement, including empty/no-op/receipt responses. Errors
never establish success or clocks. API envelope is protocol 2, signing argument
remains protocol 1. No v1 fallback; old routes are rejection-only per C/cutover.

Automatic/source errors are exactly `{protocol:2,error:ControlError}`; status map:

| HTTP | Closed codes | Meaning/action |
| --- | --- | --- |
| 400 | bad_headers, bad_request, update_required, invalid_intent | Invalid framing/shape/version; invalid_intent includes expired/new future intent; no mutation. |
| 401 | unauthorized | Invalid/expired/unbound/revoked session/key; no eligibility oracle. |
| 403 | forbidden, capability_required, fleet_read_required | On/Start work permission absent; fleet_read_required is manual Start only. |
| 409 | conflict, request_id_conflict | CAS/source binding mismatch; or live retained UUID has a different normalized command. Read status; never silently rebase. |
| 404 | receipt_not_found | No unexpired own-account receipt; deliberately indistinguishable absent/purged/other-account. No consent inference. |
| 429 | rate_limited, receipt_capacity | Session cadence vs new-On retained capacity. Honor bounded retry; Off never returns receipt_capacity. |
| 503 | feature_disabled, service_unavailable | New work disabled, key index unready or transient transaction fault. Off with valid authenticated ready identity is not gated by mode.enabled. |
| 409 | revision_replayed | Construct fresh signed attempt with higher durable attempted revision, preserving exact command. |

Missing routes/methods, redirects, HTML, wrong version/binding or malformed errors
are incompatible/transport failures, never success; clients preserve journals.
Method not allowed is HTTP405 `{protocol:2,error:"method_not_allowed"}` plus exact
Allow methods from table; no fallback. Validation/auth refusal does not issue a
receipt. All errors are no-store. Semantic/CAS refusal changes no consent/source;
signed cadence/revision handling follows the common gate, never an independent
counter. Server/client map these literals centrally, not arbitrary provider text.

## 2. Closed automatic DTOs and correlation

```text
Consent = {
  generation:G, revision:G, enabled:bool,
  approving_device_id:ExistingUuid|null, approved_at:T|null,
  disabled_at:T|null,
  closed_reason:null|"explicit_off"|"source_stop"|"approver_revoked"
}
SourceBinding = {source_id:U, source_generation:N+, consent_generation:G}
AutomaticStatus = {
  consent:Consent,
  approver:"none"|"this_device"|"other_device"|"revoked",
  readiness:"off"|"global_disabled"|"member_required"|"authorization_required"|
    "capacity_limited"|"waiting_for_grant"|"waiting_for_fleet"|"verifying"|
    "reconnecting"|"ready",
  recovery_action:"none"|"restore_membership"|"authorize_fleet_read"|
    "reauthorize_automatic"|"wait",
  retry_at:T|null, sources:SourceBinding[]
}
AutomaticCommand = {
  protocol:2, request_id:U, intent_created_at:T,
  enabled:bool, expected_generation:G, expected_revision:G
}
AutomaticReceipt = {
  kind:"automatic", command:AutomaticCommand,
  accepted_at:T, expires_at:T, result:Consent
}
AutomaticGet = {protocol:2, status:AutomaticStatus}
AutomaticResult = {
  protocol:2, request_id:U,
  result:"applied"|"replayed"|"already_off",
  receipt:AutomaticReceipt|null, status:AutomaticStatus
}
ReceiptGet = {protocol:2, receipt:Receipt, status:AutomaticStatus}
Receipt = AutomaticReceipt | SourceStopReceipt
```

Absent consent is exactly generation/revision 0, enabled false, every nullable
field null, approver none, readiness off, action none, retry null, sources [].
After first On generation is positive; approving device/time are immutable within
that generation even after Off/revocation. On while already On is **explicit
reauthorization**, not a no-op: increments generation and revision, changes
approver to caller, closes predecessor sources and reservations, requires fresh
work proof. Off preserves generation and approval attribution, increments revision
only if enabled, sets disabled_at/reason, and closes all that generation's work.
For enabled consent disabled_at/reason are null. Off consent may retain its old
approver; revoked means that exact retained approver is currently revoked.

Status sources contain only current-consent-generation non-ended automatic
sources, sorted by source UUID, unique, max16; no manual or other-account sources.
No source is required to turn Off. They are observations, not membership proof.
Readiness precedence: off; global disabled; Member absent; revoked approver;
ready if any current usable authority; verifying if any current claim; reconnecting
if transient/expired evidence; capacity_limited if discovery/source caps block;
waiting_for_grant if no usable owned grants; otherwise waiting_for_fleet. Grant
revocation for all previously usable candidates yields authorization_required /
authorize_fleet_read rather than endless transient retry. Ready/verifying/waiting
fleet/off have action none; global_disabled/capacity/reconnecting use wait;
member_required uses restore_membership; revoked approver uses
reauthorize_automatic. retry_at is next admitted due time or null when user/action
is needed; readiness never changes saved consent. No grant/provider secrets or
unbounded per-character failure list is returned.

Pending mutation is **client state**, not a server DTO status. The sole exact
state4 schema, validators, terminal capacity and complete restart/supersession
algorithm are `fleet-telemetry-v2-cutover-contract.md` §4. Its PendingAutomatic preserves
command/attempted plus one bounded cancel_after_on intent. Attempted On never
silently disappears into a newer Off; only its exact On receipt can authorize the
derived Off targeting that On's resulting CAS. Queued cancellation is durable
before UI acknowledgement and never targets another device's replacement On.

`status.consent.revision` orders **account-wide consent**, not signed requests.
Only merge status after complete response-binding validation and current
origin/key/device/runtime fence. Never replace a larger observed consent revision
with a smaller one, including a receipt's historical result. Equal revision must
have identical Consent; contradictory payload is malformed. Equal-revision live
readiness may change; use the current lane observation order, not receipt history.
Devices learn each other's changes via ordinary signed status reads (not a push or
second loop); after focus/restart/command, schedule one urgent status read.
An exact receipt can settle its original pending command while a newer current
status says On; UI must show that newer On, never label historical Off as current.
A CAS conflict never rebases an old Off. A valid current status showing Off may
retire a pending Off as `observed_off` (local completion classification, no new wire
field); retain/report "account Off observed; this request outcome unknown" when no
matching receipt exists. A status showing newer On requires fresh explicit user
confirmation. A historical Off receipt may acknowledge only its own request.

## 3. Bounded receipts that cannot strand opt-out (F4)

One account has at most **256 automatic receipt slots, counting reservations**.
Every enabled generation owns exactly one durable *unfilled terminal reservation*
until disabled, regardless of how long it stays enabled. This is not an expiring
receipt. Let H be retained automatic receipts and R be 1 if enabled, else 0.
Invariant: `H + R <= 256`. A newly accepted On/reOn needs room for its own receipt
and its successor reservation: after purging expired receipts, require
`H + 2 <= 256`. ReOn replaces, rather than accumulates, the old reservation.
The reservation is acquired atomically with On; no accepted On exists without it.

A new valid Off always uses that reservation: `H'=H+1,R'=0`. It does not use the
ordinary admission path. Hence even `H=255,R=1` accepts Off, obtaining `H=256`.
Neither audit/outbox admission-history quotas nor source-intent quotas may veto
this transition; existing storage/infrastructure transaction failure can still
prevent success and must be reported honestly. Cleanup/invalidation effects and
receipt commit are all-or-nothing. Audit uses a bounded fixed event, never a
second optional command-history admission quota. On/reOn may be rate-limited;
opt-out is never refused solely because retained history is full.

An **already-Off command matching current generation AND revision** returns
`result:"already_off",receipt:null` and current status. It is an authenticated,
read-only no-op, not a newly accepted persistent mutation; no receipt slot, revision
or request-UUID tombstone is allocated. This is intentional bounded settlement,
not a claim of permanent per-UUID history. A lost no-op response retried after
another device's On conflicts; it cannot turn off that newer generation. Receipt
GET for such a no-op returns receipt_not_found. UI may acknowledge the directly
correlated no-op while showing its observed revision, but cannot recover its
historic outcome from a later unrelated GET. Finite storage cannot preserve an
unbounded stream of arbitrary no-op UUIDs.

Processing order under account serialization: authenticate terminal identity gate;
look for unexpired own-account receipt UUID across both receipt stores; compare
normalized command; if exact return replayed historical receipt plus freshly read
status, even if work permission/CAS/lifetime has since changed; altered command
returns request_id_conflict. Then validate operation-specific intent freshness, CAS and operation
permission; handle already-Off; check On admission; atomically mutate+record.
Existing receipt reads/replays require identity/own-account terminal permission,
not current Member, source, grant, On capability ceiling or participation.

Receipt `accepted_at` is post-lock DB time, `expires_at=accepted_at+24h`; validity
is now < expires_at. Never evict an unexpired receipt; reads do not extend it.
**On/reOn freshness, not Off lifetime:** new On/reOn requires
`intent_created_at <= now < intent_created_at+60s`. Automatic Off (signed or browser)
requires only a valid nonfuture intent_created_at and exact current generation AND
revision; it has **no maximum intent age**. Keep original UUID/body/timestamp/CAS
across offline queueing, restart and session recovery; only the transport attempt
is fresh. SourceStart/SourceStop both require nonfuture intent_created_at and new admission
strictly before intent_created_at+60s (receipt replay precedes this check); durable account opt-out uses AutomaticCommand(enabled=false).

Exact unexpired receipt lookup precedes CAS/age. After receipt purge, an unapplied
Off whose CAS still matches can apply using the still-reserved terminal slot,
regardless of age. If it already applied, consent revision advanced; repeat cannot
apply twice and returns conflict, not a reconstructed historical receipt. Client
then reads authoritative status: current Off settles *desired-state convergence*,
not proof its own old request committed. An already-Off no-op whose CAS still
matches stays already_off without allocating history at any age. Any intervening
On/reOn changes generation/revision; old Off conflicts whether the prior receipt
exists, expired or never existed. On after purge still requires fresh60s intent
and cannot replay an old opt-in. No timestamp refresh or automatic CAS rebase. Request
UUID uniqueness is guaranteed during retention, not forever; altered old UUIDs
outside retention are not a supported way to mint new commands. No raw HTTP/body
serialization hash is used as intent identity: compare the closed normalized
command field tuple (operation + UUID + timestamp + CAS + desired mode).

Approver revocation disables its still-current enabled generation, bumps revision,
fences all claims/sources and releases R without an extra user receipt. This cannot
hit receipt quota, including zero-source accounts. Revoking a former approver
cannot affect a newer replacement-device generation. No receipt falsely claims
that a pending explicit Off was the revocation actor. Cross-device stale On/Off
fails CAS. Natural source end does not change consent revision or release R.

### Opt-out versus work permission — deliberate terminal boundary

| Condition | Signed status/receipt/read-only replay; signed Off and Stop | New On/reOn and discovery |
| --- | --- | --- |
| Same-account valid unexpired signed session, nonrevoked key/device, ready key identity; durable device shared-source approval | Required. Account is resolved from authenticated session, never a body account ID. | Required. |
| Session ceiling/ack contains shared-source | Not required for withdrawal-only operations; requiring fresh acknowledgement after recovery could trap Off. No rights are granted. | Required for explicit On; worker retains approving-device approval, not an initiating session lease. |
| Member / feature enabled | Not prerequisites for terminal controls with a valid session. Read returns explicit blocked readiness. | Required, rechecked after locks. |
| Active source / usable Fleet Read grant / telemetry participation / combat approval | Never prerequisites. | Source not needed; grant not needed to save On. Worker proof needs grant. Participation/combat never required for verification. |
| Invalid/expired session, revoked key, or unready key index | No unauthenticated Off or fabricated acknowledgement. Keep pending exact choice; no signed bypass. | No admission. |

Member/global-disable keep dormant desired consent but immediately fence authority
and claims. Existing mode transition deletes fleet sessions; recovery refuses
disabled mode/non-Member. Do not promise signed Off in that sessionless interval.
The coordinator-approved **non-destructive browser Off** below remains available
with an authenticated own-account browser session, independently of fleet session,
Member/mode, grant, source, device acknowledgement and approving-device liveness.
Revoke remains a separate optional destructive action, never required for opt-out.
Without either authenticated channel, show pending authentication, never server-Off
success. No OAuth rights, fake fleet session or broadened On/source permission.

### Browser Off on existing /account/fleet-devices — coordinator ruling

No new REST route. Render current consent and an Off-only control on the existing
`GET /account/fleet-devices` surface under its own-account browser-session gate.
Submit Next Server Action POST to `/account/fleet-devices`, retaining existing
Next action dispatch (opaque framework action ID, not an invented API endpoint).
GET/render and cache revalidation are read-only regarding consent.

```ts
// Same closed command as signed API, but enabled is literal false.
type AutomaticOff = AutomaticCommand & {enabled:false};
type BrowserAutomaticView = Omit<AutomaticStatus, "approver"> & {
  approver:"none"|"account_device"|"revoked"
};
type BrowserOffReply =
  | {ok:true;request_id:string;result:"applied"|"replayed"|"already_off";
     receipt:AutomaticReceipt|null;status:BrowserAutomaticView}
  | {ok:false;request_id:string|null;
     error:"bad_request"|"unauthorized"|"invalid_intent"|"conflict"|
       "request_id_conflict"|"service_unavailable";
     status:BrowserAutomaticView|null};
// app/account/fleet-devices/actions.ts; untrusted entry point, exact input below
turnOffFleetAutomaticAction(input:unknown):Promise<BrowserOffReply>;
// services/fleet-automatic.ts; trusted server context, never body account/session
readFleetAutomaticForBrowser(db:Db, auth:{accountId:string;browserSessionId:string},
  clock?:()=>Date):Promise<BrowserAutomaticView|null>;
turnOffFleetAutomaticForBrowser(db:Db,
  auth:{accountId:string;browserSessionId:string},command:AutomaticOff,
  clock?:()=>Date):Promise<BrowserOffReply>;
```

Validation: input must be the exact six AutomaticCommand fields including
protocol2, canonical request_id U, valid T, literal enabled=false and two G CAS
integers (no booleans/coercion, missing/extra keys, On, source IDs, account/device/
session fields). Bound the normalized command to2048 UTF-8 bytes before service
work; retain framework action body bound. Unknown/invalid input returns bad_request,
request_id=null, status=null, changes nothing. Do not consume a malformed UUID as
receipt identity. The browser creates one UUID/timestamp on explicit Off click,
captures the rendered generation/revision, disables duplicate submission and keeps
that immutable input for response-loss retry; a new render never rewrites it.

Action authenticates through the **existing requireAccount/getSessionAccount
browser cookie gate**. It reads the raw browser cookie only server-side and supplies
it with the resulting accountId to the service, not from an action argument or URL.
No browser session value goes in DTOs, receipts, logs or task tickets. Service
probes that session's account, obtains normal full selector/identity/account locks,
then browser-session lock **after account and before authority/source/device locks**;
rechecks same account and unexpired session using post-lock DB time. Missing/expired
or changed binding returns unauthorized with null status; session logout/revocation
races cannot turn a stale page into permission. Own account key chooses consent;
no ability to select another account. requireAccount's existing login redirect may
precede the closed action result; it is authentication navigation, not Off success.

CSRF boundary: only the existing Next Server Action POST mechanism, with Next's
Origin vs Host/X-Forwarded-Host check; do not relax allowedOrigins or add GET/query
mutation. The action additionally requires the request Origin to equal configured
canonical app origin (missing/malformed/mismatched fails before service), so a
missing-Origin request is not accepted just because it has a cookie. Proxy headers
must be trusted/normalized by deployment, not used as an alternate account origin.
Framework action IDs/closure encryption are not authentication. Scope is existing
SameSite browser cookie/session handling, not new OAuth grants or fleet headers.
No X-Fleet-Attempt or canonical fleet signing is added to browser actions; those
remain the desktop/pre-session protocols. Browser response correlation is the
awaited action request plus matching request_id/receipt command and account-page
lifetime; read-only browser status is never imported as a desktop signed receipt.

Both signed control and browser Off call the **same transaction-only consent
mutation function** in services/fleet-automatic.ts:
`applyFleetAutomaticCommand(tx:DbTx, prepared:PreparedAutomaticControl,
command:AutomaticCommand, now:Date):Promise<AutomaticMutation>`.
`PreparedAutomaticControl` is module-private, constructed only by validated gates;
keys exactly accountId:string, actor:({kind:"device";deviceId:string}|{kind:"browser_off"}),
consent:Consent|null, locked:Awaited<ReturnType<typeof lockFleetLifecycle>>.
`AutomaticMutation={request_id:string,result:"applied"|"replayed"|"already_off",
receipt:AutomaticReceipt|null,consent:Consent}`. The helper explicitly refuses
browser_off with enabled=true, including receipt lookup: browser action cannot
read/replay an On receipt by changing its discriminator. Gate already holds full
consent/sibling selectors and the account lock; no nested transaction/new ledger.
Same CAS, normalized fingerprint, cross-store UUID lookup, H+R budget/reserved Off
slot, receipt retention, source withdrawal and fixed audit transaction apply.
Browser audit identifies actor account and `browser_off`, never attributes it to
the approving device. Saved approval/device attribution remains unchanged.

Success returns current browser status after mutation, matching immutable receipt
for applied/replayed or null for already_off; revalidatePath('/account/fleet-devices')
after committed work. Conflicts return current own-account status (other errors
status=null), never automatically retry with current CAS. Render highest observed
consent revision; equal revision must have identical Consent. Late action receipt
cannot overwrite newer On. Browser status uses account_device rather than pretending
that a browser has this_device identity. No source/character catalogue or On control
is added to the page by this contract.

Desktop learns browser Off from its **next authenticated request-bound automatic
status** on the existing serialized lane after ordinary polling/reconnect; absence
of a usable fleet session remains unobserved locally, not fabricated confirmation.
Browser action has its own UUID. It does not insert a receipt for an outstanding
desktop UUID or send a browser-to-desktop callback. On observing current Off, a
pending desktop Off may retire as observed_off, with unknown-own-request outcome,
not applied/replayed. Only a matching receipt (direct result or receipt GET) may
establish its own historical commit. Newer On remains visible and old pending Off cannot disable it. No new
poller/continuation ledger or key revocation is involved.

## 4. Source bindings, Stop and receipt recovery

```text
AutomaticBinding = {consent_generation:G}  // positive; account is implicit owner
SourceView = {
  source_id:ExistingUuid, generation:N+, character_id:ID|null,
  state:"pending"|"active"|"paused"|"ended",
  reason:null|"stopped"|"expired"|"superseded"|"not_in_fleet"|"boss_lost"|
    "identity_changed"|"fleet_read_invalid"|"member_lost"|"device_revoked"|
    "token_invalid"|"mode_transition"|"service_unavailable"|
    "untrustworthy_evidence"|"timed_out"|"ended",
  pending_expires_at:T|null, automatic:AutomaticBinding|null
}
SourceCharacter = {
  character_id:ID, character_name:string, character_link_epoch:ExistingUuid,
  has_fleet_read:bool, token_usable:bool
}
SourcesGet = {protocol:2,sources:SourceView[],characters:SourceCharacter[]}
SourceStart = {
  protocol:2, operation:"start", source_id:ExistingUuid, expected_generation:0,
  character_id:ID, character_link_epoch:ExistingUuid, intent_created_at:T
}
SourceStartResult = {protocol:2,source:SourceView}
SourceStop = {
  protocol:2, operation:"stop", request_id:U, intent_created_at:T,
  source_id:ExistingUuid, expected_generation:N,
  expected_automatic:AutomaticBinding|null
}
StopEffect = "manual_only"|"unknown_cancelled"|"disabled_current"|
  "current_already_off"|"older_generation_only"
SourceStopReceipt = {
  kind:"source_stop",command:SourceStop,accepted_at:T,expires_at:T,
  source:SourceView,automatic_effect:StopEffect,consent:Consent
}
SourceStopResult = {
  protocol:2,request_id:U,result:"applied"|"replayed"|"already_stopped",
  receipt:SourceStopReceipt|null,source:SourceView,
  automatic_effect:StopEffect,status:AutomaticStatus
}
```

SourcesGet remains own-account catalogue/troubleshooting, not a fleet roster.
Max256 sources and max256 characters, unique/sorted IDs. Character name retains the
existing max200-scalar text rule, using C's fixed Unicode-16 category table for v2
rather than W's Unicode-14 host validator; no new identity-name normalization. Sources read uses work permission
because it discloses character grant catalogue; receipt/status need only terminal
permission. Start retains existing 60s admission, source ID idempotence, 16 live /
256 retained account caps and manual provenance, never implicitly On.

Storage provenance is the immutable pair
`(automaticConsentAccountId, automaticConsentGeneration)`; both null manual or both
present with account equality and positive generation. Never rebind a source on
restart, later fleet, reOn, takeover or terminal transition. No cascading FK from
source provenance to consent. Consent generation/revision survive dormant periods
and receipt cleanup for account lifetime; account deletion removes consent and
receipts, leaves only source provenance under existing terminal retention policy.
Source tombstones retain original binding and any stop receipt for at least the
later of existing intent-expiry+24h, endedAt+24h and receipt expiry; source purge
never transfers its identity or infers current consent. New automatic fleet uses a
new server UUID. Consent receipts never depend on the source still existing.

Stop transaction checks retained request receipt first. Otherwise lock complete
source/consent sibling selectors, then compare expected source generation and
expected_automatic to the target's **immutable** binding. A naturally ended source
with changed generation conflicts; a fresh, explicit same-source command may use
the observed generation only after checking the unchanged automatic binding. No
transparent rewritten retry. If owning generation is current and enabled, disable
it before ended-source early-return, fence all sibling work, invalidate all owned
automatic sources, and commit a receipt. If current but already Off, explicitly
return current_already_off; if older, only stop the old source; manual Stop never
changes consent. Unknown source expected_generation=0/expected_automatic=null may
create existing bounded cancellation tombstone; any automatic expectation or
nonzero generation conflicts, never selects the current consent.

Every retained source reserves **one inline Stop receipt slot at source creation**
(max256 slots/account, max2048 serialized bytes each; embedded fixed closed data,
not a new unbounded table). First explicit Stop of that source records it, even if
source already naturally ended. Later different UUIDs on an already stopped source
return already_stopped with no new receipt; same live UUID/different command
conflicts. Source state must be ended and any currently bound consent already Off
before this no-op. Historical receipt replay returns the immutable receipt plus
current status, never replays a disable. Request IDs share one account namespace:
lookup both <=256 automatic records and <=256 inline records under account lock.
A Stop that disables current On uses its pre-reserved inline slot and **releases**
R; it does not also allocate an automatic receipt. Thus it cannot hit history
quota and all receipt recovery uses the same GET selector. StopEffect is explicit
command settlement, **never inferred from GET ended state**. Manual/old Stop cannot
consume capacity required for a new current automatic Off.

Source receipt is at most one per source lifetime and expires after24h. Retain the
"explicitly stopped" fence until source purge even after receipt payload purge;
old expired command fails lifetime rather than reallocating history. Direct
already_stopped is a correlated no-op, not recoverable permanent UUID history,
just like already_off. SourceStopResult's source/automatic_effect are the recorded results on replay;
status is current. A receipt has result.enabled false only for its *own* account
revision and cannot prove automation remains Off after a newer opt-in.

## 5. Actual pre-source preparation/claim/bind/commit handoff (F5)

These are exact proposed exports, not aliases for existing FleetFetchTicket.
Owner files: pure DTOs/cadence `A/src/core/fleet-automatic.ts`; transactions
`services/fleet-automatic.ts`; network `jobs/fleet-automatic.ts`; **I alone** extracts
shared authority commit from `services/fleet-source-observation.ts` and bounded
upstream machinery from `jobs/fleet-source.ts`. Keep current manual APIs working
against their persisted source. No caller inserts a placeholder source to get a
ticket and no caller-supplied boolean constitutes positive proof.

Internal `AccountId` and device/link IDs use ExistingUuid; internal times are Date. Internal
objects are readonly detached snapshots, not serialized tokens in outbox/audit.
`Boss = typeof character.$inferSelect` (existing row, includes token/grant fields),
`Link={characterId:ID,linkEpoch:ExistingUuid}`, `Evidence=NonNullable<ReturnType<typeof
deriveFleetEvidenceWindow>>` from current fleet freshness module.

```ts
// core/fleet-automatic.ts — closed queue and in-process types
// G fields have runtime safe-integer validation. UUIDs canonical as above.
type AutomaticTask = {
  accountId: string; characterId: number; consentGeneration: number;
  candidateGeneration: number; reservationId: string;
};
type AutomaticOutbox = AutomaticTask & {kind: "fleet-automatic"};
type AutomaticJob = AutomaticTask & {jobType: "fleet-automatic"};
type AutomaticClaim = {
  task: AutomaticTask; consentRevision: number; approverDeviceId: string;
  boss: Boss; claimGeneration: number; claimExpiresAt: Date;
};
type AutomaticToken = {
  claim: AutomaticClaim; settledTokenEnc: string; accessTokenExpiresAt: Date;
};
type AutomaticBound = {
  token: AutomaticToken; fleetId: number; linkedCharacters: readonly Link[];
  expectedAuthorityGeneration: number; membershipRetryAt: Date;
};
type AutomaticVerified = {
  evidence: Evidence; memberIds: readonly number[]; nextFetchAt: Date;
};
type AutomaticFailure = {
  outcome: "not_in_fleet" | "not_boss" | "fleet_read_invalid" |
    "identity_changed" | "service_unavailable" | "untrustworthy_evidence" |
    "timed_out" | "capacity_limited";
  nextAttemptAt: Date | null;
};
type AutomaticCommit =
  | {result:"created"|"reused";sourceId:string;sourceGeneration:number}
  | {result:"fenced"|"capacity_limited"|"authority_changed"};
// services/fleet-automatic.ts — db is Db, never a retained DbTx over HTTP
readFleetAutomatic(db: Db, call: SignedFleetCall): Promise<FleetReply<AutomaticGet>>;
controlFleetAutomatic(db: Db, call: SignedFleetCall,
  command: AutomaticCommand): Promise<FleetReply<AutomaticResult>>;
readFleetAutomaticReceipt(db: Db, call: SignedFleetCall,
  requestId: string): Promise<FleetReply<ReceiptGet>>;
// services/fleet-source.ts — changed v2 boundary; same owner, no parallel service
controlFleetSource(db: Db, call: SignedFleetCall & {
  command: SourceStart | SourceStop
}): Promise<FleetReply<SourceStartResult | SourceStopResult>>;
readFleetSourceState(db: Db, call: SignedFleetCall): Promise<FleetReply<SourcesGet>>;
reserveDueFleetAutomatic(db: Db, clock?: ()=>Date): Promise<number>;
claimFleetAutomaticDiscovery(db: Db, task: AutomaticTask,
  clock?: ()=>Date): Promise<AutomaticClaim|null>;
bindFleetAutomaticDiscovery(db: Db, token: AutomaticToken, fleetId: number,
  membershipRetryAt: Date, clock?: ()=>Date): Promise<AutomaticBound|null>;
commitFleetAutomaticDiscovery(db: Db, bound: AutomaticBound,
  verified: AutomaticVerified, clock?: ()=>Date): Promise<AutomaticCommit>;
settleFleetAutomaticDiscovery(db: Db, ticket: AutomaticClaim|AutomaticToken|AutomaticBound,
  failure: AutomaticFailure, clock?: ()=>Date): Promise<void>;
// jobs/fleet-automatic.ts
runFleetAutomaticJob(deps: FleetSourceDeps, task: AutomaticTask): Promise<void>;
```

For these proposed service exports, request DTOs retain their specified snake_case
wire keys; services return the stated DTO values; service returns the complete closed response including protocol:2; the route
validates it and adds the request-binding header, never guesses extra fields. Existing source
service internals keep camel-case domain types; the exported v2 boundary above
accepts/returns the closed wire DTOs. I owns its single explicit adapter. Routes
return an envelope once, never wrap these response DTOs a second time. Extend
FleetCode with the common dictionary and retain existing not_verified for relay
admission only; ControlError is the §1 subset, never a string-wide error type.
Optional clock is test-only; production samples `fleetDatabaseNow` **after waits**.

### Complete source creation record — actual provenance only

Explicit On/reOn validates the current signed session, device/account binding and
session ceiling/acknowledgement (C/K) before recording consent. Ongoing automation
uses current account/device/boss/ownerHash/linkEpoch authority plus the immutable
automatic consent account/generation binding; it neither stores nor requires the
initiating session. Receipt replay, session recovery and later discovery do not
change those immutable source bindings. No session-attribution field is added to
consent, source, tickets or audit; existing manual data needs no such backfill.

Complete automatic insert mapping (existing fields plus automatic consent/Stop bindings):

| Field | Exact value |
| --- | --- |
| id | prospective server UUID, already source-advisory-locked |
| accountId / deviceId | claim.task.accountId / claim.approverDeviceId |
| bossCharacterId / bossOwnerHash / bossLinkEpoch | claim.boss.id / ownerHash / fleetLinkEpoch, revalidated |
| automaticConsentAccountId / automaticConsentGeneration | claim.task.accountId / consentGeneration |
| generation / fetchGeneration | 1 / 0 |
| state / latestOutcome | active / verified |
| fleetId | bound.fleetId |
| intentCreatedAt / intentExpiresAt | post-lock now / now+60s |
| activatedAt / lastAttemptAt | now / now |
| nextFetchAt | verified.nextFetchAt with preserved provider pacing |
| fetchClaimExpiresAt / enqueueUntil | null / null |
| endedAt / terminalReason | null / null |
| retainUntil | intentExpiresAt+24h; terminal lifecycle later extends to §4 retention floor |
| stopReceipt / explicitlyStopped | null reserved inline slot / false |

No default or caller invents a missing required field. All source/proof writes stay
one guarded positive transaction; this completes the mapping, not a new discovery stage.

### Candidate storage and admission

One candidate/account/character, max256/account; unique live generation per link.
Fields (no others needed by authors): accountId, characterId, consentGeneration,
candidateGeneration, ownerHash, linkEpoch, nextAttemptAt, failureCount(0..6),
lastOutcome(null or AutomaticFailure.outcome or "verified" or "waiting_for_grant"),
reservationId(U|null), enqueueUntil(Date|null), claimReservationId(U|null), claimGeneration(G),
claimExpiresAt(Date|null), sourceId(U|null). Consent row also owns
nextReconcileAt(Date), candidateCursor(ID|null); generation/revision/approval/closed
fields are Consent above. Scheduler refreshes candidates from bounded own-account
catalogue; >256 refuses discovery, not truncates. A link or consent change replaces
the candidate binding with incremented candidateGeneration and clears reservation,
claim and source pointer, never resets a counter to recycle a task identity.
Absent/new candidate starts generation1, claimGeneration0. candidateGeneration
and claimGeneration use checked G counters; at Gmax fence that candidate and
report capacity_limited (no new reservation/claim, no counter reset). A new consent
cannot bypass an exhausted retained candidate counter. Source/fetch/authority int4
advance likewise refuses before overflow and withdraws work without reviving it.
ReservationId/enqueueUntil are both null or both present; claimReservationId/
claimExpiresAt are both null or both present, mutually exclusive with reservation.
sourceId is null or a current-binding automatic source UUID; task G generations
are positive. Consent nextReconcileAt is finite, candidateCursor null or ID.
Deletion/recreation must use a fresh
reservationId; stale queue deliveries cannot claim it. No-grant accounts are
rescanned after30s with no HTTP. Receipt/source reservations are unrelated to
queue reservations.

Scheduler, under mode -> identity -> account locks, reads current consent and
approver, current character link/owner/grant, no live matching source/claim; reserves
with random reservationId and 10s enqueueUntil and same-transaction outbox. It never
opens ESI. At most100 accounts/candidates per tick, rotate ordered due/cursor fairly.
Cleanup and active source reservation occur first. Dispatcher emits exact
AutomaticJob and singleton key
`fleet-automatic:<accountId>:<characterId>:<consentGeneration>:<candidateGeneration>:<reservationId>`.
Claim compares every task field including reservationId, due time, consent enabled,
current approver/device approval, Member/mode/key-ready, link/owner and usable grant;
rejects a still-live claim, then increments claimGeneration, sets claimExpiresAt
DB-now+30s and clears enqueueUntil. It returns **AutomaticClaim without source ID**.
Duplicate deliveries do not re-claim: move reservationId into claimReservationId
and clear reservationId; the task UUID must equal claimReservationId in every
postflight. Requeue requires new reservationId; settlement clears claimReservationId. Abandoned claim expires;
next reservation can resume with a new claim generation. Expiry never extends proof.

### Network and bind

Run with existing FleetSourceDeps, the **same** worker ESI instance, bounded shared
memory and owner AbortSignal. Existing token cache compares stored settled blob,
owner hash, link epoch and expiry; no other cache may establish authority.
15s upstream deadline covers refresh/JWK/membership/roster; preserve original
promise ownership through token CAS even after timeout. `getFreshAccessToken` is
outside lifecycle transactions; consume its settled tokenEnc only on successful
CAS, verify JWT character/owner/Fleet Read scope and finite expiry, then construct
AutomaticToken. Wrong identity/scope or expired JWT cannot become positive proof.
No access token is put into a ticket, queue or DB; job-local token is used for ESI.

Membership uses existing getCharacterFleet and cache/pacing extraction. Healthy
404 means not_in_fleet; boss-only roster403 means not_boss; 401 suspends grant;
other status/stage combinations are transient/untrustworthy, never guessed
terminal identity. A membership200 alone is not boss proof. Before roster I/O,
bind probes all live/paused activated predecessor sources for discovered fleet,
then takes **mode -> identity characters -> sorted accounts -> authority slots ->
sources -> devices -> fleet sessions -> union relay characters**, skipping unused
levels but never acquiring an earlier level later. Include candidate boss/approver
and all predecessor selectors. Reprobe before/after waiting; changed selectors throw
FleetLifecycleRetry and restart outer transaction (existing max3 retries).

Bind rechecks current consent generation AND revision/approver, candidate/claim,
claim deadline, boss ownership/hash/link/grant, stored refreshTokenEnc equals
settledTokenEnc and unexpired JWT. It captures indexed bounded linked-character
epoch snapshot (8192+1 overflow refuses, no truncation), ensures empty authority
slot if absent and captures its generation (zero when newly inserted), returns
AutomaticBound. Creating an empty fleet authority fence is permitted; creating a
source intent/authority owner is not. Membership cache boundary constrains later
membership discovery, never independently refreshed active roster proof.

### Positive commit and shared authority extraction

After validated boss-only roster200, derive Evidence with the existing strict
Date/Age/Cache-Control rules. A fresh boss must be in the roster and the retained
pre-roster linked-character snapshot (all accounts, as current source proof requires). Up to256 retained proof members, complete or refused.
Commit computes retained IDs from the *captured* links and prepares the full
selector union with their current identity locks. Under same account/lifecycle
serialization recheck all bind guards plus:
- every claim/task/consent/approver binding still current; no source Stop/Off,
  revocation, Member/mode loss, grant/token rotation or link change can be ignored;
- post-lock now < claim expiry AND token expiry AND evidence expiry;
  evidence.observedAt <= now; no cached body grants a fresh deadline;
- fleet slot generation exactly captured; existing verifiedAt strictly older
  than this observation; changed authority rejects without clearing incumbent;
- only links still at captured epoch are retained (never add newly linked rows);
  boss retained, <=256 proof members, <=16 live/256 retained account sources.

Positive commit pre-generates a prospective server UUID, includes its absent-source
advisory selector before device/session locks, and inserts only after all guards.
The UUID itself is not a source or authority. Only **then** create server UUID source with immutable account/device/boss/consent
binding and the complete field mapping above (including retainUntil), generation1, fleetId, intentCreatedAt=now, intentExpiresAt=now+60s,
activatedAt=now, active state, nextFetchAt=verified.nextFetchAt, empty fetch claim,
fetchGeneration0, reserved inline Stop slot. Commit source and proof atomically:
no visible pending placeholder or later independent activate. If matching live
automatic source appeared meanwhile, discovery returns reused WITHOUT applying
its older body or modifying that source; existing active-source claim owner alone
refreshes it. A different fleet, terminal source or manual source is never reused
or relabelled. Candidate sourceId points to the created/reused source and discovery
stops while that source is live. Natural end clears pointer on next bounded scan;
future proof uses a new UUID and never revives an ended source. Every commit
result, including reused/fenced/capacity_limited/authority_changed, releases only
the still-current candidate claim. created/reused sets sourceId; capacity waits
30s+jitter; authority_changed waits max(nextFetchAt,DB-now+5s); fenced cannot
reschedule newer candidate state. These outcomes do not require caller invention.

I extracts one transaction-only helper from existing positive commit:
`applyFleetAuthorityProof(tx:DbTx, prepared:PreparedFleetAuthority,
proof:PreparedFleetProof, now:Date):Promise<void>` in source-observation.ts.
`PreparedFleetAuthority` has exactly these keys: source (fleetSourceIntent row),
authority (fleetSourceAuthority row), boss (Boss), device (fleetDevice row), owner
(account row), mode (Awaited<ReturnType<typeof lockFleetSharingMode>>), identities
(Map<number,Boss>), locked (Awaited<ReturnType<typeof lockFleetLifecycle>>).
The automatic caller appends its newly inserted, already advisory-locked source
to locked.sources; a just-created source is valid. No separate network owner.
`PreparedFleetProof={expectedAuthorityGeneration:number,evidence:Evidence,
linkedCharacters:readonly Link[],nextFetchAt:Date}`. The helper rechecks authority
CAS/freshness and boss-retained condition; closes displaced activated sources,
withdraws only their matching authority/leases/projections, sets replacement slot
and active-source nextFetchAt once. It throws FleetLifecycleRetry on selectors
not included in prepared locks; does not run prepare or open/nest a transaction.
The helper's typed refusal is
`FleetAuthorityProofRefusal extends Error { readonly reason:
"authority_changed"|"untrustworthy_evidence" }`; these are sanitized literals.
An automatic caller maps them to authority_changed/fenced respectively and rolls
back tentative insertion before separately settling its still-current claim.
A manual caller retains existing paused/pacing semantics. A selector retry is
FleetLifecycleRetry, distinct from these proof refusals. Manual and automatic
callers both use it after their distinct consent/claim checks. Failure paths never invoke it, allocate a source, or clear another owner's
slot. A rejected positive commit rolls back new intent/proof together.

Negative/transient settlement only updates the still-current candidate claim,
releases it and chooses bounded due time. It allocates **zero source intents** and
no automatic command receipts. not_in_fleet/not_boss reset failureCount and use
30s + deterministic0..3s jitter; failures increment capped count, 30s*2^(count-1)
capped15min plus same jitter, always max with valid provider/shared pacing.
Jitter milliseconds = first unsigned big-endian32 bits of SHA256(UTF8 lines
`fleet-automatic-jitter-v2`, accountId, decimal characterId, decimal
consentGeneration, decimal claimGeneration; no final newline) modulo3001.
This is deterministic scheduling, not a crypto/authentication domain change.
Uninterpretable timing uses existing conservative probe boundary, not invented
freshness. Authorization/identity loss suspends until current grant/link state
changes. Claim-only failure cannot assert a trusted upstream terminal fact;
terminal provider outcomes need AutomaticToken and the same settled-token/expiry
postflight checks. Fenced callbacks may preserve only valid pacing on their still
current candidate, never mutate newer generation. No discovery under known shared
ESI backoff. No worker retry loop outside retained scheduler. Automatic job rejects unexpected
failures only as `fleet_automatic_job_failed`; handler validation uses
`fleet_automatic_payload_invalid`, never serializes token/provider/DB parameters.

### One runtime owner, reserved active capacity

Extend existing createFleetSourceOwner (same wrap/stopAdmission/drain signatures),
startFleetSourceScheduler, fleet dispatcher and outbox. Add queue `fleet-automatic`
with existing fleet-source short policy, retryLimit0, expiry30s, retention1min,
no cron/generic runJob/DLQ. One concurrent discovery callback **per existing worker process** (same deployment
replica count as the source owner; cross-process candidate claims remain DB-fenced); **do not replace or
share its queue head with active fleet-source callback capacity**. Both handlers
are wrapped by the same sourceOwner; one shared createFleetSourceMemory and ESI
client. Same500ms nonoverlapping scheduler tick runs cleanup -> reserve active ->
reserve discovery; fleet-source dispatcher selects both explicit fleet task kinds.
Shutdown closes admission, stops scheduler/dispatch, offWork both queues, then
awaits original owner promises before either pool closes. Real queue starvation,
clock/lock and token settlement tests remain required; the adjacent state model
does not prove pg-boss behavior.

## 6. Pre-session request/response correlation — exact, distinct from intent

The four POSTs have no fleet session and no canonical signed-session headers.
Their immutable proofs remain exactly:
- pairing completion: `UTF8("fleet-pairing-v1\n" + pairing_id)`;
- recovery initiation: UTF8 lines `fleet-recovery-init-v1`, configured canonical
  origin, request_id, issued_at, hex(SHA256(decoded canonical SPKI)); no final newline;
- recovery completion: UTF8 lines `fleet-recovery-v1`, configured origin,
  challenge_id, nonce, same key digest; no final newline.
Existing recovery nonce derivation `fleet-recovery-nonce-v1` and token encryption
are unchanged. Required richer capability approval is C's contract, not a proof
rename. Keep pairing registration's current bounded canonical-key handling.

**Each HTTP attempt**, including identical initiation retry or pairing polling,
generates a fresh Token in request header `X-Fleet-Attempt`. It is NOT an idempotency
key, not signed into existing proof domains, and is never persisted in the server
intent/challenge. Reject missing/duplicate/noncanonical header before admission.
Reject any caller X-Fleet-Request-Binding as a substitute. Successful pre-session
response supplies exactly one X-Fleet-Request-Binding equal to:

```text
hex(SHA256(UTF8(join("\n", [
  "fleet-api-v2-pre-session", configured_canonical_origin, "POST",
  literal_validated_v2_path, attempt_token, hex(SHA256(exact_raw_body_bytes))
]))))
```

No trailing newline. Client uses configured canonical origin, not Host/redirect or
response data. This is replay correlation under trusted HTTPS, **not proof of
possession or a server signature**. No clock anchor. Body digest binds actual
proof/key/intent bytes; attempt prevents an identical retry accepting a replayed
old whole response. Header is intentionally outside immutable intent/proof: TLS
protects it, a malicious relay can already fabricate correlation, and re-signing
proofs with it would change deployed crypto domains. Replacing the attempt does
not permit replay of a consumed completion; server's original one-use checks still
control issuance. Error envelopes never establish proof outcomes.

```text
PairingBegin = {protocol:2,public_key_spki_b64url:string,requested_capabilities:Capabilities}
PairingBegun = {protocol:2,pairing_id:ExistingUuid,approval_url:string,expires_at:T}
PairingComplete = {protocol:2,completion_signature:string}
PairingCompleted = {
  protocol:2,session_id:Token,
  catalogue:{revision:N,characters:{character_id:ID,character_name:string}[]}
}
RecoveryBegin = {
  protocol:2,public_key_spki_b64url:string,request_id:Token,issued_at:T,
  initiation_signature:string
}
RecoveryBegun = {protocol:2,challenge_id:ExistingUuid,request_id:Token,nonce:Token,expires_at:T}
RecoveryComplete = {protocol:2,nonce:Token,recovery_signature:string}
RecoveryCompleted =
  {protocol:2,result:"reconnected",device_id:ExistingUuid,session_id:Token,
   session_expires_at:T,approved_capabilities:Capabilities,
   participation:{enabled:bool,generation:N}}
  | {protocol:2,result:"device_revoked"|"device_key_conflict"}
  | {protocol:2,result:"account_ineligible"|"retry_later",retry_after_ms:N+}
```

applied/replayed results require non-null matching receipt; already_off/already_stopped
require null. Result request_id equals request and receipt.command.request_id;
ReceiptGet selector equals receipt.command.request_id. AutomaticReceipt.result
must have the command's desired mode, unchanged generation for Off or expected+1
for On, and revision=expected_revision+1. SourceStartResult source.source_id must match
command, source.character_id must equal command.character_id, automatic=null.
A command expected_generation=0 cannot return an automatic source. SourceStop
expected_generation is 0..Nmax-1 despite N allowing larger observed values.
SourceStopResult source and automatic_effect equal its receipt fields when nonnull;
receipt command, source UUID and immutable automatic binding must agree.
unknown_cancelled requires expectation0/null and manual ended tombstone; manual_only
requires null binding. disabled_current/current_already_off require the historical
receipt consent generation equal to the positive source binding, enabled=false;
older_generation_only requires source binding less than receipt consent generation.
The current status may be newer. Consent requires revision>=generation, generation0
iff the exact absent-consent value; positive generation has nonnull approving device
and approved_at. Positive disabled consent requires disabled_at>=approved_at and
a nonnull closed_reason; enabled consent requires both null. Dates on receipts
obey accepted_at<expires_at=accepted_at+24h; result approval/disabled times cannot
exceed accepted_at. Source pending_expires_at is null for active/ended, required
for pending, nullable for paused (activated history is not exposed); ended requires
nonnull reason, non-ended reason may be null. No caller reconstructs activation
from null expiry. status.sources each belongs to status.consent.generation and
is empty when consent Off. AutomaticBinding generation is strictly positive. No other null/result combinations are accepted.

SPKI field is unpadded base64url1..120 chars decoding to accepted Ed25519 DER;
signature exactly canonical base64url64 bytes/86 chars. approval_url existing
same-origin HTTPS/relative URL max2048 chars; preserve strict no whitespace,
backslash, credentials/foreign-origin redirects. Pairing catalogue uses current
validators of8192 characters/name200. Pairing completion retains the existing
64KiB client response budget (unlike v2 snapshot GET's64MiB); this is an admission bound,
not a guarantee8192 maximum-width names fit. Precompute the closed response size
before mint/commit; oversize returns service_unavailable without consuming the
pairing or issuing an unreadable session response. No partial catalogue. No extra capability/session keys in pairing
completion; fetch device state on new signed lane. Recovery retry_after_ms is
1..86400000 and complete outcomes only as listed. All pre-session success/error
responses no-store; success body limit64KiB for every pre-session POST.
Pre-session errors exactly `{protocol:2,error:code}`:400 bad_request/update_required
(and invalid_key on begin pairing),404 not_found (malformed completion ID),409
not_completable (pairing complete only),401 unauthorized (recovery),429 rate_limited
(recovery),503 feature_disabled/service_unavailable. No arbitrary account diagnosis
in an unproven error, and no conversion of HTTP errors into device_revoked results.

Recovery `request_id` and `issued_at` are **one immutable initiation identity**:
persist before send; retries keep them and initiation signature unchanged while
using fresh X-Fleet-Attempt. Echo request_id must match. Same issued-at and key
must match server's retained unconsumed challenge; never change timestamp to
refresh it. Once completion was attempted, response loss/malformed correlation
means unknown outcome: discard challenge and initiate with a new request_id, not
repeat completion. Proven retry_later/account_ineligible also consume it; honor
retry_after_ms, begin fresh. Recovery never returns a stored raw prior session.

Pairing begin currently has **no request-id idempotence field**; do not invent one.
Response loss leaves no known pairing_id; another begin is a new bounded pairing
request, not replay recovery of the first. Persist accepted pairing_id before
browser exposure. Completion proof for repeated pending polls is deterministic;
X-Fleet-Attempt changes on each HTTP call. Lost possibly-successful completion
must use existing registered-key recovery (not claim the old consumed pairing
will replay its session). Any still-pending approval decision stays explicit;
recovery cannot invent newly requested approvals. Browser callback
`completeFleetReadGrant` remains grant-only, as inspected in
`src/app/auth/eve/callback/route.ts`. Save automatic On first; after grant return,
the existing server due scan considers **current** consent+grant, never a stored
browser-to-desktop continuation. Off/revocation/reOn during OAuth is authoritative.

## 7. Offline proof versus required implementation gates

`automatic-control-proof.py` is an intentionally isolated bounded state and
serialization prototype. It imports no production services, touches no DB/files
at runtime and makes no network calls. It checks quota/CAS/no-op/history races,
source-generation binding, discovery fence dimensions and request-vs-attempt
correlation. It is **not** a feature/regression/security/pg-boss test and cannot
prove transactions, real routing, crypto verification or browser UX.

Future shared fixture: `tests/fixtures/fleet-automatic-v2.json` in both repos,
byte-identical; pre-session/signed binding vectors belong in C's shared v2 fixture
set, preserving existing crypto goldens. Integration owner must add actual tests
for lost responses at all writes, both lock race orders, full quota fresh Off,
no source/no grant/non-Member/sessionless behavior, current approver revoke with
zero sources, unknown/purged source, source-ended-before-Stop, two-device reOn,
JWT expiry/token rotation after lock wait, link+authority CAS, zero-intent negative
discovery and queue starvation/shutdown before this annex is implemented or
called production-safe. Cutover/doc reconciliation and independent review remain
separate gates, not hidden fields left for service/job/client authors to invent.
