# Shared combat profile — accepted dependency checkpoint

Phase A is accepted. Session 1 may proceed with remaining local-model Tasks 2,
3 and the effect work in Task 5. Core Tasks 1/4 remain complete. This checkpoint
covers profile/name helpers and fixtures, **not** wire DTO/codec implementation,
relay schema, automatic verification or deployment readiness.

## Provenance and integration

Both integration worktrees now use fresh `coord/fleet-v2-implementation` branches.
The branch from merged PR #248 was preserved, not amended.

| Repository | Exact base | Session 1 commits, in order | Coordinator cherry-picks, in order |
| --- | --- | --- | --- |
| Wingman | `0fb54df362d1b10c17adee010a0998c016366059` | `d187438967d3b95acff4c45b2f89840e613ec85d`, `e7b92e1d8d70b3a0401b3bf22f6f65899f8089e2` | `cac8afce`, `e943f3aef7473396164fc9e78d8a35e258879570` |
| authGD | `123a4d2547e2a93fefd1044645fedff1ad581b8b` | `5850afa399099197a11fd9d50910b389a47b9721`, `08139fba7ff7e1c30dc8ebb7e242178587e02a13` | `29d4658`, `13a4295d5f8b9ee605c0f9a5fe956832bc1f8243` |

Each pair was integrated with `cherry-pick -x`; complete trees matched the respective
Session 1 HEAD before this documentation checkpoint. Session 1's original branches
remain clean and unchanged. Continue Phase B from its existing Wingman HEAD, without
replaying the foundation or rebasing onto the coordinator's equivalent commits.
Other lanes should consume one lineage, never both equivalent commit pairs.

## Accepted interface ruling

The producer normalizes first, then keys the canonical name. Python
`observed_name_key` and TypeScript `observedNameKey` return `None`/`null` for invalid
or noncanonical inputs. Valid names produce frozen full-default casefold plus frozen
NFC keys. Expanded keys are not display names: do not truncate them or reapply
display-name limits. Invalid attribution must not erase otherwise valid effects.

The two implementations consume the same immutable profile; host Unicode fallback
is forbidden. Narrow attributes, formatting exclusion and resource packaging are
part of this dependency, including the follow-up test isolation fixes.

Profile SHA-256:
`036582f29ec5b427cd50397a5504fa4c9a3145e35d15118a64c4eb2f26700868`

Shared 149-vector fixture SHA-256:
`d9ccb14c6142bf66afd9f49e1c859b73834cbdbb88be002fbe1e052115725b7c`

## Verification and review

Session 1's retained handoff records 13,627 Wingman passes / 13 Windows-only skips,
222 focused authGD passes, wheel installation/vector checks, exhaustive scalar and
sequence evidence, and independent review/polish closure. The coordinator parsed
its JUnit independently: 13,640 cases, zero failures/errors and 13 skips; checked
both clean commit chains and all cross-repository profile/fixture hashes.

Coordinator audit `def1100e-66e3-4fb` returned **ACCEPT**, no blocking issues. It
checked actual final follow-up diffs against review closure, including Git environment
isolation and profile file mode—not only the earlier newline fix. No scope leaked
into telemetry, transport, schema, services, routes or UI.

Fresh checks on the integrated source trees:

```sh
# Wingman coordination worktree
TMPDIR=/tmp uv run --no-sync python -m pytest tests/test_combatprofile.py tests/test_combatprofile_packaging.py tests/test_telemetry_combat.py tests/test_fleet_metrics.py tests/test_telemetry_coordinator.py tests/test_telemetry_parsing.py tests/test_telemetry_gamelogs.py -q
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .

# authGD coordination worktree
TEST_DATABASE_URL=postgres://authgd:authgd@127.0.0.1:1/authgd_foundation_test TMPDIR=/tmp npm test -- tests/fleet-combat-profile.test.ts tests/fleet-freshness.test.ts tests/fleet-signature.test.ts
npm run typecheck
node_modules/.bin/eslint src/core/fleet-combat-profile.ts tests/fleet-combat-profile.test.ts
npm run format:check
```

Results: Wingman **480 passed in 12.68s**, Ruff lint/format passed (469 files).
authGD **222 passed in 4.29s**, typecheck/ESLint/Prettier passed. The existing Vite
native-loader/oxc warnings remain; no unrelated changes were made.

The explicit non-listening DB endpoint was verified before testing. Normal Vitest
setup remains intact and attempts that endpoint before taking its existing
unavailable-DB path; this is not a zero-socket claim. No shared DB, schema operation,
DB-dependent test, full authGD suite or E2E run is claimed. The coordinator did not
repeat the entire Wingman suite or Unicode audit on byte-identical integrated code.

Actual Windows frozen-executable, broader transport/DB integration, response resource
budgets, clock/suspend support, browser/two-PC acceptance and activation remain
separate gates. Nothing was pushed, merged into main or deployed by this checkpoint.

## Evidence locations

Session 1's full local reports live at `.superpowers/sdd/fleet-v2-foundation/handoff.md`
in its Wingman and authGD foundation worktrees. They record exact command output,
RED/GREEN and mutation evidence, reviews, wheel checks and limitations. These ignored
reports are local evidence, not new application/CI tests.
