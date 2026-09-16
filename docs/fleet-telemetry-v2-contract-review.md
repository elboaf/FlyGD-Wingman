## Verdict: READY — shared contract

The revised candidate closes all six accepted findings sufficiently for independent implementation. **No new Important/Critical contract defect or unresolved material interface was established.** This is contract readiness, not runtime, migration or platform certification.

Contract paths below are relative to W `.superpowers/sdd/fleet-telemetry-coordination/`.

### Findings 1–6

1. **ADDRESSED — immutable, order-preserving origins.**  
   `combat-contract-draft.md:133–148` specifies exact-coordinate isotonic insertion, immutable existing pins, atomic staging and whole-replacement refusal. This resolves the original worse-anchor inversion without repinning surviving effects.  
   Receiver protection is also closed: `combat-contract-draft.md:163–169` scopes retained offsets to origins, permits pruning only after authenticated DB advancement, derives the **71-record** cap and separates genuinely new-data recovery from old-origin non-renewal. Unlike the rejected global minimum, an old slow GET cannot indefinitely bias future origins. These protections appropriately replace—not reuse unchanged—the publication-UUID timing in `W/wingman/ui/remotefleet.py:53–74`.  
   **Further correction required:** none at contract level.

2. **ADDRESSED — measurement freshness cannot be renewed by serialization.**  
   `combat-contract-draft.md:151–156` binds `sampled_at_ms` to the original `FleetSnapshot.sampled_at_mono`, preserves aggregate values and measurement pins, and requires both original-sample admission and a final pre-HTTP check. Relay freshness remains measured from that pinned sample.  
   This addresses the actual seam: `W/wingman/fleetsharing/worker.py:281–283` currently dates submission, whereas `W/wingman/telemetry/metrics.py:525–571` supplies the genuine measurement timestamp. The contract assigns the transport change without reopening completed model work.  
   **Further correction required:** none.

3. **ADDRESSED — coherent byte budgets and Unicode ownership.**  
   `combat-contract-draft.md:102–117` freezes the Unicode-16 artifact, table-only consumers, helper/import paths and separate identity-name rules; it expressly accommodates Python 3.11/Unicode 14 rather than assuming a runtime upgrade.  
   The 512-KiB PUT and 64-MiB decoded canonical GET ceilings accommodate the declared cardinalities without truncation. Independently reconstructing the widths produced **419,900-byte actual Python PUT**, **5,739-byte GET row**, and **47,022,137-byte maximum GET envelope**; native Node serialization agreed for the checked row. The conservative 8,192 outer bound is consistent with the aggregate admission budget in `A/src/services/fleet-shared-admission.ts:35–220`, not a fabricated 256-row fleet limit.  
   **Further correction required:** only the nonblocking wording correction below.

4. **ADDRESSED — quota-safe, durable Off and exact cancellation.**  
   `automatic-control-contract.md:184–249` reserves terminal capacity with On, accepts new Off at `H=255,R=1`, gives same-CAS Off no maximum intent age, and distinguishes receipt replay from bounded already-Off observation.  
   `cutover-migration-contract.md:303–360` closes the desktop cancellation journal: attempted On remains retained; cancellation is durable; **only its exact On receipt** supplies the derived Off CAS; missing history cannot target a competing/newer On. Local terminal growth is separately reserved at `cutover-migration-contract.md:362–402`.  
   Sessionless opt-out is nondestructive: `automatic-control-contract.md:268–371` specifies own-account browser Off, explicit Origin checking, post-lock session revalidation and the same consent transaction. Revocation is not required. Browser results cannot masquerade as desktop receipts.  
   **Further correction required:** none.

5. **ADDRESSED — material control and discovery interfaces are closed.**  
   The receipt selector is a signed literal path with an empty GET body (`automatic-control-contract.md:43–69`). Closed automatic/source results, historical receipts versus current status, and request correlation are specified at `:97–181`, `:376–471` and `:747–882`. Common error/framing rules have a single authority in `common-api-contract.md:9–82`.  
   Source-free claim/token/bind/commit interfaces and positive-creation guards are specified at `automatic-control-contract.md:473–739`. They do not pretend the existing persisted-source `FleetFetchTicket` can be renamed into discovery: see `A/src/services/fleet-source-observation.ts:37–45,211–249`. The proposed shared authority extraction corresponds to the actual guarded commit at `:399–561`.  
   **Confirmed:** `A/src/db/schema.ts:894–920` has **no `initiatingSessionId`**. The candidate uses actual account/device/boss/owner/link provenance and immutable consent binding; `automatic-control-contract.md:558–590` adds no fictional session attribution.  
   **Further correction required:** none.

6. **ADDRESSED — closed/drained cutover and preservation of unknown journals.**  
   `cutover-migration-contract.md:101–173` selects an explicit close → drain → fence → schema → verify-closed → separately authorize-reopen sequence, including original callback/token-settlement ownership and the pre-session expiry barrier. That matches the destructive session/source effects of `A/src/services/fleet-sharing-mode.ts:61–109`; a flag or ordinary rolling deployment is not substituted for drain.  
   The single state4 schema and archive rules at `cutover-migration-contract.md:175–301,404–473` preserve original keys, origin, attempted revision and journal evidence while preventing archived commands from entering the v2 lane. Old Start/Stop outcomes remain unknown where the exposed DTO cannot prove original provenance. This is consistent with the limited persisted fields in `W/wingman/fleetsharing/state.py:203–323`. No consent, attempt flags or initiating-session history is invented.  
   **Further correction required:** none.

## New Important/Critical findings

**None established.**

## Minor — actionable documentation inconsistency

**Describe the non-snapshot response ceilings as changes, not existing behavior.**

- `common-api-contract.md:49–55` assigns 1-MiB ceilings to several non-snapshot operations and calls the PUT response reader “existing.”
- `combat-contract-draft.md:115` says all other response bounds remain unchanged.
- Actual W code uses **64 KiB for every response except snapshot GET**: `wingman/fleetsharing/client.py:27–29,575–588`.

The common dictionary gives an implementable authoritative limit, so this does not block implementation. **Minimal correction:** remove the incorrect “existing” description and replace the unchanged-bounds statement with an explicit reference to the common operation-specific table. Identify those non-snapshot increases as intentional v2 client/server changes.

## Unproven implementation/platform gates

These remain necessary acceptance work, **not defects in the closed handoff**:

- Real transaction/CAS, receipt-capacity, revocation and Off races; source-free token/link/authority guards; pg-boss capacity and original-promise shutdown.
- Complete state4 parsing, reserve enforcement and atomic-write failure tests.
- Actual Next action Origin/session enforcement and browser/desktop convergence.
- Cross-language Unicode helpers and packaged resources; allocation/latency at the enlarged response ceiling.
- The stated DB/elapsed-clock bounds and Windows suspend-inclusive timing or reliable resume fencing.
- Generated migration review, real held-reader/writer drain and interruption tests, current-client integration, rendering and Windows/WebView2 acceptance.

## Verification performed

- Both HEADs matched the supplied SHAs; W’s only tracked change since `67056ac9` is `docs/fleet-telemetry-coordination.md`.
- **All 12 candidate hashes matched.**
- Read the requested authority, original findings and revised documents; inspected the relevant source and proof seams.
- Ran the bounded `contract-state4-proof.py`: **passed**, including table-only consumption on **Python 3.11.15 / Unicode 14.0.0**.
- Independently checked serialization widths as reported above.

No edits, subagents, live calls, DB tests or reruns of the large proof suites. Core Tasks 1/4 remain outside redispatch scope.
