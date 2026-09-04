# Shared Fleet Telemetry Tracer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove, in isolated test/development environments, that authGD can ESI-authorize and securely relay Wingman’s sparse per-character DPS and `SCRAM/POINT` snapshots without affecting local telemetry.

**Architecture:** authGD owns Member-tier/Fleet-Read authorization, paired device public keys, signed short-lived device sessions, server-side eligibility cache, atomic sparse snapshot replacement, global per-character leases, and current-row expiry. Wingman projects immutable local `FleetSnapshot` values through a one-slot worker handoff; it never sends raw gamelog facts or performs I/O on `TelemetryCoordinator`’s dispatcher. The tracer uses stateless signed HTTP plus Postgres, not a socket/broker, and intentionally stops before finished Wingman settings or remote Fleet Bar rendering.

**Tech Stack:** Python 3.11+, `cryptography`, Windows DPAPI, stdlib HTTP/threading, pytest, Ruff; TypeScript strict, Next.js 16 App Router, Node `crypto` Ed25519, Drizzle/Postgres 16, Zod, Vitest, MSW, Playwright only for the minimal pairing page if added.

**Spec:** `docs/superpowers/specs/2026-09-04-shared-fleet-telemetry-design.md`

## Scope and repository layout

This is a **tracer-bullet plan**, not a production rollout. It spans two
repositories because authGD is the authorization/relay service and Wingman is
the desktop publisher/receiver.

- Wingman worktree: `/mnt/c/dev/flygd-wingman/.worktrees/shared-fleet-telemetry-design`
- authGD repository: `/home/tng/workspace/authGD`

Before the first authGD write, create a new linked authGD worktree from its
current main branch (for example `../authGD-fleet-telemetry-tracer` on
`feature/fleet-telemetry-tracer`). Do not write into authGD’s primary checkout.
The existing Wingman worktree/branch is already isolated.

## Global Constraints

- Amend Wingman `PRODUCT.md` before a distributable build connects to authGD:
  the current “No telemetry. No account except” policy otherwise forbids this
  feature. The exception remains default-off, explicitly paired, Member-only,
  sparse, and display-only.
- A participant is `account.tier == member`; authGD `status == cryo` remains
  eligible.
- Fleet eligibility requires a current linked Fleet Read grant with
  `esi-fleets.read_fleet.v1`. Do not add it to baseline `EVE_SSO_SCOPES` or
  make existing accounts globally require reauthorization.
- authGD, not Wingman, derives fleet membership from ESI and filters readers.
  Wingman never submits a fleet ID or trusts a client-supplied character name.
- Use an Ed25519 device key pair. Store the private key only DPAPI-protected in
  Wingman; authGD stores only the public key and hashes opaque pairing/session
  values. Browser session cookies and EVE tokens never enter Wingman.
- A signed request binds protocol, HTTP method, exact path, device session,
  issued-at, monotonic request revision, and SHA-256 body digest. Reject stale
  revisions, invalid signatures, expired sessions, duplicate security headers,
  and clock skew outside 60 seconds.
- Every accepted publish transaction replaces that device’s complete sparse
  projection: any omitted prior row withdraws immediately, even when the new
  snapshot is non-empty. Reject an invalid batch atomically; never partially
  apply it.
- The current server-derived fleet is row/lease metadata; one EVE character ID
  has at most one current relay row and one publisher lease globally.
- Remote rows contain only character ID, authGD-rendered name, DPS,
  `SCRAM/POINT`, and server-calculated liveness. Do not transfer raw facts,
  timestamps, attacker/target text, log paths, source IDs, window/PID details,
  local log health, EVE tokens, or fleet IDs.
- `0 dps` is shared only when `SCRAM/POINT` is active. Quiet, `NO LOG`, unknown,
  and unmatched local characters produce no remote row.
- Server receive time controls liveness: `live` for the first 3 seconds,
  `stale` through 10 seconds, then hard exclusion/deletion. An accepted empty
  sparse snapshot removes rows immediately; a network loss does not.
- authGD route handlers do not call ESI. They read only unexpired
  server-materialized eligibility. Do not use pg-boss, `audit_log`, `sync_run`,
  or a durable combat-event table for one-second relay state.
- `TelemetryCoordinator.subscribe_fleet()` callbacks are dispatcher-thread
  calls. A sharing callback may only replace a latest-value slot and signal a
  worker; it must not perform HTTP, JSON encoding, crypto, DPAPI, or UI work.
- Preserve existing local Fleet Bar, Alerts, Preview, replay prevention,
  generation ordering, shutdown, and pywebview contracts. Remote rows do not
  feed `FleetMetrics`.
- Keep all authGD migrations generated via `npm run db:generate`; never hand
  edit a migration. Add new authGD tables to `src/db/tables.ts`.
- Keep all new Wingman non-method `Api` attributes underscore-prefixed. The
  tracer does not add completed Settings UI or remote Fleet Bar rendering.
- CCP’s authoritative policy answer is a public-release gate. Unit/integration
  work does not establish permission.

---

## File and responsibility map

### authGD production files

- `src/lib/esi/client.ts` — add the named Fleet Read scope and typed fleet/roster
  probe methods that preserve status and cache-directive evidence.
- `src/app/auth/eve/link/route.ts` — allow only the named `fleet-read` optional
  grant; do not widen baseline scopes.
- `src/lib/fleet-signature.ts` — pure canonical-message, digest, header parsing,
  Ed25519 verification, and timestamp validation.
- `src/services/fleet-pairing.ts` — one-time pairing state, public devices,
  hashed short-lived sessions, approval, revocation, and low-frequency audits.
- `src/services/fleet-eligibility.ts` — catalogues and read-only, expired-safe
  eligibility selection from materialized ESI evidence.
- `src/services/fleet-relay.ts` — atomic revision/rate/lease/sparse replacement,
  filtered reads, server-clock liveness, expiry, and revocation cleanup.
- `src/db/schema.ts` / `src/db/tables.ts` — relay persistence and managed table
  registration.
- `src/app/api/fleet/v1/**/route.ts` — thin signed API routes.
- `src/app/fleet/pair/[id]/page.tsx` and approval action — minimal authenticated
  browser confirmation surface for a pairing request.
- `scripts/fleet-esi-feasibility.ts` — deliberately invoked, redacted,
  non-production ESI observation tool; never an automatic scheduler.

### authGD tests

- `tests/fleet-signature.test.ts`
- `tests/fixtures/fleet-signature-v1.json` — public deterministic canonical
  request/signature vector, copied verbatim into Wingman’s matching fixture.
- `tests/fleet-pairing.test.ts`
- `tests/fleet-eligibility.test.ts`
- `tests/fleet-relay.test.ts`
- `tests/fleet-routes.test.ts`
- extend `tests/esi-client.test.ts`, `tests/auth-routes.test.ts`,
  `tests/db-schema.test.ts`, and `tests/seed-dev.test.ts` only where each
  asserted contract changes.

### Wingman production files

- `wingman/fleetsharing/model.py` — frozen, network-safe protocol/status types.
- `wingman/fleetsharing/projection.py` — pure `FleetSnapshot` plus authGD
  catalogue to sparse ID-only outbound rows.
- `wingman/fleetsharing/crypto.py` — Ed25519 key generation, canonical signing,
  and DPAPI serialization boundary.
- `wingman/fleetsharing/client.py` — bounded stdlib HTTP transport abstraction;
  no UI or coordinator dependency.
- `wingman/fleetsharing/worker.py` — one-slot handoff, serialized revisions,
  catalogue refresh, publish/read cycle, backoff, state callback, and bounded
  shutdown.
- `wingman/fleetsharing/state.py` — local non-EVE persisted device material and
  validation.
- `wingman/paths.py` — one named state-file location for fleet-sharing device
  material.
- `wingman/telemetry/coordinator.py` — add a separate sharing predicate without
  changing existing local behavior.
- `wingman/__main__.py` — construct/subscribe/stop the tracer sharing worker.
- `pyproject.toml` — explicitly package `wingman.fleetsharing`.

### Wingman tests

- `tests/test_fleetsharing_projection.py`
- `tests/test_fleetsharing_crypto.py`
- `tests/fixtures/fleet-signature-v1.json` — verbatim copy of authGD’s public
  request/signature vector, so Python verifies the exact Node contract.
- `tests/test_fleetsharing_client.py`
- `tests/test_fleetsharing_worker.py`
- `tests/test_fleetsharing_state.py`
- extend `tests/test_telemetry_coordinator.py`, `tests/test_main.py`,
  `tests/test_packaging_completeness.py`, and `tests/test_paths.py` where the
  new boundary is exercised.

### Explicit tracer exclusions

Do not add the production sharing Settings card, pairing UX inside Wingman,
remote Fleet Bar row rendering/merge, installer/release changes, WebSocket/SSE,
a broker, ESI polling scheduler, fleet totals, raw-log history, or public
service deployment. A later plan is required after the release gates below.

---

### Task 1: Record the product exception and establish safe workspaces

**Files:**
- Modify: `PRODUCT.md`
- Modify: `docs/superpowers/specs/2026-09-04-shared-fleet-telemetry-design.md`
  only if the policy inquiry outcome needs a status link
- Create in authGD worktree only: no production file yet

**Produces:** a recorded product exception that exactly bounds the tracer and a
separate clean authGD worktree.

- [ ] **Step 1: Verify the current Wingman and authGD branch/PR state**

  Run before making either write:

  ```bash
  cd /mnt/c/dev/flygd-wingman/.worktrees/shared-fleet-telemetry-design
  git status --short
  git log -3 --oneline
  cd /home/tng/workspace/authGD
  git status --short
  git log -3 --oneline
  ```

  Expected: no unrelated local work is absorbed into this tracer. If either
  checkout is dirty, stop and identify the owner before continuing.

- [ ] **Step 2: Create an isolated authGD worktree**

  From the authGD primary checkout, verify its worktree directory is ignored,
  then create a branch from current main:

  ```bash
  cd /home/tng/workspace/authGD
  git check-ignore -q .worktrees
  git worktree add .worktrees/fleet-telemetry-tracer -b feature/fleet-telemetry-tracer
  cd .worktrees/fleet-telemetry-tracer
  git status --short
  ```

  Expected: a clean linked worktree. Do not use a browser cookie, `.env`, or
  production database during setup.

- [ ] **Step 3: Amend the Wingman product boundary test-first by asserting its documented terms**

  Create `tests/test_product_contract.py`. It reads `PRODUCT.md` and requires
  all of:

  ```python
  required = (
      "Fleet sharing is optional and off by default",
      "authGD Member",
      "no raw combat logs",
      "does not automate gameplay",
  )
  assert all(text.count(phrase) == 1 for phrase in required)
  ```

  Run the new test and verify it fails before the product copy changes.

- [ ] **Step 4: Amend `PRODUCT.md` narrowly**

  Replace the absolute “No telemetry. No account except” sentence with its
  approved exception: Fleet sharing is off by default; a user must explicitly
  pair to authGD; only currently eligible authGD Members in the same
  ESI-verified fleet receive sparse DPS/current `SCRAM/POINT`; no raw gamelogs
  or history leave the machine; it remains display-only and non-automating.
  Keep the Google/Discord wording intact for unrelated features.

- [ ] **Step 5: Verify documentation contract and existing local behavior**

  Run:

  ```bash
  cd /mnt/c/dev/flygd-wingman/.worktrees/shared-fleet-telemetry-design
  uv run --no-sync python -m pytest tests/test_product_contract.py \
    tests/test_telemetry_coordinator.py tests/test_fleet_metrics.py -v
  git diff --check
  ```

  Expected: the new policy assertion and local telemetry suites pass.

- [ ] **Step 6: Record the unverified CCP-policy release gate**

  Do not send an external CCP inquiry during this tracer. Record in the spec’s
  release-gate section that the user directed the project not to seek a new
  ruling and that technical validation does not establish policy permission.
  Keep CCP-policy status `unverified`; it blocks public release only, not the
  isolated tracer work in this plan.

- [ ] **Step 7: Commit the Wingman policy artifact**

  ```bash
  git add PRODUCT.md tests/test_product_contract.py
  git add -f docs/superpowers/specs/2026-09-04-shared-fleet-telemetry-design.md
  git commit -m "docs: permit bounded fleet telemetry tracer"
  ```

---

### Task 2: Add Fleet Read scope support and an ESI feasibility probe

**Repository:** authGD worktree

**Files:**
- Modify: `src/lib/esi/client.ts`
- Modify: `src/app/auth/eve/link/route.ts`
- Create: `scripts/fleet-esi-feasibility.ts`
- Modify: `tests/esi-client.test.ts`
- Modify: `tests/auth-routes.test.ts`

**Interfaces:**

```ts
export const FLEET_READ_SCOPE = "esi-fleets.read_fleet.v1";

type FleetInfo = { fleetId: number; fleetBossId: number };
type FleetMember = { characterId: number };
type FleetProbeResponse<T> = {
  status: number;
  // Constructed only after strict successful parsing; failures raise EsiError.
  value: T;
  cacheControl: string | null;
  etag: string | null;
};
```

The probe client returns only fields required to establish group membership; it
does not store ESI raw responses, systems, ships, stations, or names.

- [ ] **Step 1: Write failing scope-grant and ESI parsing tests**

  In `tests/auth-routes.test.ts`, invoke `/auth/eve/link?grant=fleet-read` with
  an authenticated test session and assert the EVE authorize redirect includes
  `FLEET_READ_SCOPE` plus the existing configured scopes. Assert a plain link
  does not gain it.

  In `tests/esi-client.test.ts`, use MSW to test:

  ```ts
  expect(await esi.getCharacterFleet(7, "token")).toEqual({
    status: 200,
    value: { fleetId: 42, fleetBossId: 8 },
    cacheControl: "max-age=5",
    etag: '"fleet-v1"',
  });
  ```

  Add failures for malformed numeric IDs, missing cache header, 401/403, and a
  member roster whose irrelevant fields are absent but `character_id` is valid.

- [ ] **Step 2: Run the focused tests and confirm the new symbols are absent**

  ```bash
  cd /home/tng/workspace/authGD/.worktrees/fleet-telemetry-tracer
  npm test -- tests/esi-client.test.ts tests/auth-routes.test.ts
  ```

  Expected: compilation/test failures for the missing scope and fleet methods.

- [ ] **Step 3: Implement the named optional grant**

  Define `FLEET_READ_SCOPE` beside the existing optional ESI scope constants.
  Add exactly `"fleet-read": [FLEET_READ_SCOPE]` to the allowlisted `GRANTS`
  object in `src/app/auth/eve/link/route.ts`. Do not add a user-controlled scope
  parameter or modify `EVE_SSO_SCOPES`.

- [ ] **Step 4: Implement typed probe methods and cache evidence capture**

  Add `getCharacterFleet()` and `getFleetMembers()` to the existing ESI client.
  Each must use the existing authorized request/error pattern and return status,
  `Cache-Control`, and `ETag` alongside the minimal parsed value. Treat any
  malformed required field as an unusable response, never as an empty fleet.
  Keep the API responses and raw body out of logs.

- [ ] **Step 5: Add the manually invoked feasibility script**

  `scripts/fleet-esi-feasibility.ts` takes an explicitly supplied linked
  character ID, obtains a fresh token through existing server-side token logic,
  calls the two methods, and prints only:

  ```text
  character-fleet: <HTTP status>, cache-control=<value>, etag=<present|absent>
  roster: <HTTP status>, cache-control=<value>, etag=<present|absent>, members=<count>
  ```

  Validate its argument as a positive integer. Reject `SYNC_MODE=dry-run` with
  an explanation that a live isolated environment and a consenting character
  are required. Do not print token material, character/roster names, IDs, or
  raw responses.

- [ ] **Step 6: Run focused verification**

  ```bash
  npm test -- tests/esi-client.test.ts tests/auth-routes.test.ts
  npm run typecheck
  npm run format:check
  ```

  Expected: all pass. Do not execute the live script until the user supplies an
  isolated `SYNC_MODE=live` environment and a consenting test character.

- [ ] **Step 7: Commit authGD Fleet Read feasibility support**

  ```bash
  git add src/lib/esi/client.ts src/app/auth/eve/link/route.ts \
    scripts/fleet-esi-feasibility.ts tests/esi-client.test.ts tests/auth-routes.test.ts
  git commit -m "feat: probe ESI fleet read access"
  ```

---

### Task 3: Add authGD’s ephemeral relay schema and pure request signature contract

**Repository:** authGD worktree

**Files:**
- Create: `src/lib/fleet-signature.ts`
- Modify: `src/db/schema.ts`
- Modify: `src/db/tables.ts`
- Create: one Drizzle-kit-generated migration and matching metadata snapshot
  under `drizzle/` (the generator, not this plan, owns the filename)
- Create: `tests/fleet-signature.test.ts`
- Create: `tests/fixtures/fleet-signature-v1.json`
- Modify: `tests/db-schema.test.ts`
- Modify: `tests/seed-dev.test.ts`

**Interfaces:**

```ts
export type FleetAuthHeaders = {
  sessionId: string;
  issuedAt: string;
  revision: bigint;
  bodySha256: string;
  signature: string;
};

export function canonicalFleetRequest(input: {
  protocol: 1;
  method: "GET" | "POST" | "PUT";
  path: string;
  sessionId: string;
  issuedAt: string;
  revision: bigint;
  bodySha256: string;
}): Uint8Array;

export function verifyFleetRequest(
  publicKeySpki: Uint8Array,
  headers: FleetAuthHeaders,
  body: Uint8Array,
  request: { method: string; path: string; now: Date },
): "ok" | "bad_headers" | "bad_digest" | "bad_time" | "bad_signature";
```

Add tables for pairing requests, public devices, hashed device sessions,
materialized eligibility, globally keyed character leases, and current rows.
Every relay table holds only short-lived operational state and foreign keys
needed for revocation.

- [ ] **Step 1: Write failing pure signature tests**

  Generate a test Ed25519 key pair at test runtime. Assert a valid canonical
  request verifies, then table-test each mutation:

  ```ts
  const changed = { ...headers, revision: 8n };
  expect(verifyFleetRequest(pub, changed, body, req)).toBe("bad_signature");
  ```

  Cover altered method, exact path, body bytes/digest, session ID, issued-at,
  revision, duplicate security header values, malformed base64url, wrong key
  type, and timestamps at ±60 seconds/±60,001 ms.

- [ ] **Step 2: Run signature tests red**

  ```bash
  npm test -- tests/fleet-signature.test.ts
  ```

  Expected: unresolved import/module failure.

- [ ] **Step 3: Implement the canonical Ed25519 contract**

  Use Node `crypto` only. Canonical bytes are UTF-8 lines in this exact order:

  ```text
  fleet-v1
  <METHOD>
  <exact pathname>
  <session id>
  <RFC3339 issued-at>
  <base-10 revision>
  <lowercase SHA-256 hex body digest>
  ```

  Create `tests/fixtures/fleet-signature-v1.json` with the fixed public SPKI,
  protocol/method/path/session/issued-at/revision/body values, expected digest,
  exact canonical UTF-8 text, and a valid base64url Ed25519 signature. It must
  contain no private key, session usable outside tests, or real endpoint value.
  Make `tests/fleet-signature.test.ts` verify that vector in addition to
  runtime-generated mutation tests. Copy this file byte-for-byte into
  Wingman’s `tests/fixtures/` in Task 7; its Python crypto test verifies the
  same public vector.

  Require one value for each `X-Fleet-Session`, `X-Fleet-Issued-At`,
  `X-Fleet-Revision`, `X-Fleet-Body-SHA256`, and `X-Fleet-Signature` header;
  reject comma-joined/multiple values. Parse the device key only as Ed25519 SPKI
  DER and use `crypto.verify(null, canonical, key, signature)`.

- [ ] **Step 4: Write failing schema/table-registration tests**

  Assert the schema exports all six relay tables and `MANAGED_TABLES` includes
  them. Assert an inserted session stores a hash field, not a raw session ID,
  and an inserted current row has no column for log content, target/source,
  event timestamp, fleet name, system, ship, or EVE token.

- [ ] **Step 5: Implement the minimal ephemeral schema**

  Add:

  - `fleet_pairing_request`: id, public key bytes, challenge digest, expiry,
    approved/consumed timestamps, approved account/device FKs.
  - `fleet_device`: UUID, account FK, Ed25519 SPKI public key, created/revoked
    timestamps.
  - `fleet_device_session`: SHA-256 session digest primary key, device FK,
    expiry, `last_revision`, and publish/read rate timestamps.
  - `fleet_eligibility`: source linked character, account, current fleet ID,
    JSON array of only roster character IDs, verified/expires timestamps, and
    opaque outcome code.
  - `fleet_publisher_lease`: `character_id` primary key, device/session FKs,
    current fleet ID, lease expiry.
  - `fleet_telemetry_row`: `character_id` primary key, fleet ID, device/session
    FKs, DPS, EWAR string array, received/stale/hard-expiry timestamps.

  Index expiry columns and `(fleet_id, hard_expires_at)`. Add foreign-key and
  delete behavior so device/session revocation can clean dependent relay state.
  Register the tables in `src/db/tables.ts`.

- [ ] **Step 6: Generate and inspect the migration**

  ```bash
  npm run db:generate
  git diff -- drizzle src/db/schema.ts src/db/tables.ts
  ```

  Expected: one new generated migration that creates only new relay tables/types
  and indexes. Stop if it alters an existing table unexpectedly.

- [ ] **Step 7: Run focused tests green**

  ```bash
  npm test -- tests/fleet-signature.test.ts tests/db-schema.test.ts tests/seed-dev.test.ts
  npm run typecheck
  npm run format:check
  ```

- [ ] **Step 8: Commit signature and schema foundation**

  ```bash
  git add src/lib/fleet-signature.ts src/db/schema.ts src/db/tables.ts drizzle \
    tests/fleet-signature.test.ts tests/db-schema.test.ts tests/seed-dev.test.ts
  git commit -m "feat: add fleet relay security schema"
  ```

---

### Task 4: Implement authGD pairing and materialized eligibility services

**Repository:** authGD worktree

**Files:**
- Create: `src/services/fleet-pairing.ts`
- Create: `src/services/fleet-eligibility.ts`
- Create: `tests/fleet-pairing.test.ts`
- Create: `tests/fleet-eligibility.test.ts`
- Modify: `src/services/audit.ts` only to register concise pairing/revocation
  action vocabulary if its typed action formatter requires it

**Interfaces:**

```ts
export type DeviceCatalogue = {
  revision: number;
  characters: readonly { characterId: number; characterName: string }[];
};

export type Eligibility = {
  accountId: string;
  fleetIds: readonly number[];
  rosterByFleet: ReadonlyMap<number, ReadonlySet<number>>;
  expiresAt: Date;
};

export async function beginPairing(
  dbx: Dbx,
  args: { publicKeySpki: Uint8Array; now: Date },
): Promise<{ pairingId: string; approvalUrl: string }>;
export async function approvePairing(
  dbx: Dbx, pairingId: string, accountId: string, now: Date,
): Promise<void>;
export async function completePairing(
  dbx: Dbx,
  args: { pairingId: string; completionSignature: string; now: Date },
): Promise<{ sessionId: string; catalogue: DeviceCatalogue }>;
export async function readEligibleAccount(
  dbx: Dbx, accountId: string, now: Date,
): Promise<Eligibility | null>;
export async function revokeFleetDevice(
  dbx: Dbx, deviceId: string, actorAccountId: string, now: Date,
): Promise<void>;
```

Eligibility is a read-only cache in this task. Tests seed it directly; the live
probe materializes it only after Task 2’s observed behavior is accepted.

- [ ] **Step 1: Write failing pairing lifecycle tests**

  Cover pending → approved → exactly-once completed; expired/consumed requests;
  non-Member approval; invalid completion proof; 30-minute device-session
  expiry; catalogue includes only the approving account’s linked characters;
  and device revocation deletes sessions. Assert only pairing approval and
  revocation invoke audit logging.

- [ ] **Step 2: Run pairing tests red**

  ```bash
  npm test -- tests/fleet-pairing.test.ts
  ```

- [ ] **Step 3: Implement one-time pairing and hashed session issue**

  Hash opaque pairing challenge and device-session values with SHA-256, as the
  existing browser-session service does. Browser approval requires a current
  authGD account and `tier === "member"` but intentionally ignores cryo. The
  desktop complete call proves possession of the pairing-request public key,
  consumes the request in one transaction, creates the device/session, and
  returns only `sessionId` and `DeviceCatalogue`.

- [ ] **Step 4: Write failing eligibility tests**

  Seed Member active, Member cryo, Associate, Alumni, and Pending accounts;
  linked characters; and multiple short-lived eligibility rows. Assert:

  ```ts
  expect(await readEligibleAccount(db, cryoMember.id, now)).not.toBeNull();
  expect(await readEligibleAccount(db, associate.id, now)).toBeNull();
  ```

  Assert no scope, expired evidence, or a roster lacking the requested character
  fails closed. Verify a multi-fleet account produces only server-owned
  fleet-to-character sets; callers never choose a fleet ID.

- [ ] **Step 5: Implement catalogue and expired-safe eligibility reads**

  Build the catalogue only from `character.accountId`, ordered deterministically
  by ID and revisioned from a stable hash of its ID/name pairs. `readEligibleAccount`
  requires Member tier and at least one unexpired materialized Fleet Read record
  whose underlying character scopes include `FLEET_READ_SCOPE`. Return `null`
  for missing/expired/error evidence; do not return last-known state.

- [ ] **Step 6: Implement transactional device cleanup**

  `revokeFleetDevice` marks the device revoked and deletes its sessions,
  publisher leases, and current rows in one transaction. Export one narrowly
  named `revokeFleetRelayForAccount` helper for later tier/scope/character
  lifecycle hooks; do not scatter raw relay deletes across unrelated services.

- [ ] **Step 7: Run focused tests**

  ```bash
  npm test -- tests/fleet-pairing.test.ts tests/fleet-eligibility.test.ts tests/audit.test.ts
  npm run typecheck
  npm run format:check
  ```

- [ ] **Step 8: Commit services**

  ```bash
  git add src/services/fleet-pairing.ts src/services/fleet-eligibility.ts \
    src/services/audit.ts tests/fleet-pairing.test.ts tests/fleet-eligibility.test.ts
  git commit -m "feat: add fleet device eligibility services"
  ```

---

### Task 5: Implement the atomic authGD relay core

**Repository:** authGD worktree

**Files:**
- Create: `src/services/fleet-relay.ts`
- Create: `tests/fleet-relay.test.ts`

**Interfaces:**

```ts
export type PublishedRow = {
  characterId: number;
  dps: number;
  ewar: readonly ["SCRAM/POINT"] | readonly [];
};

export type RelayReadRow = PublishedRow & {
  characterName: string;
  state: "live" | "stale";
  ageMs: number;
};

export async function replaceDeviceProjection(args: {
  sessionId: string;
  revision: bigint;
  rows: readonly PublishedRow[];
  now: Date;
}): Promise<{ ok: true } | { ok: false; code: string }>;

export async function readFleetProjection(args: {
  sessionId: string;
  now: Date;
}): Promise<{ ok: true; rows: readonly RelayReadRow[] } | { ok: false; code: string }>;
```

- [ ] **Step 1: Write failing sparse replacement and lease tests**

  Seed valid devices/sessions/materialized eligibility. Assert a valid batch
  writes a row, and a later non-empty batch that omits it deletes it immediately:

  ```ts
  const common = { sessionId: session.id, now: new Date("2026-09-04T12:00:00Z") };
  await replaceDeviceProjection({ ...common, rows: [alice, bob], revision: 1n });
  await replaceDeviceProjection({ ...common, rows: [bob], revision: 2n });
  expect(await rowFor("alice")).toBeUndefined();
  ```

  Add cases for empty withdrawal, duplicate IDs within one body, no linked
  catalogue character, character absent from every eligible roster, invalid
  EWAR, negative/excessive DPS, live lease held by a different device, revision
  replay, and a lost-response retry using a higher revision.

- [ ] **Step 2: Write failing liveness and filtered-read tests**

  Use an injected `now`. Assert live at 2,999 ms, stale at 3,000 ms, and absent
  after 10,000 ms. Assert a reader receives the flat union of rows only from
  fleets in its own unexpired eligibility cache, with names joined from authGD
  `character`, no fleet ID in output, and a local account’s self row permitted
  for downstream local-preference de-duplication.

- [ ] **Step 3: Run relay tests red**

  ```bash
  npm test -- tests/fleet-relay.test.ts
  ```

- [ ] **Step 4: Implement strict validation before mutation**

  Define constants in the service: protocol `1`, maximum 32 rows, maximum 8192
  UTF-8 body bytes, `0 <= dps <= 10_000_000`, publish/read minimum interval
  500 ms, stale age 3 seconds, hard expiry 10 seconds. Validate the entire body
  and all row eligibility before acquiring any lease or changing revision. A
  malformed/oversized/duplicate request is rejected as one unit.

- [ ] **Step 5: Implement one transaction per accepted publication**

  In deterministic ascending character-ID order, lock the session then every
  target lease/current row. Confirm revision is greater than `lastRevision`,
  enforce cadence, reject another device’s unexpired lease, and compute each
  row’s server-derived current fleet from the eligibility map. Delete this
  device’s rows absent from the submitted body, upsert submitted rows, advance
  revision, and renew leases in the same transaction. Any refusal rolls back
  every mutation.

- [ ] **Step 6: Implement read and expiry cleanup**

  `readFleetProjection` re-resolves the session/device and `readEligibleAccount`
  on every call. In one transaction, delete hard-expired rows, select only rows
  whose fleet ID belongs to the requester’s current eligibility, calculate
  `ageMs` and `live`/`stale` from database/server time, and join names from
  authGD’s `character` table. Do not expose why a non-eligible requester failed
  beyond the generic API error code.

- [ ] **Step 7: Add direct cleanup and revocation tests**

  Expose `pruneExpiredFleetRelay(now)` for a future worker-owned schedule. Test
  it removes expired rows/leases even with no reader. Test device/account
  cleanup removes current state immediately and an old signed request cannot
  restore it.

- [ ] **Step 8: Run focused verification**

  ```bash
  npm test -- tests/fleet-relay.test.ts tests/fleet-eligibility.test.ts tests/fleet-pairing.test.ts
  npm run typecheck
  npm run format:check
  ```

- [ ] **Step 9: Commit relay core**

  ```bash
  git add src/services/fleet-relay.ts tests/fleet-relay.test.ts
  git commit -m "feat: add atomic fleet telemetry relay"
  ```

---

### Task 6: Expose thin authGD pairing and relay routes

**Repository:** authGD worktree

**Files:**
- Create: `src/app/api/fleet/v1/pairing-requests/route.ts`
- Create: `src/app/api/fleet/v1/pairing-requests/[id]/complete/route.ts`
- Create: `src/app/api/fleet/v1/catalogue/route.ts`
- Create: `src/app/api/fleet/v1/snapshot/route.ts`
- Create: `src/app/fleet/pair/[id]/page.tsx`
- Create: `src/app/fleet/pair/[id]/actions.ts`
- Create: `tests/fleet-routes.test.ts`

**Interfaces:**

- `POST /api/fleet/v1/pairing-requests`: accepts a bounded base64url SPKI key;
  returns `{ protocol: 1, pairing_id, approval_url, expires_at }`.
- Browser approval page: requires existing authGD browser session and Member tier;
  shows key fingerprint/expiry and one explicit approve action.
- `POST /api/fleet/v1/pairing-requests/:id/complete`: requires request-key proof;
  returns `{ protocol: 1, session_id, catalogue }` once.
- `GET /api/fleet/v1/catalogue`, `PUT /api/fleet/v1/snapshot`, and
  `GET /api/fleet/v1/snapshot`: require all signed headers and return only
  protocol-safe values.

- [ ] **Step 1: Write failing route tests**

  Build `NextRequest` cases and use real test DB services. Assert cookie-only
  access to catalogue/read/publish is refused, while a valid signed session
  succeeds. Add a pairing browser approval test proving a non-Member redirects
  or refuses and a cryo Member can approve. Assert every response contains
  `protocol: 1` on success and unsupported protocol is an explicit
  `update_required` response.

- [ ] **Step 2: Run routes red**

  ```bash
  npm test -- tests/fleet-routes.test.ts
  ```

- [ ] **Step 3: Implement strict route schemas**

  Use Zod `.strict()` objects. Snapshot input is exactly:

  ```ts
  z.object({
    protocol: z.literal(1),
    rows: z.array(z.object({
      character_id: z.number().int().positive(),
      dps: z.number().int().min(0).max(10_000_000),
      ewar: z.array(z.literal("SCRAM/POINT")).max(1),
    }).strict()).max(32),
  }).strict()
  ```

  Reject duplicate `character_id` and an EWAR array containing duplicate tags
  after schema parsing. Read exact raw UTF-8 bytes for the signed digest before
  JSON parsing. Routes delegate validation outcomes to services; they do not
  call ESI or decode browser session cookies as desktop credentials.

- [ ] **Step 4: Implement browser pairing approval**

  Follow the app’s existing `getRequestAccount()` and redirect patterns. Render
  state before the approval action: expired/consumed, waiting for Member
  approval, approved and awaiting desktop completion. Do not reveal device key
  material beyond a short derived public-key fingerprint. Approve with a server
  action that calls the pairing service transactionally.

- [ ] **Step 5: Run complete authGD verification**

  ```bash
  npm test -- tests/fleet-signature.test.ts tests/fleet-pairing.test.ts \
    tests/fleet-eligibility.test.ts tests/fleet-relay.test.ts tests/fleet-routes.test.ts \
    tests/esi-client.test.ts tests/auth-routes.test.ts
  npm run typecheck
  npm run lint
  npm run format:check
  npm run build
  ```

  If the minimal browser page is included, add/run one focused Playwright path
  for signed-in Member approval and non-Member refusal. Do not add retries.

- [ ] **Step 6: Commit authGD HTTP tracer surface**

  ```bash
  git add src/app/api/fleet src/app/fleet tests/fleet-routes.test.ts
  git commit -m "feat: expose signed fleet relay endpoints"
  ```

---

### Task 7: Add pure Wingman sparse projection, key storage, and signed client

**Repository:** Wingman worktree

**Files:**
- Create: `wingman/fleetsharing/__init__.py`
- Create: `wingman/fleetsharing/model.py`
- Create: `wingman/fleetsharing/projection.py`
- Create: `wingman/fleetsharing/crypto.py`
- Create: `wingman/fleetsharing/client.py`
- Create: `wingman/fleetsharing/state.py`
- Modify: `wingman/settings.py`
- Modify: `wingman/paths.py`
- Modify: `pyproject.toml`
- Create: `tests/test_fleetsharing_projection.py`
- Create: `tests/test_fleetsharing_crypto.py`
- Create: `tests/test_fleetsharing_client.py`
- Create: `tests/test_fleetsharing_state.py`
- Create: `tests/test_fleetsharing_settings.py`
- Create: `tests/fixtures/fleet-signature-v1.json` (verbatim authGD fixture)
- Modify: `tests/test_paths.py`
- Modify: `tests/test_packaging_completeness.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class CatalogueCharacter:
    character_id: int
    character_name: str

@dataclass(frozen=True)
class FleetCatalogue:
    revision: int
    characters: tuple[CatalogueCharacter, ...]

@dataclass(frozen=True)
class PublishRow:
    character_id: int
    dps: int
    ewar: tuple[str, ...]


def project_snapshot(snapshot: FleetSnapshot, catalogue: FleetCatalogue) -> tuple[PublishRow, ...]:
    raise NotImplementedError


def sign_request(private_key: bytes, canonical: bytes) -> str:
    raise NotImplementedError


def fleet_sharing_file() -> Path:
    raise NotImplementedError


def validated_fleet_sharing(raw: object) -> dict[str, bool]:
    raise NotImplementedError
```

- [ ] **Step 1: Write failing pure projection tests**

  Construct `FleetSnapshot`/`FleetRow` inputs. Assert the exact sparse rules:

  ```python
  assert project_snapshot(rows(dps=0, ewar=()), catalogue) == ()
  assert project_snapshot(rows(dps=0, ewar=("SCRAM/POINT",)), catalogue) == (
      PublishRow(character_id=42, dps=0, ewar=("SCRAM/POINT",)),
  )
  ```

  Cover positive DPS, `dps is None`, `NO LOG`, unknown tag, case-insensitive
  catalogue match, no match, and deliberately ambiguous normalized catalogue
  names. Assert no name, path, log detail, source ID, or timestamp appears in a
  `PublishRow`.

- [ ] **Step 2: Run projection tests red**

  ```bash
  cd /mnt/c/dev/flygd-wingman/.worktrees/shared-fleet-telemetry-design
  uv run --no-sync python -m pytest tests/test_fleetsharing_projection.py -v
  ```

- [ ] **Step 3: Implement frozen model and projection**

  Use exactly one Unicode-safe normalization helper (`strip().casefold()`) for
  local FleetRow character names and catalogue names. Build a normalized name →
  tuple mapping; publish only if it maps to exactly one catalogue character.
  Allow only `SCRAM/POINT`, omit non-current/unavailable rows, sort output by
  integer `character_id`, and preserve a `0` only when EWAR is non-empty.

- [ ] **Step 4: Write failing crypto/state/client tests**

  Test runtime-generated Ed25519 keys against known canonical bytes from Task
  3’s public test-vector document. Test DPAPI seams receive only raw private-key
  bytes and that persisted state contains the protected blob, public key, relay
  URL origin, and opaque device/session identifiers—but never an EVE token or
  authGD cookie.

  For the client, inject `urlopen` and assert the exact five signed headers,
  body SHA-256, timeout, HTTPS-only base origin, redirect refusal, and redacted
  errors. Verify authGD’s copied public vector using `cryptography` before
  testing runtime-generated keys. Test malformed/non-v1 response rejection and
  the 403/429/5xx/transport-error status classifications.

  Test the headless pairing primitives as well: create a pairing request with
  a generated SPKI key, receive an approval URL without a browser cookie, then
  complete the approved request by signing its challenge and persist only the
  returned opaque device session/catalogue.

- [ ] **Step 5: Implement crypto/state/client seams**

  Use `cryptography.hazmat.primitives.asymmetric.ed25519`. Serialize only the
  raw 32-byte private key through injected DPAPI `protect`/`unprotect`; derive
  its SPKI public key. Use a separate state file returned by
  `paths.fleet_sharing_file()`, atomic JSON writes, strict validation, and
  `0o600` file permissions following existing credential patterns.

  The HTTP client accepts an injected opener, refuses non-HTTPS origins and all
  redirects, sets a finite 5-second timeout, reads bounded bodies, and never
  includes request body/signature/session values in exception text. Expose
  headless `begin_pairing(public_key)` and `complete_pairing(pairing_id,
  challenge, private_key)` methods for tracer tests; they return only the
  approval URL and the opaque session/catalogue values. They are transport
  primitives, not a finished Wingman settings/pairing UI.

- [ ] **Step 6: Add the inert persisted sharing predicate**

  Write `tests/test_fleetsharing_settings.py` first. It must assert that a fresh
  settings document normalizes to exactly `{"enabled": False}`, malformed
  input cannot enable sharing, and an explicit `True` round-trips through
  `settings.load()`/save normalization without affecting `fleet_bar` settings.
  Run it red, then add a top-level `fleet_sharing` default and
  `validated_fleet_sharing(raw)` in `wingman/settings.py` following the existing
  top-level section validation pattern. There is deliberately no UI control in
  this tracer, so ordinary installs remain off; tests and the isolated tracer
  harness are the only activation seams.

- [ ] **Step 7: Add package/path assertions and run focused tests**

  Add `wingman.fleetsharing` to explicit setuptools packages and extend package
  completeness tests. Then run:

  ```bash
  uv run --no-sync python -m pytest tests/test_fleetsharing_projection.py \
    tests/test_fleetsharing_crypto.py tests/test_fleetsharing_client.py \
    tests/test_fleetsharing_state.py tests/test_fleetsharing_settings.py \
    tests/test_paths.py tests/test_packaging_completeness.py -v
  uv run --extra dev ruff check wingman/fleetsharing wingman/paths.py tests/test_fleetsharing_*.py
  uv run --extra dev ruff format --check wingman/fleetsharing wingman/paths.py tests/test_fleetsharing_*.py
  ```

- [ ] **Step 8: Commit pure Wingman sharing boundary**

  ```bash
  git add wingman/fleetsharing wingman/settings.py wingman/paths.py pyproject.toml \
    tests/test_fleetsharing_*.py tests/test_paths.py tests/test_packaging_completeness.py
  git commit -m "feat: add fleet sharing protocol client"
  ```

---

### Task 8: Add the non-blocking Wingman sharing worker and telemetry predicate

**Repository:** Wingman worktree

**Files:**
- Create: `wingman/fleetsharing/worker.py`
- Create: `tests/test_fleetsharing_worker.py`
- Modify: `wingman/telemetry/coordinator.py`
- Modify: `wingman/__main__.py`
- Modify: `tests/test_telemetry_coordinator.py`
- Modify: `tests/test_main.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class SharingStatus:
    state: Literal["stopped", "connecting", "active", "verifying", "refused", "error"]
    detail: str | None = None


class FleetSharingWorker:
    def submit(self, snapshot: FleetSnapshot) -> None:
        raise NotImplementedError  # non-blocking

    def start(self) -> bool:
        raise NotImplementedError

    def stop(self, timeout: float = 5.0) -> bool:
        raise NotImplementedError

    def status(self) -> SharingStatus:
        raise NotImplementedError


# coordinator constructor addition
sharing_enabled: Callable[[], bool]
```

The new exact predicates are:

```text
discovery = preview_enabled || fleet_bar_enabled || fleet_sharing_enabled
stream    = fleet_bar_enabled || fleet_sharing_enabled || (preview_enabled && alerts_enabled)
alert     = preview_enabled && alerts_enabled
```

- [ ] **Step 1: Write failing worker concurrency tests**

  Use a blocking fake client. Submit snapshot A, wait until it blocks in HTTP,
  then submit B and C. Assert `submit()` returns without waiting and the worker
  publishes only C once the fake unblocks. Record coordinator publications while
  the client remains blocked and assert their cadence continues; a sharing
  failure must not stop local DPS decay.

  Test catalogue revision refresh, no/ambiguous match withdrawal, 403 eligibility
  loss, 429 retry-after/backoff, network failure backoff, response protocol
  mismatch, and bounded shutdown while an injected request is blocked.

- [ ] **Step 2: Write failing coordinator predicate tests**

  Add the sharing dimension to the existing table tests. With only sharing true,
  assert discovery and stream start, Alert policy does not attach, Preview does
  not render, and metrics publish to the sharing subscriber. With all consumers
  false, existing stopped behavior remains unchanged.

- [ ] **Step 3: Run tests red**

  ```bash
  uv run --no-sync python -m pytest tests/test_fleetsharing_worker.py \
    tests/test_telemetry_coordinator.py tests/test_main.py -v
  ```

- [ ] **Step 4: Implement one-slot worker lifecycle**

  `submit()` swaps an immutable latest snapshot under a small lock and signals an
  event. The non-daemon worker alone performs catalogue refresh, projection,
  revision allocation, signing, publish/read calls, retry timing, and status
  callbacks. It serializes request revisions and, after an uncertain response,
  advances to a newly signed revision rather than replaying the previous signed
  message. Coalesce repeated identical sparse projections, but immediately send
  a changed/empty projection so normal omissions withdraw rows promptly.

- [ ] **Step 5: Add sharing as a coordinator consumer**

  Add `sharing_enabled` as a callable, preserving old call sites with a default
  false lambda only where tests/transitional construction require it. Rename no
  existing Fleet Bar setting or predicate. Introduce a metrics-active condition
  of `fleet_bar_enabled || fleet_sharing_enabled`, so the coordinator produces
  snapshots for the worker without requiring the Fleet Bar window.

  Subscribe after coordinator construction in `__main__.py`, use only
  `worker.submit` as the callback, and stop/unsubscribe the worker before
  coordinator teardown. Keep the worker reference private and preserve current
  auxiliary-window-before-main shutdown order.

- [ ] **Step 6: Run focused regression suites**

  ```bash
  uv run --no-sync python -m pytest tests/test_fleetsharing_worker.py \
    tests/test_telemetry_coordinator.py tests/test_fleet_metrics.py \
    tests/test_main.py tests/test_api_quit.py tests/test_fleet_bar.py -v
  uv run --extra dev ruff check .
  uv run --extra dev ruff format --check .
  ```

- [ ] **Step 7: Commit worker wiring**

  ```bash
  git add wingman/fleetsharing/worker.py wingman/telemetry/coordinator.py \
    wingman/__main__.py tests/test_fleetsharing_worker.py \
    tests/test_telemetry_coordinator.py tests/test_main.py
  git commit -m "feat: publish fleet snapshots without blocking telemetry"
  ```

---

### Task 9: Validate the cross-service tracer and record release gates

**Files:**
- Modify: `docs/superpowers/specs/2026-09-04-shared-fleet-telemetry-design.md`
- Create: `docs/history/2026-09-04-shared-fleet-telemetry-tracer-results.md`
  only after actual observations exist
- Modify: authGD tests from Tasks 4–6 and Wingman tests from Tasks 7–8 only for
  defects found during integrated proof

**Produces:** a factual go/no-go record for the later production design; not a
public release.

- [ ] **Step 1: Run authGD’s hermetic relay proof**

  Start the local test Postgres and run the fleet-focused suite:

  ```bash
  cd /home/tng/workspace/authGD/.worktrees/fleet-telemetry-tracer
  docker compose -f docker-compose.dev.yml up -d
  npm test -- tests/fleet-signature.test.ts tests/fleet-pairing.test.ts \
    tests/fleet-eligibility.test.ts tests/fleet-relay.test.ts tests/fleet-routes.test.ts
  npm run typecheck
  npm run lint
  npm run format:check
  ```

  Expected: two generated test devices prove Member/cryo access, Member-only
  filtering, linked/in-roster admission, duplicate lease refusal, revision
  replay refusal, atomic partial omission, empty withdrawal, three-second
  stale, ten-second deletion, and revocation cleanup.

- [ ] **Step 2: Run Wingman’s hermetic worker proof**

  ```bash
  cd /mnt/c/dev/flygd-wingman/.worktrees/shared-fleet-telemetry-design
  uv run --no-sync python -m pytest tests/test_fleetsharing_projection.py \
    tests/test_fleetsharing_crypto.py tests/test_fleetsharing_client.py \
    tests/test_fleetsharing_state.py tests/test_fleetsharing_worker.py \
    tests/test_telemetry_coordinator.py tests/test_fleet_metrics.py -v
  uv run --extra dev ruff check .
  uv run --extra dev ruff format --check .
  ```

  Expected: a deliberately blocked sharing transport leaves local snapshot
  publication and idle DPS decay running.

- [ ] **Step 3: Run the isolated live ESI experiment only with consent**

  On an isolated non-production deployment using a consenting current-fleet
  character that has explicitly granted Fleet Read, run the Task 2 script once
  per test condition: in fleet, after join/leave, not in fleet, expired/revoked
  Fleet Read. Record endpoint status, cache directives/ETag presence, roster
  count, timing, environment, and whether token refresh rotated. Record no IDs,
  names, raw bodies, tokens, or combat data.

- [ ] **Step 4: Decide whether the observed ESI contract supports the design**

  Stop and return to design if a non-command member cannot obtain the required
  roster, cache/join-leave delay makes 3/10-second relay semantics misleading,
  or token refresh/call cost cannot support a safe materialization cadence.
  Do not “fix” this by making relay HTTP routes call ESI synchronously.

- [ ] **Step 5: Measure representative relay cost**

  Use generated fixture rows/devices—not real combat data—to run a one-minute
  test at the intended one-second publish/read cadence. Record end-to-end
  p50/p95 latency, requests/minute, DB writes/minute, read queries/minute,
  stale transitions, and errors. Do not expose this endpoint publicly or treat
  an unmeasured local run as production capacity evidence.

- [ ] **Step 6: Record exact outcomes and open policy status**

  Write the results document with commands, environment, measured values,
  anomalies, and a gate table:

  | Gate | Result | Evidence | Decision |
  | --- | --- | --- | --- |
  | Hermetic auth/relay | pass/fail | exact test command | continue/stop |
  | Local isolation | pass/fail | exact test command | continue/stop |
  | Live ESI visibility/cache | pass/fail | redacted observation | continue/stop |
  | Capacity | pass/fail | measurement record | continue/stop |
  | CCP policy | pending/approved/refused | authoritative reference | no public release while pending |

  Update the approved design’s release-gate status with a link to this factual
  record. Do not mark the CCP gate passed without an authoritative response.

- [ ] **Step 7: Run full repository gates and inspect scope**

  ```bash
  cd /home/tng/workspace/authGD/.worktrees/fleet-telemetry-tracer
  npm test
  npm run typecheck
  npm run lint
  npm run format:check
  npm run build

  cd /mnt/c/dev/flygd-wingman/.worktrees/shared-fleet-telemetry-design
  uv run --no-sync python -m pytest tests/
  uv run --extra dev ruff check .
  uv run --extra dev ruff format --check .
  git diff --check
  ```

  Inspect both diffs for raw payload logging, EVE/browser token exposure,
  accidental Settings/Fleet Bar UI rollout, source generation leakage, unbounded
  storage, unstated rate limits, and product-policy overreach.

- [ ] **Step 8: Run project review gates and commit results**

  Run the authGD code-reviewer/polish workflow and Wingman `polish-core --fix`
  only after the tracer code is complete; inspect every fix and rerun its
  affected tests. Use `change-explainer` for each repository’s final review
  write-up. Commit results separately in each repository:

  ```bash
  # authGD: inspect the expected tracer-only paths before staging; do not absorb
  # unrelated work from the worktree.
  git status --short
  git add src tests scripts drizzle docs
  git commit -m "test: validate fleet telemetry tracer"

  # Wingman
  git add -f docs/superpowers/specs/2026-09-04-shared-fleet-telemetry-design.md \
    docs/history/2026-09-04-shared-fleet-telemetry-tracer-results.md
  git commit -m "docs: record fleet telemetry tracer gates"
  ```

---

## Spec coverage check

| Approved design requirement | Plan task(s) |
| --- | --- |
| Explicit product exception / no public release before CCP answer | 1, 9 |
| Optional Fleet Read, no global baseline scope widening | 2 |
| Server-derived ESI fleet/roster eligibility | 2, 4, 5, 9 |
| Paired public-key device identity, no cookies/tokens in Wingman | 3, 4, 6, 7 |
| Signed/revisioned requests and replay refusal | 3, 5, 6, 7, 9 |
| Sparse per-character values and no quiet remote rows | 5, 7, 8 |
| Atomic partial omission/empty withdrawal semantics | 5, 6, 9 |
| One global publisher lease per character | 5, 9 |
| Member tier permits cryo | 4, 5, 6, 9 |
| Three-second stale / ten-second removal | 5, 6, 9 |
| No raw logs/history and bounded retention | 3, 5, 6, 9 |
| Stateless HTTP rather than sockets | 5, 6 |
| Local coordinator isolation and sharing-only predicate | 7, 8, 9 |
| Versioning / compatibility / package completeness | 3, 6, 7 |
| Multi-fleet server routing with flat filtered union | 4, 5, 6, 9 |
| Tracer-only scope and capacity/ESI validation | 2, 9 |

## Preconditions for a later production plan

A subsequent plan may add finished Wingman pairing/settings UI, remote Fleet Bar
rendering, a safe ESI eligibility refresh schedule, complete relay cleanup hooks
for every authGD identity mutation, database-backed pruner scheduling, a public
deployment decision, and release/installer work only when Task 9 records all
technical gates as passing and CCP policy is affirmative. The later plan must
re-run a design review if ESI feasibility forces a different authorization model.
