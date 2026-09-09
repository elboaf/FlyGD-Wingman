# Local duration + Fleet integration — verified snapshot

## Authority and outcome

User authorized local integration and combined verification only. No push, PR, merge to upstream, release, new native app run or disposal. Worker branches/worktrees/evidence are preserved. N-S3 is closed; its uncommitted fixture/evidence is not included here.

Worktree: `.worktrees/followups-integration`.
Branch: `integrate/followups-duration-fleet`.
Tested source endpoint: `1e0c4ce99640f246e950e1dd3fd5ebd6130937a1`.
Final tested upstream target: `a4bf00cc1aa94725ca5929c57e8b5a1852f3ab35` (#190).

**Outcome:** accepted E/F changes integrated locally; final Linux suite **9,176 passed / 11 Windows-only skips**. No integration conflicts, manual production edits or polish fixes were necessary. Windows hosted checks and native/WebView2 behavior are not established by this local run.

Upstream moved again during verification to `59387732c87d429676670da3057980565884c189` (version bump), through `de1cae6` (#191 Import setup flow). As announced, this verification is frozen at #190 rather than chasing moving main indefinitely. Those final two upstream commits are NOT incorporated. Refresh/compare upstream before any later publication; this is not a claim to have tested current moving main.

## What changed and how it works

### Duration reconciliation (E)

First accepted definitive duration verdict wins for exact `(path, size, mtime)`, including definitive None. Retained upload captures resolve independently of stale row IDs; installed rows update through current IDs. Cache dirtiness and persistence survive publication failures. Batches group retained objects and use a bounded current-path index, avoiding quadratic warm hydration and whole-row serialization per queued result. Rename/topology revision invalidation, durable links and WorkGate behavior remain intact.

### Fleet creation identity (F)

A fresh Python creation token travels in the page URL fragment; JS captures it once and prefixes all five page-to-Python Fleet callbacks. Admission, readiness and cleanup stay bound to the concrete window. Stale/replaced/retired-window callbacks cannot mutate the new window. Fit retries retain/revalidate the original target; hide/show preserves creation identity. Failed destruction retains cleanup ownership without restoring admission.

This is creation identity, not authentication or a document-reload epoch. Accepted best-effort fit/ready and native visibility/packaged-URI limitations remain.

## Exact additive history

Both accepted lanes originated at `ab06a6efde9ade0f40791d812d922356e8e6c16f`. Fresh upstream at worktree creation was `e352d531aa6441a6f0bec78f332141f91a03bda9` (#189). All six commits were cherry-picked in their accepted order, without rewriting originals:

| Accepted original | Integration commit |
| --- | --- |
| `f031b1e9f037c4bdf95eeeae637f227767cb0509` | `27fc593c5e7eea7eb995640a2d97e8befa3eeec8` |
| `a484d9ce9998f5285f9150861033873241efd2c7` | `b71744598a1b4fec551a54dc6e96bf8bce76cd80` |
| `d7c0bd40ca359fffb4cd30fa84cabc418d6d82a4` | `ea33564676662094b265bb7f49464592820e3228` |
| `188ecc5ee73022f2d46c8503946450a160e725e2` | `13c8baf5ae338456deab4e9c15cb5e30c11d3ee9` |
| `915d42caebdf2c31177b3f518bfbebf10b46a4d1` | `7f3d27c524ceb029c7efa5f44e0c0d278afd1ff7` |
| `d10c31dc58bbfa98aebb637df29f472623865507` | `4442b6348ff6ca28fa7a53a928815d0691b4c4db` |

#190 arrived while checks ran. It was added by merge `1e0c4ce99640f246e950e1dd3fd5ebd6130937a1`, not rebase/amend. Its API/catalog facade and bridge-contract additions merged without conflicts; all upstream feature/assets/licensing changes were retained.

Independent blob comparisons before #190 proved all accepted files identical to their lane versions except fleetbar.js, which equalled the accepted file plus exactly upstream's newer character title-tooltip hunk. After #190, aggregate E/F diff has the SAME stable patch ID against the new target as against #189: `4f61278ca077340514935ddcf120930b11363cd0`. The two auto-merged API/test files also retain exactly #190's upstream patch (stable ID `7d0ceab395bb8c7d50b778835e649d198551b82f`). No manual conflict resolution or opportunistic refactoring.

Worker tracked trees remain clean at their original accepted heads. N remains at its fixed original base with its separate untracked artifacts.

## Blind-spot and polish passes

Blind-spot reviewer `5629bf9d-bf3b-4b8` found no integration blocker: E/F have no files in common, and the initial only upstream overlap was the separate tooltip hunk. Confirmed own-environment/Node/release-codec prerequisites, shared API/WorkGate boundaries and no inference from old test counts.

Polish ran in safe-fix mode over explicit E/F range, with Python/JavaScript conventions and repository ES5/lifecycle rules taking precedence. Full diff scoped; independent read-only reviews:
- Code quality: `ce6f78d0-3c59-418` — no actionable finding or safe simplification.
- Failure propagation: `6209249c-635d-458` — no actionable swallowed-error/persistence/cleanup finding.
- Comment contracts: `2f94e9aa-a20c-4c6` — no findings.

Type-definition pass skipped: no new class/interface/struct definitions in the diff. No auto-fixes applied. The final E/F patch identity stayed unchanged after the additive upstream merge; the two new overlap hunks were directly checked. Final checks below ran after review. Historical accepted lane verification notes were not rewritten.

## Environment and baseline

Own Linux environment: `/tmp/wingman-followups-integration-linux-venv`, CPython3.11.15, locked dev dependencies. Imports were asserted to resolve this integration checkout. Node26.5.0 and Linux Cargo were available. No worker environment was reused or repointed.

Initial environment at this new worktree's `.venv` and first full baseline reached about90% without reported failures but exceeded600s; it produced no completed JUnit result. It is not passing evidence. A separate native-Linux-storage environment was created with the same locked versions; the original newly created `.venv` was left in place. Runtime stayed substantial because the suite includes many subprocess-driven UI tests; no performance-fix claim is made.

Own release codec built/staged before tests:

```sh
cargo build --locked --release --manifest-path packaging/settings-codec/Cargo.toml --target-dir packaging/settings-codec/target
```

Copied `target/release/wingman-settings-codec` to this checkout's `packaging/bin`, checked byte equality and `codec.codec_available()`. Rebuilt/restaged after #190 before the final full suite. Final release binary SHA256 `4a4b57f48829002be1aff6eda8193f9e1fb8257a9bef5666dd26b0e225e815b4`. Cargo test alone was not used as availability evidence.

Completed runs:

| Snapshot | Passed | Skipped | Time |
| --- | ---: | ---: | ---: |
| Fresh #189 baseline | 8613 | 11 | 638.11s |
| E/F on #189, endpoint4442b634 | 8762 | 11 | 694.67s |
| E/F + #190, endpoint1e0c4ce9 | 9176 | 11 | 883.22s |

Final JUnit contains9,187 cases, zero failures/errors. Every skip is an explicitly Windows-only junction/DPAPI/WinDLL/window-station binding case. No Node/codec availability skips. All twenty explicitly `settings codec not built`-marked parametrized cases ran, alongside required real-codec setup-integration variants; the full module contains23 variants,15 parametrizations named native. These categories are not claimed as an exhaustive count of every codec invocation.

## Exact final checks

Commands run from this integration checkout, using `UV_PROJECT_ENVIRONMENT=/tmp/wingman-followups-integration-linux-venv` for uv:

```sh
uv sync --locked --extra dev
uv run --no-sync python -m pytest tests/ -q -rs --basetemp=/tmp/wingman-followups-final-tmp --junitxml=/tmp/wingman-followups-final-1e0c4ce.xml
uv run --no-sync ruff check --no-cache .
uv run --no-sync ruff format --check --no-cache .
node --test scripts/test_fleetbar_runtime.js
node scripts/js_smoke.js
cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml
```

Results: **9176 passed/11 skipped**, Ruff clean/**335 files formatted**, Fleet Node **35 passed/0 skipped**, every module of all three pages loaded, Rust **1 passed**. Executed the CI workflow's exact static WebView2-predicate agreement and build-action uv-prefix checks; both passed. Full pytest includes bridge/tooltip/startup/scaling/runtime and other page harnesses. Final diff checks passed.

Logs and JUnit copies are retained under ignored `tmp/followups-verification/` in this worktree; initial originals remain in `/tmp/wingman-followups-*`. Build outputs/environments are local ignored evidence, not committed payload.

## Remaining limitations and reviewer focus

- This is a tested local Linux snapshot through #190, not current main after #191/version bump. Update against freshly verified upstream before publication, preserving this history additively.
- Windows Node/Cargo executables and a Windows Rust target were not available in the initial bounded inventory. No system toolchain installation, full Windows run or hosted CI was attempted. Future authorized publication must obtain the CI Windows job with its own release codec/Node prerequisites; Linux skips are not Windows passes.
- No actual app/WebView2/EVE/desktop operations, credentials/ESI/uploads, installer execution or release performed. N-S3's completed fixed-base proof remains separate; no new native round was requested.
- Highest-value reviewer checks: exact-identity definitive None/persistence paths, bounded hydration/index invalidation, Fleet creation-token admission and retained failed-destroy ownership, plus preservation of upstream tooltip/catalog facades.
- No push, PR, upstream merge, release or disposal. The next delivery decision requires user authorization.
