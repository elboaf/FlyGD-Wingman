# Local combat model — Phase B acceptance

**ACCEPTED and integrated locally.** Remaining model Tasks 2, 3 and 5 are complete;
previously completed core Tasks 1/4 were not recreated. This completes Session 1's
foundation/model assignment, not the relay, transport, automatic or UI feature.

## Provenance

Session 1 continued from `e7b92e1d8d70b3a0401b3bf22f6f65899f8089e2` on
`feat/fleet-v2-foundation-model` and ended at
`1e2c0f91f50238c9c9bfcc818c43cb834c16cbba`, without rebasing or replaying foundation
commits. Its clean worktree and local evidence remain preserved.

All four new commits were integrated with `cherry-pick -x` into Wingman's
`coord/fleet-v2-implementation`:

| Session 1 commit | Coordinator commit | Scope |
| --- | --- | --- |
| `fd7b48d60a78df3193a08dd86dfe6acd73d91ef2` | `9184b5f8` | Conservative tackle attribution and additive fact fields |
| `c14a3dc15a6a168e6dd649022198cc3a475d5fbd` | `f40fda79` | Existing stream field propagation |
| `b9ffa192595d9c3785b8c1d66d0c95ab4e8563b5` | `6ce96f43` | Independently expiring effects |
| `1e2c0f91f50238c9c9bfcc818c43cb834c16cbba` | `1fe366ae34017e24f5d5bfab637c0a6611bbcecc` | Complete attribution-framing correction |

The full non-document tree matches Session 1's reviewed final HEAD. Only eight
owned Python paths changed in Phase B: telemetry model/parsing/gamelogs/metrics
and their four specified test files. Shared helpers/profile/fixtures, core readers,
Alert production, transport, UI, packaging and authGD were not modified.
authGD integration remains `13a4295d5f8b9ee605c0f9a5fe956832bc1f8243`.

## Consumer handoff

- Facts append optional `observed_name`; positional prefixes remain compatible.
  The gamelog stream copies the field through its existing boundary.
- Names require conservative complete supported framing and canonical normalization.
  Unsupported or invalid attribution loses only the name, not a valid effect.
  Names describe observed log sources, not verified identities.
- Metrics uses the existing sole mutable owner and lifetime/sequence authority.
  POINT and SCRAM retain bounded named observations plus independently aged
  unknown/overflow buckets; NEUT remains unnamed. Expanded folded keys stay intact.
- Damage cannot renew effect buckets. Another retained name cannot renew an existing
  name or unknown bucket. Only evidence assigned to a bucket advances its deadline;
  equal/older evidence cannot shorten or re-identify surviving observations.
- First safe spelling survives while its key is live. Expired slots are reclaimed
  before capacity admission; new names do not evict still-live retained names.
- Snapshots compose detached immutable effects alongside independent row activity.
  Readers/republication must retain IDs, deadlines and original sample time.
- The former shared EWAR hold is removed at this planned step. Earlier core-only
  verification describes its own intermediate state, not the current model.

Complete rosters, zero/unavailable distinction, ten-second DPS/rounding, existing
victim/Alert/NPC rules and distinct damage/EWAR future-time policies remain intact.
No new transport/presentation wiring or named-effect display is implemented here;
existing tag consumers do observe the newly independent expiry semantics.

## Review and verification

Coordinator audit `a14c32fa-8156-479` returned **ACCEPT**, with no actionable blocker.
It compared the actual final correction with saved review evidence, checked current
consumers, and ran 29 correction and 37 retention/lifetime assertion invocations.
The final correction closes the prefix-harvesting finding; all 31 other parser
definitions remain unchanged by that correction. Earlier task/whole-branch approval
was not substituted for final-fix review.

The coordinator independently verified the exact four-commit chain, eight-file scope,
unchanged dependency hashes and final corrected JUnit: **13,922 passed, 13 skipped,
zero failures/errors**. Every skip requires Windows facilities; none is a missing
Node/codec prerequisite. Session 1's full run took 448.59s; its retained extra-gate
results cover Ruff, Cargo and JS smoke. Those are verified prior-run artifacts,
not a second full-suite run by the coordinator.

Fresh integrated-tree command:

```sh
TMPDIR=/tmp uv run --no-sync python -m pytest tests/test_combatprofile.py tests/test_combatprofile_packaging.py tests/test_telemetry_combat.py tests/test_telemetry_parsing.py tests/test_telemetry_gamelogs.py tests/test_telemetry_coordinator.py tests/test_fleet_metrics.py tests/test_alert*.py tests/test_fleetsharing_projection.py tests/test_fleetsharing_worker.py tests/test_fleetsharing_publication_worker.py tests/test_fleetsharing_remote_worker.py tests/test_fleetsharing_cadence.py tests/test_api_remote_fleet.py -q -rs --junitxml=.superpowers/sdd/fleet-telemetry-coordination/phase-b-integration-pytest.xml
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
```

**1,253 passed in 49.38s**, no skips. Ruff lint/format passed (469 files).
Source parity and clean status checks passed after integration; subsequent changes
are coordinator documentation only. No authGD tests or DB operations were needed
for this Wingman-only checkpoint.

## Evidence and remaining work

Session 1's complete local handoff, final reviews, RED/GREEN/mutation reports and
corrected full-suite artifacts live under `.superpowers/sdd/fleet-v2-local-model/`
in its foundation/model worktree. Coordinator focused JUnit lives at the path above.

Backend and transport lanes may consume this model and the accepted shared profile;
wire/schema/admission, automatic controls, clock-origin continuity and UI/setup still
need implementation and integration. Session 1 has no automatic authorization to
start UI work without a new ownership brief. Windows frozen/WebView2/suspend,
rendered UI, broader transaction and two-PC acceptance remain separate gates.
No push, main merge, deployment or live activation occurred at this checkpoint.
