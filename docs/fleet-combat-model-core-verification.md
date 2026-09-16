# Local combat model core — verification and integration checkpoint

The isolated core is implemented, reviewed and integrated into the **local**
coordinator branch. This is not a release or completion of the remaining shared
Fleet telemetry feature. No push, main-branch merge or production change occurred.

## Source identity

- Core implementation base: `4db102946b356b00ec68108f0c7907dcf8f34628`.
- Task 1: `10271167279bf0664742ef46eec3883d3b347d0a` — immutable values/readers.
- Task 2: `3571bd0ea531a5b7947273fe0a3d22a31b454e51` — row activity/sample/lifetime.
- Full verification ran on `3571bd0e`, unchanged before/after the gates.
- Coordinator cherry-picks: `0d3cac89` and `e85d7dff`, with original commit
  provenance recorded by `git cherry-pick -x`.
- After integration, all non-document source/test/configuration contents match
  `3571bd0e`; only `docs/fleet-telemetry-coordination.md` differed at the comparison.

## What changed and how it works

`telemetry/model.py` defines frozen combat evidence and appends optional metadata
without moving existing positional fields. `telemetry/combat.py` reads immutable
local evidence, filters independently expired supplied observations, decides local
visibility and reports the next future transition using the caller's monotonic
instant. It creates no timers, identities or I/O.

`telemetry/metrics.py` adds a separate thirty-second row-activity deadline alongside
ten-second directional DPS and the intentionally unchanged legacy EWAR hold.
Accepted incoming/outgoing damage, including zero and rounded-zero damage, and
incoming EWAR qualify. Delayed evidence gets only its remaining event-time window;
15-second-old damage contributes activity but no DPS. Complete sorted roster and
NO LOG rows remain collected.

Only a strictly later activity deadline changes its `(opaque lifetime UUID,
accepted sequence)` identity. Rejected facts leave the correction sequence usable.
Actual source/session invalidation clears evidence and changes lifetime identity;
unchanged active rebind retains it. Snapshot metadata records the actual existing
monotonic measurement sample; reading cached snapshots does not renew it.

Internal UUIDs are not projected into current page or relay payloads. No parser,
Alert, coordinator, UI, transport, schema or runtime-owner source changed.

## Reviews and polish

Both task reviews passed spec compliance and quality with no findings. Four
polish roles—general quality, silent failures, type design and comment truth—found
no issues, so polish made no edits. Final independent core review approved
`4db10294..3571bd0e` for coordinator integration, with no Critical/Important/Minor
findings. It also ran a bounded real-metrics/coordinator probe covering delayed
incoming activity, cached sample time, expiry and Off/re-enable token fencing.

## Fresh verification

Commands ran in `/mnt/c/dev/flygd-wingman/.worktrees/fleet-combat-model` with its
locked dev environment, Node and a checkout-local built release settings codec.
The runtime codec path, availability and equality to the release-binary hash were
asserted before and after testing.

```sh
uv run --no-sync python -m pytest tests/ -q -rs --basetemp=/tmp/wingman-local-core-3571bd0e --junitxml=.superpowers/sdd/fleet-combat-model-core-plan/core-pytest.xml
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml
node scripts/js_smoke.js
```

Results:

- **13,466 passed, 13 skipped in 405.92s**; no failures/errors.
- Every skip requires real Windows facilities: junctions, DPAPI/WinDLL, native
  window/message-pump bindings or pystray's Windows backend. No Node/codec skips.
- Ruff lint passed; format check reported **462 files already formatted**.
- Cargo: **1 passed**, none failed/ignored.
- Standalone JS smoke: **PASS every page module loaded**.
- Coordinator independently parsed JUnit: 13,479 cases, 13 skips, no failures/errors.

After cherry-picking into the coordinator worktree, the coordinator ran:

```sh
uv run --no-sync python -m pytest tests/test_telemetry_combat.py tests/test_fleet_metrics.py tests/test_telemetry_coordinator.py tests/test_telemetry_parsing.py tests/test_telemetry_gamelogs.py -q
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
```

**317 passed in 8.79s**; Ruff lint and format passed. Source parity checks against
the fully tested commit passed before this documentation checkpoint.

Task reports retain the earlier RED controls: reader tests failed before correct
expiry/ordering behavior; 49 row-activity tests failed before implementation; an
in-memory mutation disabling incoming row refresh failed seven unchanged cases.
Those controls were not rerun during final verification.

## Ruling and remaining boundaries

Ruling: local metrics are available when either direction is non-None; zero is a
known measurement. This preserves a known direction without fabricating the other.
If changed later, the cost is a local predicate/test adjustment, not a wire or
persisted-schema change. This is not the remote nullable-metric contract.

Production effect observations remain empty in this core. Named attribution,
independent effect production/retention, replacement of legacy EWAR hold, UI row
filtering and display, shared transport/relay, automatic verification and cutover
remain open. The six shared-contract findings are still awaiting user acceptance;
none was applied as part of this core.

Windows/WebView2/frozen-app, rendered UI, live relay and two-PC acceptance were not
performed. Node and Linux tests cannot certify them. The branch/worktree and local
logs are retained for ongoing coordination, not published as a release.

Detailed raw evidence and complete skip identities remain in the model worktree's
`.superpowers/sdd/fleet-combat-model-core-plan/core-verification-report.md` and
sibling test logs/JUnit. The final review and task ledgers remain there as well.
