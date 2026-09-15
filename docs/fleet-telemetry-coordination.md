# Fleet telemetry remaining-work coordination

Status: parallel discovery and contract planning. No remaining-feature implementation has started.

## Authority and bases

- Approved behavior: [fleet-telemetry-v2-design.md](fleet-telemetry-v2-design.md), sections 2–6, with the user's subsequent approval to drop v1 shared-fleet compatibility. Consent-generation safety remains required.
- Timing work is complete and merged: Wingman PR #246, merge `62e1645cf9f49f11ea9af83ffe4ad619a9de5bdf`. Do not amend or reimplement that PR.
- Wingman integration base: `62e1645cf9f49f11ea9af83ffe4ad619a9de5bdf`.
- authGD integration base: `a9bfb49cc0424c1d6156ec905ef94b94cb119e16`.
- Wingman coordinator: `/mnt/c/dev/flygd-wingman/.worktrees/fleet-telemetry-coordination`, branch `coord/fleet-telemetry-v2`.
- authGD coordinator: `/home/tng/workspace/authGD/.claude/worktrees/fleet-telemetry-coordination`, branch `coord/fleet-telemetry-v2`.

Both integration worktrees start from fetched upstream main. Primary checkouts,
other worktrees, and the old merged timing branch are left untouched.

## Approved remaining scope

- Incoming and outgoing DPS, still calculated over ten seconds.
- Local and remote combat rows hide after thirty seconds without accepted damage
  dealt/received or tracked incoming EWAR, without prolonging transport freshness.
- NEUT indication and distinct POINT/SCRAM observations; retain multiple named
  tackle aggressors with independent expiry. Named NEUT aggressors are not an
  additional requirement.
- Persistent explicit automatic-verification opt-in across restarts and future
  fleets involving current owned, authorized boss characters.
- Simplified setup with automatic continuation/recovery, explicit Off and useful
  readiness/failure status rather than normal manual Check/Refresh/Start chores.
- Stopping an automatic source disables its current owning consent generation;
  delayed/repeated old Stops cannot disable a newer opt-in; manual Stop semantics
  remain source-specific.
- One required new shared-fleet contract. The user permits v1 clients to stop
  working: no v1 fallback, dual row shapes, legacy projections or old-client Stop
  guarantee. Replace mixed-version success testing with old-request rejection and
  cutover fencing tests. This resolves the previous legacy Stop decision gate.
- Explicit extended-data and automatic consent remain required. No inference of
  automatic permission from historical pairing, grants or manual Starts. Preserve
  identities/credentials during upgrade; no automatic grant/key/settings erasure.

## Parallelization policy

The coordinator owns requirements, contracts, integration, reviews and status.
Implementation agents will each receive a separate linked worktree/branch and a
bounded file/interface ownership brief. The user's request authorizes parallel
implementation where those worktrees and interfaces isolate the work; it does not
authorize concurrent edits to a shared checkout.

Serialize the parts whose disagreements create cross-repository breakage:

1. Freeze one required shared combat/cutover contract and one automatic-consent
   contract, with cross-language fixtures and independent review.
2. Give authGD schema/migration generation a single owner. Do not let parallel
   lanes generate migrations from competing schema snapshots.
3. Give shared bridge/admission files a named integration owner. Lane agents must
   not independently invent overlapping fields, handlers or consent semantics.
4. Integrate only reviewed commits into the coordinator worktrees. Resolve shared
   wiring there through a scoped implementer and review, not unreviewed manual
   changes by the coordinator.
5. Isolate authGD test databases and service ports before parallel integration
   tests. Until isolation is verified, serialize database/e2e runs; pure/unit and
   Wingman tests can proceed independently.
6. Run full cross-repository, current-contract and old-version rejection gates on the integrated result,
   not only green lane branches. Keep Windows and live two-PC acceptance distinct.

No lane may push, merge a shared branch, deploy, change production consent/data,
access real secrets, rotate token keys, or weaken authorization. Those actions
remain coordinator/user decisions after review.

## Initial concurrent planning passes

| Pass | Deliverable | Principal repository surface | Status |
| --- | --- | --- | --- |
| C — shared contract | Required combat/age contract, schema needs, rejection/cutover matrix | Both protocol/transport layers and authGD relay/schema | Simplification running: `4198e20d-d47c-499` |
| A — automatic verification | Persistent consent/source lifecycle, current-client Off/Stop, worker/recovery and test ownership | authGD lifecycle/jobs/routes; Wingman control boundary | Decision unblocked; plan running: `8ade9390-ecf1-40d` |
| M — client combat model | Local activity and independent EWAR attribution model, preserved Alert behavior, snapshot/projection interfaces | Wingman telemetry and consumers | Existing draft revised by C's draft owner to remove wire-compatibility obligations |
| U — presentation/setup | UI/bridge ownership and minimal setup flow, empty/stale/update-required states and UI checks | Wingman Fleet Bar/settings and authGD setup pages | Initial proposal retained as evidence; its legacy-UI promises are superseded |

These passes inspect and propose only. They do not independently implement new
wire fields, consent storage or production behavior. Their proposals will be
reconciled into reviewed contracts and executable lane plans.

## Intended implementation lanes after contracts are pinned

| Lane | Independent deliverable | Dependencies |
| --- | --- | --- |
| Shared contract/schema foundation | Version/capability fixtures, DTO definitions and additive generated schema | C + A + M decisions and contract review |
| Client combat model | Ten-second directional metrics; thirty-second activity; independent effect/attacker observations | Domain model contract |
| Relay extended combat | Validated current-format publications/reads, age propagation and unsupported-request rejection | Shared contract/schema foundation |
| Client shared transport | Required-version checks, projection/receipt aging and consent-safe state upgrade/recovery | Shared contract + client combat interfaces |
| Server automatic verification | Durable desired mode, bounded server reconciliation, generation-safe Off/Stop | Consent/schema foundation |
| Presentation/setup | Consistent rows, indicators/names, guided continuation and diagnostics | Stable payload/control interfaces; runtime integration at final gate |

Discovery may refine exact file ownership, but it must not silently broaden the
approved behavior or discard a requested feature. New material security, consent,
compatibility or irreversible-data decisions are surfaced before implementation.

## Coordinator checkpoints

- [x] Verify #246 merged and fetch both upstream bases.
- [x] Create fresh coordinator integration worktrees.
- [ ] Collect C/A/M/U proposals and resolve interface/file conflicts.
- [ ] Independently review shared contracts and migration/consent boundaries.
- [ ] Write executable lane plans and allocate implementation worktrees.
- [ ] Execute independent lanes in parallel with per-lane red/green and review.
- [ ] Integrate and run combined protocol/lifecycle/UI gates.
- [ ] Run polish, independent review and requested CodeRabbit/PR workflow.
- [ ] Obtain any required deployment/live-acceptance authorization separately.

## Verification status

This coordination setup verified upstream SHAs, worktree isolation and repository
instructions. Wingman `uv sync --locked --extra dev` succeeded. Fresh baseline:

```sh
uv run --no-sync python -m pytest tests/test_fleet_metrics.py tests/test_telemetry_parsing.py tests/test_fleetsharing_protocol.py tests/test_fleetsharing_cadence.py tests/test_api_remote_fleet.py -q
```

Result: **266 passed in 17.40s**. These are unchanged-baseline tests, not proof of
remaining features. Full new-feature/native acceptance has not run.

authGD `npm ci` succeeded without source/lock changes. Local Vitest 4.1.11 and
tsx 4.23.12 execute under Node 26.5.0. No database/e2e suite has been started;
its worktree-hashed databases and service ports must be assigned deliberately.

Dependency setup reported seven existing advisories. A production-only audit
reported Next (critical) and sharp (high). These are inherited baseline advisories,
not established exploitation of this deployment. Keep dependency remediation
separate from feature branches; no automatic `npm audit fix` or upgrades were run.
Review these before deployment. The audit artifact is retained locally.

## Discovery handoffs and open contract checks

Full proposal artifacts are in this plan's ignored workspace:
`.superpowers/sdd/fleet-telemetry-coordination/` (`combat-contract-proposal.md`,
`automatic-proposal.md`, `model-proposal.md`, `ui-proposal.md`). Consolidated
`combat-contract-draft.md` and `model-plan-draft.md` are being simplified for the
approved breaking cutover; `automatic-plan-draft.md` is being prepared in parallel.
Original reports/probes remain historical discovery evidence. Their v1 support,
legacy Stop promise, downgrade support and mixed-version success requirements are
superseded by the updated master design. Drafts are not frozen interfaces.

Confirmed coordination constraints:

- Current v1 response keys/capability arrays are closed. The new required boundary
  must cover device/pairing/recovery, controls and snapshots; unsupported old
  requests must not gain authority or expanded consent. There is no obligation to
  project new data or capability arrays into old response shapes.
- Preserve existing Alert `source` strings; their decoration affects NPC filtering.
  Fleet labels need a separate safe field, not source normalization.
- Keep complete local roster snapshots for visibility settings and duplicate
  suppression. Filter combat display/publication later.
- The existing E2E certificate pins an older Wingman commit; integration must
  deliberately update/add a current-contract gate and pinned old-client rejection
  fixture, not bypass the pin.
- Confirmed by source trace: the old desktop retires Stop on an ended-source GET,
  reporting acknowledged without necessarily sending a Stop. A natural end also
  advances source generation, so a sent old-generation Stop conflicts before the
  proposed consent handler. The server cannot honor an intent it never receives.
  This exposed a conflict in the previous old-client/natural-end promise, now
  superseded by the approved breaking cutover. The probe reproduced both paths: zero Stop
  requests when the preflight observation is already ended; one conflicting Stop
  and no rebased retry when natural end races the POST. Both locally acknowledge
  and clear the durable pending command. The isolated probe exited 0; it did not
  implement automation or contact a live service.
  User decision: v1 support is unnecessary and old clients may stop working.
  No old-client workaround is required. Updated clients must settle explicit
  consent-aware Off/Stop; keep generation checks and read-only GETs.
- Contract reconciliation recommends independently aged named/unnamed observations,
  pinned timing origins surviving sharing-session/owner replacement, and binding
  telemetry data to its publication identity. Separate optional format-negotiation
  machinery is no longer required for v1 compatibility; choose the minimal single
  required-version boundary during the revised contract review.
- Durable explicit automatic mode before a grant is sufficient for continuation:
  the existing grant-only callback may save authorization, while reconciliation
  observes current consent. No separate callback-driven consent activation or
  continuation ledger is justified by the inspected flow.

Do not let these shared-contract checks block unrelated preparation, but do not
start implementations that would bake their unresolved assumptions into source.
