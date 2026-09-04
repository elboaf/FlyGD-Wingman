# Shared fleet DPS and incoming EWAR telemetry

## Status

**Approved design for discovery/prototype only.** This document defines the
chosen architecture and the validation gate before production implementation.
It does not authorize a production change, a protocol deployment, or a CCP
policy claim.

## Summary

FlyGD Wingman will optionally share a **sparse, per-character display
snapshot** with other eligible FlyGD members in the same live EVE fleet. The
local Fleet Bar remains a local-only, stable display by default. Sharing is a
separate, persistent, default-off opt-in; after pairing, it operates
automatically whenever authGD verifies the member and fleet eligibility.

`authGD` is the authenticated relay and authorization authority. EVE fleet
membership, derived server-side through `esi-fleets.read_fleet.v1`, defines
the ephemeral sharing group. authGD stores no raw combat logs or historical
combat telemetry. It stores only current sparse rows with short expiry.

The first transport is signed HTTP snapshot publication and polling, not
WebSockets, SSE, peer-to-peer transport, or a persistent room system.

## Product boundary prerequisite

Wingman's current product constraint says "No telemetry. No account except"
Google uploads and the user's Discord webhook. This feature is a deliberate,
narrow exception: it adds an optional authGD device identity and transmits
combat-log-derived display metrics to currently verified fleet members.

Before a production implementation plan or release, `PRODUCT.md` must be
explicitly amended to authorize that exception and retain its limits: default
off, explicit pairing/consent, authenticated Member-only recipients, no raw
combat logs/history, and no gameplay automation. This specification does not
silently override the current product boundary.

## Goals

- Show authorized fleet members current per-character outgoing DPS and incoming
  `SCRAM/POINT` state.
- Automatically publish only while a paired authGD Member has active Fleet Read
  authorization and the relevant linked character is in a verified fleet.
- Keep quiet remote characters out of the shared display.
- Preserve all local telemetry semantics and keep local telemetry functional
  when authGD, ESI, or the network is unavailable.
- Avoid transmitting raw gamelog content, combat participants, local paths, or
  EVE credentials.
- Prevent impersonation, duplicate publishers, replays, and lingering stale
  data.

## Non-goals

- Replacing the local Fleet Bar, its stable roster, or its `0 dps` / `NO LOG`
  semantics.
- Fleet-wide DPS totals, rankings, historical reports, combat-log storage, or
  a general fleet-management product.
- Sharing raw combat facts, event timestamps, attacker/target names, ship
  details, source paths, process/window identifiers, or log health details.
- Treating Discord roles, Wanderer ACLs, an invite code, or a persistent
  authGD room as fleet membership.
- Gameplay automation, game-memory reads, client input, or EVE token export
  from Wingman.
- A claim that CCP permits this use. Policy confirmation is a release gate.

## Existing local telemetry contract

The local Fleet Bar is the authority for the underlying metric interpretation:

- Outgoing DPS is local outgoing damage in `(now - 10 seconds, now]`, divided
  by ten and rounded half-up.
- Incoming EWAR v1 is only local verified `SCRAM/POINT`, with event-time expiry.
  ECM/JAM remains unshipped until a real fixture proves safe detection and
  attribution.
- A local observed quiet character is `0 dps`; a local unavailable log is
  `NO LOG`. Local rows are stable and alphabetical.
- Local client/source generations, relogs, truncation, and stream gaps reset or
  baseline local metrics. They are local correctness machinery and never cross
  the network boundary.

The remote protocol sends only the completed display-level result after
`TelemetryCoordinator` serializes it. The coordinator must never perform
network I/O: its subscriber only hands the newest immutable snapshot to a
separate coalescing sharing worker.

## Eligibility and group model

### AuthGD membership

A participant is eligible only when its authGD account currently has
`account.tier == member`. authGD's `cryo` status does **not** remove this
eligibility; membership and activity status are separate authGD axes.

A participating account must also have at least one linked EVE character with
an active, valid `esi-fleets.read_fleet.v1` grant. That grant is an explicit
Fleet Read opt-in, not an addition to authGD's baseline EVE scopes. Existing
accounts must not become globally short-scoped merely because the feature was
introduced.

A Fleet Read character must be in a fleet authGD can successfully resolve.
authGD uses its encrypted server-held EVE refresh token; Wingman never receives
or forwards that token.

### Fleet as an ephemeral group

The current EVE fleet ID is the sole group key. authGD derives it from ESI and
never trusts a client-provided fleet ID. It then obtains the fleet roster and
accepts or returns a character only when the roster currently contains that
character ID.

This allows one Member account with a valid Fleet Read grant to publish every
locally observed character that both belongs to that account in authGD and is
present in the verified roster. Each participating account supplies its own
Fleet Read authorization; no account's ESI grant authorizes a different
account to read or join the shared feed.

If an account can establish eligibility for more than one current fleet through
its linked Fleet Read characters, authGD evaluates every published character
against its verified fleet rather than assuming all alts share one fleet. A
character has at most one current server-derived fleet: authGD atomically moves
that character's current row to the new fleet when its verification changes.

The read endpoint returns a flat union of rows the requester is entitled to
view. Wingman does not route or authorize by fleet ID; authGD has already
filtered the rows, and an EVE character cannot simultaneously appear in two
current fleet groups. The response therefore need not disclose a fleet ID or
render a group boundary.

### ESI validation boundary

The current ESI OpenAPI document exposes:

- `GET /characters/{character_id}/fleet`
- `GET /fleets/{fleet_id}/members`

Both require `esi-fleets.read_fleet.v1`. authGD must honour the endpoints'
cache directives and treat their cache lifetime as the normal membership
verification boundary. It must fail closed once that evidence expires: it may
not admit new writes or return rows based on an expired or failed verification.

The prototype must validate, with a consenting in-fleet non-command character,
that practical roster visibility, cache headers, and join/leave latency match
this design. The public specification alone is not evidence of operational
visibility for every fleet role.

## Pairing and device authentication

authGD's existing browser session is HTTP-only and is not a desktop API
credential. Wingman must not reuse, copy, or ask the user to paste that cookie.

Pairing creates a distinct device identity:

1. Wingman generates a signing key pair and stores its private key using Windows
   DPAPI.
2. It opens an authGD pairing page containing a one-time request. A signed-in
   Member explicitly approves that request in the browser.
3. authGD binds the device public key to the account and returns only an opaque,
   short-lived device-session identifier to Wingman.
4. Wingman signs every relay request over a canonical method, path, issued-at
   value, request revision, and body digest. authGD verifies the registered
   public key, session, clock window, and revision before acting.

The opaque session ID is not sufficient to replay a request. Revisions are
strictly increasing within one device session and are stored/checked atomically
by authGD. A new session starts a new revision sequence only after a proof by
the registered device key.

AuthGD must support explicit device listing/revocation. Revocation removes
active publisher leases and current rows belonging to that device immediately.

## Sparse snapshot protocol

### Publication

Wingman derives a sparse remote projection from its latest completed local
`FleetSnapshot`:

- Include a row only when `dps > 0` or current EWAR is non-empty.
- Include `0 dps` when current `SCRAM/POINT` is active.
- Omit quiet, no-log, unknown, and non-local characters.
- Treat every accepted publication as an atomic replacement of the publishing
  device's complete sparse projection. A row omitted from a non-empty later
  publication is withdrawn immediately, just as an empty publication withdraws
  every row owned by that device.
- Send an empty authoritative row list when the last active row ends. It is a
  normal withdrawal, not a disconnected-device signal.

Protocol v1 is conceptually:

```json
{
  "protocol": 1,
  "session_id": "opaque-short-lived-id",
  "revision": 482,
  "rows": [
    { "character_id": 123, "dps": 642, "ewar": [] },
    { "character_id": 456, "dps": 0, "ewar": ["SCRAM/POINT"] }
  ]
}
```

The signature and authentication metadata are transport headers rather than
telemetry payload fields. The wire contract accepts only the documented
properties, bounded integers, an allowlisted EWAR value, and a bounded row and
body size.

Character IDs come from an authenticated device catalogue returned by authGD.
The catalogue contains only the paired account's linked `{character_id,
character_name}` entries plus a revision. Wingman matches a locally discovered
title-derived name to exactly one catalogue entry using its documented
case-insensitive normalization; it publishes nothing for no match or an
ambiguous match. A catalogue revision change, removed link, or name mismatch
forces a refresh and leaves the character unshared until an exact match is
restored. Wingman must not resolve arbitrary names or submit a publisher-supplied
name. authGD owns the ID-to-name rendering value and independently rechecks the
link before accepting every row.

### Relay and read model

authGD validates the whole publication before atomically replacing that
device's sparse projection. Accepted state is one current row per
`character_id`, tagged with its server-derived current fleet, owning device,
server receive time, expiry, and revision. A row moved to another verified
fleet replaces its prior group membership in the same transaction. authGD does
not retain a sequence of facts or snapshots.

Readers use authenticated HTTP polling, initially at a bounded one-second
cadence with conditional responses where useful. authGD filters response rows
by the requester's verified current fleet. A response includes authGD-derived
character names and only the remote display values required by the bar:

```json
{
  "protocol": 1,
  "rows": [
    {
      "character_id": 789,
      "character_name": "Fleetmate",
      "dps": 531,
      "ewar": ["SCRAM/POINT"],
      "state": "live",
      "age_ms": 420
    }
  ]
}
```

A receiver may receive a row for one of its own character IDs. Its presentation
adapter de-duplicates by ID and prefers the directly observed local row. It
keeps remote rows separate from local facts and source lifecycles.

### Publisher leases

AuthGD grants exactly one renewable publisher lease for each `character_id`.
The current server-derived fleet is lease metadata, not part of its identity, so
a fleet transition cannot leave two live rows for one character. The lease
belongs to one authenticated device session. A competing device is refused
while that lease is live; it never wins because it happened to reconnect last.
An expired lease can be acquired only through normal authenticated publication
and current ESI eligibility checks.

## Staleness and failure behavior

- Every accepted snapshot immediately removes that device's previously active
  rows that are absent from it. A sparse-empty publication therefore removes all
  of that device's active rows immediately.
- If a publisher stops without withdrawal, authGD labels its rows `stale` after
  three seconds from server receipt and hard-removes them at ten seconds.
- EWAR is only a current local snapshot field. Neither event timestamps nor an
  EWAR timer are relayed; an interrupted publisher therefore cannot make a
  tackle warning look live beyond the receive-time lease.
- If ESI evidence expires or verification fails, authGD fails closed for new
  writes and reads. Previously accepted rows age through stale to removal.
- If the relay or network fails, Wingman's local discovery, gamelog stream,
  Fleet Metrics, local Fleet Bar, Preview, and Alerts remain unaffected. The
  sharing UI reports a concise disconnected or verifying state and reconnects
  with bounded exponential backoff and jitter.
- Remote state never renders as local `NO LOG`. It is explicitly `REMOTE`,
  `STALE`, or unavailable.

## Wingman integration

Fleet sharing is an independent runtime consumer:

- Add default-off `fleet_sharing` settings, pairing state, and explicit sharing
  status. Do not overload `fleet_bar.enabled`.
- Extend telemetry runtime predicates so sharing can receive completed local
  metric snapshots even when the local Fleet Bar, Preview, and Alerts are off.
- Keep the sharing worker platform-neutral and injectable; only DPAPI key
  storage and application wiring are Windows-specific.
- The coordinator subscriber performs one bounded, non-blocking coalescing
  handoff. The sharing worker performs all HTTP, signing, retry, and response
  parsing outside coordinator locks and dispatcher delivery.
- A remote presentation adapter merges local and remote display rows by
  character ID. It must not feed remote data back into `FleetMetrics` or local
  gamelog/source-generation state.
- The UI visibly states whether sharing is on, verifying fleet access, active,
  stale/disconnected, or refused. Local-only remains the default and the
  sharing control must make the data leaving the machine clear.

## AuthGD integration

authGD needs deliberately separate responsibilities:

- Fleet Read opt-in/grant management, without widening baseline OAuth scope
  requirements.
- Device-pairing, public-key registry, short-lived device sessions, and
  revocation.
- ESI fleet/roster client, ephemeral cache respecting upstream directives, and
  Member-tier authorization.
- Direct signed publish/read relay endpoints with strict schema validation,
  atomic lease/revision handling, and ingress rate limits.
- Expiring current snapshot records and cleanup. Per-second telemetry must not
  enter `audit_log`, `sync_run`, pg-boss jobs, or a durable event history.
- Audit records only for pair, enable/disable, grant, revoke, and access-control
  transitions. Operational metrics record counts and failure classes without
  the row payload.

The initial relay must use ordinary stateless HTTP plus Postgres. authGD has no
existing realtime fan-out or cross-instance socket coordination; a process-local
WebSocket broadcaster would split users across web machines when the service
scales. A dedicated realtime service is a future option only if measured polling
latency or load justifies it.

## Security and privacy requirements

- TLS is mandatory; neither device credentials nor telemetry travel over plain
  HTTP.
- All authorization is server-side and rechecked at the ESI cache boundary.
  Fleet ID, character identity, membership, row name, and recipient scope are
  never trusted from the Wingman payload.
- Relay request signatures bind method, destination, body hash, timestamp,
  session, and monotonic revision. Reject invalid signatures, expired sessions,
  old revisions, unknown rows, duplicates, excess data, and unsupported
  protocol majors.
- Bound publish and read cadence, body size, rows per message, and concurrent
  leases. Log failure class and opaque IDs only; never log raw bodies, tokens,
  signatures, or combat details.
- Current rows and ESI roster cache are short-lived operational state, not
  history. Expiry/deletion must be enforced server-side, not delegated to the
  client.
- Membership demotion, Fleet Read revocation, and device revocation delete or
  invalidate related current relay state as part of their authorization change.

## Compatibility and migration

- Existing Wingman installations retain local-only behavior because sharing
  defaults off. Existing local Fleet Bar settings and semantics do not change.
- Older Wingman builds have no paired device and do not publish or receive.
- Protocol uses an explicit major integer. authGD rejects unsupported major
  requests with an update-required response; clients reject incompatible major
  responses instead of guessing field semantics.
- Fields may be added only as optional, ignorable extensions within a supported
  major. Removal or changed meaning requires a new major.
- authGD migrations are generated and reviewed through its established Drizzle
  workflow; no existing EVE token or browser-session semantics are repurposed.
- The required Wingman `PRODUCT.md` exception is reviewed and accepted before a
  production implementation plan or release.

## Alternatives considered

### AuthGD WebSocket/SSE relay

A socket reduces polling overhead and can lower update latency but needs durable
cross-instance fan-out, connection lifecycle management, capacity monitoring,
and a new deployment/runtime model. authGD currently has none of these. Defer
until Option A is measured inadequate.

### Signed peer-to-peer relay

AuthGD could issue fleet eligibility tickets while Wingman clients exchange rows
directly. NAT traversal, STUN/TURN, peer IP exposure, signalling, unreliable
mesh membership, and debugging complexity outweigh the small retention benefit.
Reject for v1.

### Persistent authGD rooms or invite codes

They are not needed because current ESI fleet membership is the chosen group
boundary. They would add separate membership, consent, and revocation models
without improving the user-approved eligibility rule.

## Prototype and release gates

The first implementation work is a narrow tracer bullet, not a production
rollout:

1. **ESI feasibility:** use a consenting in-fleet non-command character in a
   non-production environment to validate fleet/roster visibility, cache
   directives, join/leave delay, no-fleet response, expired grant, and scope
   removal.
2. **Device proof:** pair a generated test device key to a test Member account;
   prove no browser cookie or EVE token reaches Wingman.
3. **Relay proof:** exercise signed publication/read with two simulated Members,
   matching and non-matching fleets, linked and unlinked character IDs, a
   partial omission from a non-empty replacement, and a sparse-empty withdrawal.
   Prove that an eligible multi-fleet reader receives only authGD's filtered
   union, never a client-routed or duplicate character row.
4. **Safety proof:** verify lease conflict refusal, revision replay refusal,
   signature rejection, membership/Fleet Read/device revocation, rate limits,
   stale-at-three-second behavior, and deletion at ten seconds.
5. **Integration proof:** ensure network delay/failure does not block the local
   telemetry coordinator or alter local DPS, EWAR, Preview, Alerts, or Fleet Bar
   behavior.
6. **Capacity proof:** measure end-to-end update latency, request rate, database
   writes, and read cost for representative multibox fleet traffic before fixing
   production polling intervals.
7. **Policy gate:** obtain a current authoritative CCP position on this specific
   real-time log-derived sharing use before any public production release.

   **Status: unverified, by explicit direction.** The user directed the
   project not to seek a new CCP ruling for this tracer, so no inquiry has
   been sent and none is planned as part of this work. Passing the ESI
   feasibility, device, safety, integration, and capacity proofs above is
   technical validation only; it does not establish CCP policy permission
   and does not change this gate's status. Unverified CCP-policy status
   blocks public production release; it does not block the isolated,
   non-public tracer implementation work in this plan.

The design becomes eligible for a production implementation plan only after the
ESI feasibility, device proof, safety proof, and policy gate have documented
results.

## Evidence consulted

- Wingman's local Fleet Bar design and implementation: `wingman/telemetry/`,
  `wingman/ui/fleetbar.py`, `wingman/ui/api.py`, and
  `docs/superpowers/specs/2026-09-03-floating-fleet-dps-ewar-bar-design.md`.
- authGD identity, token, session, and deployment model: `AGENTS.md`,
  `README.md`, `PRODUCT.md`, `src/db/schema.ts`, `src/services/session.ts`,
  `src/app/auth/`, `src/lib/esi/sso.ts`, `src/config.ts`, and `fly.toml`.
- ESI live OpenAPI metadata: <https://esi.evetech.net/meta/openapi.json>,
  consulted 2026-09-04. Authenticated endpoint behavior remains a tracer-bullet
  validation item.
