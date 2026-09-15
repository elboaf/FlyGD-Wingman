# Fleet telemetry: reliable delivery, consistent combat rows, automatic setup

Status: behavioral direction approved, including the breaking shared-fleet cutover below; detailed contract review remains pending.

Compatibility decision: the user explicitly permits v1 shared-fleet clients to
stop working. The release requires updated clients; maintaining v1 telemetry,
dual-format projections or old-client Stop behavior is no longer a requirement.
This supersedes the earlier compatibility promise, not the authorization,
consent-generation or explicit opt-in requirements. No live cutover is authorized
by this design change.

Original discovery bases inspected:
- Wingman `961507949ff3fae93b40506bcad03f8449353a6e`.
- authGD `15d346d3ee648943426172003b92199d67795e29`.

## Goal and approved behavior

Fleet telemetry should feel like one display regardless of which PC owns a
character. The user approved:

- Fix the timing path that can withdraw active DPS while fleet verification is
  still valid on the relay.
- Share incoming and outgoing DPS.
- Show incoming NEUT and POINT/SCRAM observations, including named tackle
  aggressors. Preserve multiple observed aggressors, not just the latest one.
- Hide both local and remote rows after 30 seconds without damage dealt, damage
  received, or a tracked incoming EWAR event. Keep DPS calculated over 10 seconds.
- Make fleet verification a persistent opt-in, maintained automatically across
  Wingman restarts and future fleets while an authorized owned character is boss.
- Remove normal manual Check/Refresh/Start chores. Keep explicit opt-out and
  actionable failure information.

This is a coordinated Wingman/authGD change, delivered in separable stages. It is
not a redesign of Preview or Alert behavior, fleet automation, a combat-history
service, or permission to weaken fleet membership checks.

## Evidence and current constraints

### Timing

The existing worker can convert expired cached eligibility into an empty
publication. An accepted empty replacement removes the sender's relay rows.
Refreshing the server's proof does not refresh the client's cached observation.

A deterministic exercise of the real owner loop used constant 42 DPS, a server
proof renewed every six seconds with a ten-second lifetime, and 600 ms response
latency. It produced four empty withdrawals in one minute. With 80, 200 and
400 ms responses, the same constant-DPS exercise produced none. See the companion
[evidence record](fleet-telemetry-v2-evidence.md) for the exact probe.

Live read-only observations also captured rows disappearing before their stored
expiry while damage remained inside the ten-second window and the source was
fresh. This matches the reproduced failure class; the live client did not expose
its cached eligibility at each disappearance, so the historical trace does not
prove the cause of every live gap.

Relevant ownership: `fleetsharing/worker.py`, `fleetsharing/scheduling.py`, and
`tests/test_fleetsharing_cadence.py`. All signed requests share a revision and
must remain serialized. authGD's `docs/fleet-protocol.md` forbids parallel signed
requests as a shortcut around cadence.

### Combat information

`telemetry/parsing.py` already produces incoming damage, incoming neut, and
victim-scoped tackle facts. Tackle facts retain a source string. `metrics.py`
currently reduces EWAR to a set of tags, losing aggressor attribution; its shared
EWAR activity deadline can be extended by outgoing damage. `FleetRow` already
has incoming DPS, but the shared publication contains only outgoing DPS and
`SCRAM/POINT`. NEUT is explicitly filtered out.

The local-first display merge in `ui/api.py` must keep suppressing duplicate
remote representations of verified local characters, including hidden locals.
Activity filtering must not alter collection, known-character settings, Preview,
Alerts, or publication merely because a local row is hidden.

### Verification and setup

The authGD website's point-in-time Check fleet result is an own-account diagnostic;
it neither saves a relay roster nor starts ongoing verification. A running source
already refreshes automatically. The missing product behavior is persistent
intent and recovery after terminal source events, along with understandable setup.

Existing source intents are bounded commands and terminal retry fences, not
persistent opt-in. Account ownership, character link epochs, grants, device
revocation, source generations, and current server proof are load-bearing security
boundaries. An automatic mode must use them rather than extending an expired
source's authority.

## Alternatives and recommendation

1. Patch the timing and add more instructions beside existing controls. Smallest
   immediate change, but leaves recurring setup and local/remote inconsistency.
2. **Recommended:** fix timing independently, then add one required combat format,
   one activity policy, and persistent server-owned verification intent behind a
   simpler Wingman setup flow. Preserves the current runtime owners and allows a
   staged rollout.
3. Replace the relay with a new push transport and redesign collection. Adds a
   second delivery architecture without evidence that it is needed. Out of scope.

## 1. Reliable eligibility scheduling

Treat these as distinct states:

- fresh authority permits a publication;
- local activity has genuinely ended, permitting an intentional withdrawal;
- cached authority needs renewal, requiring a fresh eligibility observation;
- authoritative revocation/Off/Stop/identity change requires immediate fencing.

Schedule eligibility with awareness of its earliest relevant expiry, actual
completion pacing, retry deadlines and competing reads. Do not let preferred
snapshot reads or rapidly changing publications indefinitely starve prerequisite
refreshes. Preserve independent publication cadence and the existing critical
Off/withdrawal priority.

An expired cached observation alone must not be treated as a fresh assertion of
inactivity. This includes partial expiry: an atomic replacement containing only
still-cached eligible rows would wrongly withdraw the other active characters.
Suspend uncertain replacements while reacquiring authority and let the relay's
current proof and normal expiry enforce visibility. Do not republish
using expired permission, prolong freshness, or reinterpret an authoritative
empty/refused response as permission to keep sending.

The regression must exercise the actual worker and scheduler with independently
renewed source proof, not a fake that grants a new ten-second lifetime on every
eligibility GET. Include sustained/changing damage, visible settings metadata,
latency, clock skew, retry/backoff, Off and true source loss.

## 2. One combat activity model

Keep three independent clocks/concepts:

1. **DPS window:** incoming and outgoing sums over the existing ten seconds.
2. **Row activity:** last accepted damage dealt, damage received, or tracked
   incoming EWAR event; visible for less than 30 seconds after that event.
3. **Observation freshness:** whether current telemetry/authorization is still
   trustworthy. Network loss is not inactivity and must not fabricate zeros.

A real low-damage event counts even if its rounded DPS is zero. Misses, ordinary
log chatter, discovery, HTTP heartbeats, repeated snapshots, and UI hydration do
not extend combat activity. Tackle counts only for its proven victim; fleet-wide
broadcast copies must not mark every reader as tackled.

An active row can therefore display 0 outgoing / 0 incoming while its 30-second
activity hold elapses. Both local and remote rows follow this rule.
Expiry removes the row, not its collection state or saved local visibility choice.
Maintain stable ordering while a row exists; reappearing local rows use established
local ordering, and remote ordering remains deterministic.

Remote transport still stales/expires under its bounded freshness policy, currently
three/ten seconds. The 30-second activity hold is not a 30-second stale-network
allowance. During healthy quiet hold, the sender publishes fresh zero-valued rows
with advancing activity age. After genuine inactivity it withdraws them.

Missing-log and connection diagnoses remain visible at the status level when no
combat rows are eligible to display. Never turn unavailable metrics into zero or
leave a permanent NO LOG combat row as the only way to report a setup failure.

## 3. EWAR observations and aggressors

Retain distinct POINT, SCRAM and NEUT observations in the combat presentation
model. For tackle, preserve each observed aggressor from the affected character's
log. An aggressor does not need an authGD account, fleet membership, SSO grant, or
Wingman installation. Do not perform a new network identity lookup to label them.

Extract the character name from known log markup where possible, rather than
passing markup, corporation/hull decoration, or a raw line to the page. If a safe
name cannot be established, retain the effect with an unknown aggressor instead
of guessing or dropping the warning. An NPC source must not be presented as a
verified player identity.

Each effect/aggressor observation has its own maximum 30-second age. Reobserving
that same source/effect renews it; unrelated damage and a different aggressor do
not. The row activity timer and individual effect timers are separate. Stop,
source/session replacement and identity invalidation clear the appropriate
observations; old queued events cannot restore them.

Gamelogs do not provide a reliable end notification. Indicators mean recently
observed effects, not proof that a module remains active. Use concise wording in
help and expiry behavior rather than inventing exact effect-ended events.

Keep names and collections bounded at parser, protocol and display boundaries.
Show a compact inline effect/name summary and make all retained names available
without truncating them irretrievably. If a retention limit is reached, preserve
the aggregate effect indication without claiming that retained names enumerate
all aggressors. These limits and exact wire fields belong in the cross-language
contract reviewed before implementation, not independent constants in each repo.

Do not change Alert firing/hold behavior as a side effect of changing the Fleet
combat model. Preserve shared parsing and victim attribution guarantees.

## 4. Extended shared combat contract

Introduce one explicitly versioned combat contract/capability, required for shared
fleet operation after cutover. Reject unsupported old requests rather than
reinterpreting them, and do not silently broaden existing device consent. The
new format carries the information necessary for:

- outgoing and incoming DPS, with unavailable distinguishable from zero;
- remaining row-activity lifetime / equivalent bounded age;
- distinct effect observations and tackle aggressor names with independent ages;
- existing non-rejuvenating publication freshness and request correlation.

Transmit only sparse current observations, not raw logs, persistent combat history,
combat target lists, OAuth credentials, or native process identities. Age must
advance across publisher sampling, request latency, relay residence and receiver
receipt. Equal metrics, repeated publication/read responses, hydration and a new
publication UUID must not restart a combat or aggressor timer.

The relay remains the authorization authority on every accepted write/read. It
validates dimensions, names, counts, ages and body sizes; it retains the current
source/session/link/participation proof for every row.

### Breaking cutover and rollout

- Deploy the new server contract and reviewed generated migrations before enabling
  the updated clients. Do not edit previously applied migrations.
- After cutover, v1 shared-fleet reads, publications and controls are unsupported.
  Reject them without admitting data or mutating consent/authority. There is no
  v1 fallback, legacy row representation or narrow projection to maintain.
- Detect an unsupported server/client contract and fail closed. Updated clients
  should explain that an update is required; old clients need not understand the
  new message or remain usable. Unrelated local Wingman tools are unaffected.
- Expanded data still requires explicit publishing approval. Old pairing, grants
  and session acknowledgement do not automatically approve richer telemetry or
  persistent automatic verification.
- Do not render pre-cutover telemetry as new-format observations or invent missing
  incoming data/activity ages. Pin how stale rows and in-flight old work are fenced
  during cutover; unsupported stored telemetry cannot be served as fresh new data.
- Preserve the signed one-request lane, attempted-revision journal, request-binding
  checks, non-rejuvenating publication identities and identity/revocation fences.
  Existing signing primitives or historical identifiers need not be renamed merely
  because they contain `v1`; API support and cryptographic scheme versions differ.
- No legacy-server/client downgrade guarantee is required. Recovery must preserve
  consent and identity safety; dropping compatibility is not permission to erase
  pairings, grants, keys or settings, or rotate token-encryption keys.
- Deployment and activation remain explicit operational steps after current-client
  integration and old-version rejection/cutover tests. No production change or
  mode enablement is an incidental side effect of installing development code.

The implementation plan must pin one authoritative wire/schema contract, test
vectors and cutover/rejection matrix before either repository implements it.

## 5. Persistent automatic verification

Separate durable desired behavior from a particular verified fleet/source.
Persistent opt-in belongs to the authGD account so multiple paired PCs do not
race to create independent automatic sources. Retain the approving account/device
attribution and its revocation boundary; revoking that device must not silently
transfer its consent to another installation. A currently authorized account can
explicitly reauthorize automatic mode from a replacement device. The existing
server worker owns bounded discovery, reconciliation, verification and cleanup;
Wingman observes it and issues user choices. Do not create a second fleet-refresh
loop per desktop.

When explicitly opted in, automatically consider current owned characters with
usable Fleet Read grants. Verify actual boss status and fleet membership before
creating/adopting current source authority. Only a fresh validated observation
permits sharing. A later fleet, boss change or transient outage can require a new
source generation; never revive a terminal command or treat saved preference as
proof of membership.

Leaving a fleet pauses that character's verification work without erasing the
account's desired automatic mode. Retry with bounded backoff. Rejoining or leading
a future fleet can resume automatically. Loss of grant/ownership/link identity,
account eligibility or device validity must fence affected authority immediately.
Return a specific recovery action when consent cannot be used, rather than retrying
an invalid credential forever. Turning automatic verification Off cancels its
future work and stops the automatic sources it owns, without stopping another
account's valid verification.

### Stop semantics for the updated contract

Each automatically managed source must retain an immutable association with its
owning automatic-verification consent and consent generation. Source generation
and consent generation are distinct: starting a future fleet must not turn an
old source command into authority over a newer opt-in.

An authorized Stop targeting an automatic source disables its owning consent
**only when that consent generation is still current**. In one serialized
transition, disable the desired automatic mode, fence queued/in-flight source
creation for that generation, and stop the automatic sources it owns. An
acknowledged Stop must not be immediately undone by reconciliation. Apply this
rule even if the targeted source naturally ended before Stop arrived, provided
its owning consent generation is still current.

The updated client must settle an explicit consent-aware Off/Stop operation.
Merely observing an ended source is not acknowledgement that automatic mode was
disabled. Keep source-generation checks for source-directed commands and current
consent-generation/revision checks for automatic-mode controls; handle conflicts
without rebasing an old opt-out onto a newer opt-in. For a source-directed Stop,
the server resolves its immutable consent binding rather than inferring it from
whichever consent is current. An unknown or purged source identifier cannot
disable current automation by association.

Older clients' local Stop-convergence behavior need not be supported. Rejecting
their unsupported protocol closes that compatibility issue without making GETs
mutate consent or weakening generation checks.

A delayed or repeated Stop bound to an older consent generation may settle that
old source under the existing source-command rules, but must not disable a newer
opt-in or stop its sources. Re-enabling automatic verification creates a new
consent generation, and an old source must never be rebound to it. Concurrent
Stop and opt-in operations must recheck these bindings in the same transaction
that changes intent, so the serialized outcome cannot be overwritten by old work.

Stopping a manually created source retains its existing source-specific behavior:
it does not disable automatic consent or stop unrelated sources. Manual and
automatic provenance must remain distinguishable throughout retention and retry.

Keep automatic verification opt-in separate from this PC's telemetry transmission
switch. A boss can maintain verification while not publishing their own metrics;
that is existing supported behavior. The ordinary participant sees no boss setup
unless verification is needed. Global sharing disable still overrides all work.

Migration does not infer persistent permission from an old pairing, Fleet Read
grant, or historical Start. Existing users receive one clear opt-in action. Once
accepted, no repeated browser grant, Refresh or Start is needed during normal use.
Do not rotate token-encryption keys, merge accounts, or broaden EVE scopes beyond
the existing read-only fleet access.

## 6. Setup and status UX

Use Settings > Fleet telemetry, not a new top-level destination.

- Participant: connect the paired account once, explicitly enable shared combat
  telemetry, then see whether sharing is ready and which fields are supported.
- Boss: enable automatic verification once; if needed, grant the existing Fleet
  Read permission through a guided continuation that automatically resumes the
  previously requested setup after successful authorization.
- Keep a single clear current status, with the next action beside it: Off,
  connecting, waiting for fleet verification, ready, reconnecting, or authorization
  required. Distinguish a saved preference from actual live readiness.
- Show a relevant participating-fleet summary when authorized; the own-character
  catalogue is not labelled or presented as the complete shared fleet roster.
- Move source UUIDs, per-stage attempt state, technical refresh and historical
  diagnostics into Troubleshooting. Do not delete their safety/recovery semantics.
- Retain a clear automatic-verification Off action and a separate local Fleet Bar
  visibility control. Leaving the page does not alter runtime intent.
- For an automatic source, label the current UI action **Turn off automatic
  verification**, making its consent-wide effect explicit. An accepted automatic
  Off/Stop must be reflected on other updated devices; late status responses must
  not overwrite a newer opt-in.

No success screen may require the user to remember an unmentioned second Start
or Refresh. Returning from authorization must honor current opt-in, binding and
page/runtime ownership, not replay a cancelled or superseded action.

## Verification and delivery order

1. Timing fix and focused regression, deployable without protocol/schema changes.
2. Combat model/activity and independently expiring aggressor tests; preserve Alert
   behavior and local-only functionality.
3. Required server/client contract, reviewed migration, old-version rejection tests, and
   two-account integration for outgoing, incoming-only, NEUT-only and named tackle.
4. Consistent local/remote row behavior and empty/error states, with actual rendered
   browser checks and separately recorded Windows/WebView2 smoke.
5. Persistent automatic intent, worker reconciliation and simplified onboarding,
   including multiple devices, restart, later fleets, boss handover and opt-out.
6. Server-first controlled rollout and live two-PC acceptance. Do not use production
   credentials/data in fixtures or turn live sharing on as a test side effect.

Acceptance must include delayed responses and metadata competition during combat,
30-second quiet holds with zero DPS, multiple aggressors with independent expiry,
low damage that rounds to zero, unknown attacker names, fleet-wide tackle copies,
missing logs, disconnects, stale/replayed responses, late messages after Off,
identity changes, revoked grants, unsupported old clients, cutover fencing, and a
source owned by another player.

Stop acceptance additionally covers: an updated client disabling automatic mode;
Stop racing with queued/in-flight reconciliation; a source ending naturally before
its Stop arrives; repeated Stop after a new opt-in; delayed Stop from an older
consent generation; multiple automatic sources/paired devices sharing one consent;
unknown or purged source identifiers; and manual-source Stop leaving automatic
consent and unrelated sources unchanged. Assert the persisted consent, resulting
source authority, worker admission and cross-device status, not only the command
response.

## Discovery verification and review boundary

The new Wingman design worktree ran the focused baseline covering cadence, remote
worker/projection/store, metrics and bridge display: **272 passed in 17.20s**.
This is a baseline, not verification of unimplemented changes. No full suite,
new feature tests, authGD migration, deployment or Windows change acceptance has
been performed for this design.

Review this design before implementation planning, particularly persistent
account-level opt-in, extended telemetry consent and required-client cutover, independent
aggressor expiry, and the distinction between 30-second activity and transport
freshness. Exact DTO fields, retention/body limits, migrations and file-level
steps will be specified in the implementation plan and contract review.
