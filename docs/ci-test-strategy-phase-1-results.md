# CI test strategy — Phase 1 results

## Decision

**AUTHORIZE_CONSOLIDATION_PLAN** — **`xdist_adopted=false`**.
The optimized serial required-path p95 is **642s**, above the **300s** ceiling.
Bounded xdist is **rejected**: eight accepted attempts and one actual failure do
not meet the ten-pass rule; even accepted-only required-path p95 is **394s**.
This authorizes only a separate contract-consolidation **plan**, not test deletion,
consolidation, reduced Windows selection, or a fittings bugfix. None is implemented here.
CI returns to the exact serial Test command at `b9d0d34`; dependencies stay unchanged.

## Sources and frozen identities

Authority: [Phase 1 plan, Task 8 and final review gate](ci-test-strategy-phase-1-plan.md#task-8-hosted-stopgo-benchmark).
`E` abbreviates `.superpowers/sdd/ci-test-strategy-phase-1-plan/`, the retained local,
ignored evidence directory, not shipped in the repository. `task-8-protocol.md` and
`task-8-xdist-protocol.md` froze the rules. Current reports: `E/task-8-serial-report.json`
and `E/task-8-xdist-hosted-reconciled-report.json`; the original blocked report is
retained history, not the final assessment. Measurements below derive from JSON.

Historical [baseline run 34309253993, attempt 1](https://github.com/elboaf/FlyGD-Wingman/actions/runs/34309253993)
tested head **`ba85247ad95125168912a353c14963a68682d7d5`**: Windows pytest **599s**,
Ubuntu **206s**, required path **653s**. This is **one observation, not a baseline p95**.
Its real collection was **9199** per OS: Windows **9151 passed / 48 skipped**,
Ubuntu **9188 passed / 11 skipped** (`E/task-8-baseline-{run,jobs}.json`, `E/task-8-baseline.log`).
The original design's approximate case counts are stale.

PR #196, `elboaf/FlyGD-Wingman`: every S/X attempt uses this complete frozen identity triple:

| Variant | Exact head SHA | Exact target-base SHA | Actual tested checkout SHA |
|---|---|---|---|
| S — serial | `b9d0d3403f43adcacc1c7c81c70adffc673254c6` | `35b137e8ef4700911531c822c9203d53e3d4737f` | `3cc2045c3131d6daaff524934d070b5aa3332af8` |
| X — xdist | `b0930ea0b09df421d4d517a99cd424f6e8e4cb5d` | `35b137e8ef4700911531c822c9203d53e3d4737f` | `1a7706efe1ae85da22896d6033748ec3d5c7b671` |

Full workflows: [serial run 34423874081](https://github.com/elboaf/FlyGD-Wingman/actions/runs/34423874081)
and [xdist run 34431394739](https://github.com/elboaf/FlyGD-Wingman/actions/runs/34431394739).
Baseline and candidates differ in upstream commits **and** Phase 1 changes; they
are not a controlled causal speedup comparison. S versus X changes only the CI
Test command, including quiet logging and ephemeral installation, not just scheduling.

## Every hosted attempt

Links use the archived API's Windows job `html_url`, uniquely identifying each
attempt. UTC spans are earliest required-job start → latest completion on
**2026-09-10**. W/U are Windows/Ubuntu Test-step seconds; Path is the required span.
Every observation covers the **whole workflow**; reruns included all jobs, not selected failures.

| Identity / attempt | Status | W s | U s | Path s | Required span UTC |
|---|---|---:|---:|---:|---|
| [S / 1](https://github.com/elboaf/FlyGD-Wingman/actions/runs/34423874081/job/102704862618) | accepted; success | 514 | 151 | 593 | 01:03:07–01:13:00 |
| [S / 2](https://github.com/elboaf/FlyGD-Wingman/actions/runs/34423874081/job/102707073887) | accepted; success | 505 | 192 | 592 | 01:13:43–01:23:35 |
| [S / 3](https://github.com/elboaf/FlyGD-Wingman/actions/runs/34423874081/job/102709262875) | accepted; success | 431 | 150 | 487 | 01:24:24–01:32:31 |
| [S / 4](https://github.com/elboaf/FlyGD-Wingman/actions/runs/34423874081/job/102711134728) | accepted; success | 462 | 193 | 526 | 01:33:40–01:42:26 |
| [S / 5](https://github.com/elboaf/FlyGD-Wingman/actions/runs/34423874081/job/102713366777) | accepted; success | 504 | 179 | 565 | 01:44:58–01:54:23 |
| [S / 6](https://github.com/elboaf/FlyGD-Wingman/actions/runs/34423874081/job/102715486451) | accepted; success | 552 | 160 | 642 | 01:55:46–02:06:28 |
| [S / 7](https://github.com/elboaf/FlyGD-Wingman/actions/runs/34423874081/job/102717955148) | accepted; success | 452 | 195 | 516 | 02:08:13–02:16:49 |
| [S / 8](https://github.com/elboaf/FlyGD-Wingman/actions/runs/34423874081/job/102720030302) | accepted; success | 488 | 141 | 557 | 02:18:26–02:27:43 |
| [S / 9](https://github.com/elboaf/FlyGD-Wingman/actions/runs/34423874081/job/102722076402) | accepted; success | 575 | 170 | 642 | 02:28:43–02:39:25 |
| [S / 10](https://github.com/elboaf/FlyGD-Wingman/actions/runs/34423874081/job/102724449953) | accepted; success | 264 | 186 | 312 | 02:40:40–02:45:52 |
| [X / 1](https://github.com/elboaf/FlyGD-Wingman/actions/runs/34431394739/job/102727461763) | accepted after skip reconciliation; success | 268 | 96 | 338 | 02:56:34–03:02:12 |
| [X / 2](https://github.com/elboaf/FlyGD-Wingman/actions/runs/34431394739/job/102729811634) | accepted; success | 216 | 81 | 272 | 03:08:37–03:13:09 |
| [X / 3](https://github.com/elboaf/FlyGD-Wingman/actions/runs/34431394739/job/102730842723) | accepted; success | 255 | 100 | 334 | 03:13:58–03:19:32 |
| [X / 4](https://github.com/elboaf/FlyGD-Wingman/actions/runs/34431394739/job/102732040323) | accepted; success | 212 | 99 | 269 | 03:20:12–03:24:41 |
| [X / 5](https://github.com/elboaf/FlyGD-Wingman/actions/runs/34431394739/job/102733083802) | accepted; success | 323 | 97 | 394 | 03:25:38–03:32:12 |
| [X / 6](https://github.com/elboaf/FlyGD-Wingman/actions/runs/34431394739/job/102734439284) | accepted; success | 251 | 98 | 328 | 03:32:53–03:38:21 |
| [X / 7](https://github.com/elboaf/FlyGD-Wingman/actions/runs/34431394739/job/102735635209) | accepted; success | 215 | 93 | 266 | 03:39:18–03:43:44 |
| [X / 8](https://github.com/elboaf/FlyGD-Wingman/actions/runs/34431394739/job/102736681035) | accepted; success | 258 | 107 | 373 | 03:44:57–03:51:10 |
| [X / 9](https://github.com/elboaf/FlyGD-Wingman/actions/runs/34431394739/job/102738051568) | **not accepted; Windows failure** | 322 | 98 | 452 | 03:52:20–03:59:52 |

Serial completed **10/10**. Xdist stopped at **9 total: 8 accepted + 1 failed**;
**attempt 10 was not scheduled**, and the failed job was not retried to obtain green.
There were no cancelled or missing-artifact attempts counted as successes.

## Wall-clock results and limits

| Population | n | Windows median / p95 s | Ubuntu median / p95 s | Required-path median / p95 s |
|---|---:|---:|---:|---:|
| Serial — all accepted | 10 | 496 / 575 | 174.5 / 195 | 561 / 642 |
| Xdist — accepted only | 8 | 253 / 323 | 97.5 / 107 | 331 / 394 |
| Xdist — **all, including failure** | 9 | 255 / 323 | 98 / 107 | 334 / 452 |

Median is ordinary sample median; p95 is nearest rank `sorted[ceil(0.95*n)-1]`:
**the maximum for n=10 (also n=8/9)**, not a stable population-tail estimate.
Required path is `max(completed_at) - min(started_at)` across `checks`,
`test (ubuntu-latest)`, `test (windows-latest)`: initial queue excluded, scheduling
gaps retained. Pytest wall time uses each API Test-step start/end, **not JUnit sums**.
Observed Windows p95 reduction is `(575-323)/575 = 43.83%` (252s), above the 20%
threshold, but reliability failed. Required-path p95 misses 300s by **94s** for
accepted xdist and **152s** for all nine. Speed alone cannot authorize adoption.

Serial command: `uv run --no-sync python -m pytest tests/ -v -rs --durations=30 --junitxml=pytest-result.xml`.
Experiment: `uv run --with pytest-xdist --no-sync python -m pytest tests/ -n 2 --dist loadfile -q -rs --durations=30 --junitxml=pytest-result.xml`.
The extra `-q` instead of `-v` and ephemeral install cost are part of this variant;
its Test-step timing includes installation. No xdist dependency was locked.
All **57 required-job** logs show uv cache hits; caches were not manipulated.
Images were mixed, not controlled: Windows `windows-2025-vs2026` versions
`20260824.214.3` / `20260907.229.1` occurred **6/4 serial**, **5/4 xdist** times;
Ubuntu `ubuntu-24.04` used `20260831.293.1` and `20260907.300.1`.
Python was **3.11.9 Windows / 3.11.16 Ubuntu**, Node **v22.23.2**, uv **0.12.12**;
base installs identify pytest **9.1.1**. Per-job image/tool/cache logs are archived.
Hosted effective overlay pytest/xdist/execnet versions and peak child-process
pressure were **not measured**. Local preflight observed xdist **3.8.0**, execnet
**2.1.2**, pytest **9.1.1**; those are not substituted for hosted measurements.

## Coverage, skip reconciliation, and actual failure

Every hosted candidate attempt collected **9258 cases per OS**. Ubuntu always had
**9247 passed / 11 skipped**; Windows S1–S10 and X1–X8 had **9210 passed / 48 skipped**.
X9 Windows had **9209 passed / 48 skipped / 1 failed**, not identical outcomes.
All original **183 setup + 87 formations** IDs passed on both OSes in all 19 attempts;
there were **zero Node/codec availability skips**. Full sorted identity/status/skip
inventories, not just counts, were checked. Current whole-file totals are 189/94,
including additional lifecycle/diagnostic tests. Task 7 local **9091** cases
(**9080 passed / 11 skipped**) tested branch-only source; hosted merged checkouts
include newer target-main tests, accounting for **167 additional cases**, not omissions.

Skip reasons remain platform/capability-specific (exact per-node records in JSON):
- Ubuntu: `requires a real Windows junction` (3), `requires real Windows junction` (2),
  `requires real DPAPI` (1), `requires real WinDLL` (1),
  `needs a real message pump and window station` (1), `binds user32/gdi32/dwmapi` (3).
- Windows: `POSIX special files and unprivileged symlinks` (21),
  `this user can read a mode-000 directory` (5), `case-sensitive POSIX alias fabrication` (4),
  `POSIX symlink semantics used to fabricate the escape` (3), `POSIX symlink semantics` (2),
  `POSIX mode bits; on Windows DPAPI does the work` (3), `POSIX mode bits; Windows relies on DPAPI` (2),
  `Windows has crypt32` (2), `the guard under test` (1),
  `this filesystem folds case, so these two paths genuinely are the same directory` (1),
  `would pop a real modal dialog and hang the suite` (1),
  `off-Windows degradation; on Windows it really reads the registry` (1),
  and two path-prefixed `cannot hold two names differing only by case` reasons.

Only those last two existing Windows skips receive comparison-only normalization:
`tests/test_evesettings_tree.py::test_profiles_have_a_stable_path_tiebreaker` and
`tests/test_evesettings_tree.py::test_the_case_folding_tiebreaker_still_settles_the_order_it_folds`.
Exactly one `\popen-gw0\` or `\popen-gw1\` insertion under the existing pytest temp
root is allowed in message/text. Status, type, source location, capability suffix,
node ID and every other character must match. Raw differences/hashes and original
blocked assessment remain intact; X1 was reconciled from saved artifacts, not rerun.
Evidence: `E/task-8-xdist-hosted/{normalization-self-check.json,attempt-01/assessment-reconciled.json}`;
Original `E/task-8-xdist-hosted/attempt-01/assessment.json` and `E/task-8-xdist-hosted/inventory-difference.json` remain available.
Collector scratch-parser bugs were corrected against saved artifacts; they were
not actual test failures and are distinct from the following Windows failure.

[X9's failing Windows job](https://github.com/elboaf/FlyGD-Wingman/actions/runs/34431394739/job/102738051568)
failed `tests/test_evefittings_refresh.py::test_all_character_refresh_is_sequential_and_globally_single_flight`:
**IndexError at line 738**, accessing `first_result[0]` after `worker.join(2)` while
the list was empty. **Cause is not established**: this does not prove an xdist race
or a product bug. No timeout, test, or application fix is made or authorized here.
`E/task-8-xdist-hosted/attempt-09/failures.json` retains the traceback; actual GitHub
failure annotations retained the testcase identity (`E/task-8-xdist-failure-annotations.json`).
This confirms identity-level diagnostics, not a source-line annotation guarantee.

## Harness timings — distinct from elapsed suite time

JUnit seconds include pytest setup/call/teardown, not worker-only CPU or Node
`duration_ms` (not persisted). Samples use **10 serial** or **8 accepted xdist**
observations per OS/node/aggregate; X9 remains separately archived. Original sums
cover 183/87 cases; whole-file sums cover 189/94. Neither is xdist **wall time**.

| Population / OS / harness | Original sum median / p95 s | Whole-file sum median / p95 s | Per-original-node p95 range s; slowest node suffix |
|---|---:|---:|---|
| S n=10 / Ubuntu / setup | 3.489 / 4.046 | 9.330 / 10.259 | 0.013–0.309; `stale-manifest` |
| S n=10 / Windows / setup | 9.223 / 11.447 | 18.804 / 26.475 | 0.038–1.204; `stale-manifest` |
| S n=10 / Ubuntu / formations | 11.628 / 12.675 | 13.063 / 14.267 | 0.008–1.518; `paste-invalid-text` |
| S n=10 / Windows / formations | 19.899 / 20.456 | 21.994 / 24.507 | 0.023–2.386; `paste-invalid-text` |
| X n=8 / Ubuntu / setup | 2.619 / 3.338 | 9.812 / 10.876 | 0.007–0.406; `malformed-text` |
| X n=8 / Windows / setup | 4.308 / 6.386 | 17.741 / 21.653 | 0.012–1.262; `catalog-read-after-name` |
| X n=8 / Ubuntu / formations | 12.718 / 14.412 | 13.846 / 15.671 | 0.008–1.676; `paste-invalid-text` |
| X n=8 / Windows / formations | 21.878 / 25.009 | 24.285 / 27.955 | 0.018–2.704; `paste-invalid-text` |

Each range spans 183 or 87 **longitudinal per-node p95s**, not a p95 pooled across
scenarios. Full node IDs, medians/p95s and observations: `E/task-8-serial/longitudinal-junit-timings.json`
and `E/task-8-xdist-hosted/longitudinal-junit-timings.json`. Within-attempt cross-scenario
p95 is a different stored field. Largest serial Windows whole-file p95 case sums:
`test_ui_setup_controller.py` **83.873s**, `test_new_screenshots.py` **35.334s**,
`test_ui_setup_yaml.py` **31.274s**; these inform only a future plan, not deletions.

## Process evidence and migration rulings

Local Linux/WSL2 evidence at S head (Node v26.5.0, strace 6.8), not a hosted Windows trace:
successful `execve` counts exclude launchers/probes and verify nested Python's Node parent.

| Original corpus | Historical one-shot children | Final local traced children |
|---|---|---|
| Setup — 183 passed, no skips | 183 Node + 417 Python = 600 | **1 Node + 5 Python = 6** |
| Formations — 87 passed, no skips | 87 Node; Python count **unmeasured** | **1 Node + 62 Python = 63** |

Sources: `E/task-{4,5}-report.md`, `E/task-8-local-process-{report.md,summary.json}`
and raw traces under `E/task-8-local-process/`. One worker per original corpus/session
is not one for the entire module: VM-error, lifecycle and other diagnostics add workers.
Earlier setup full-module 1 Node/12 Python and corrected 1/24 counts include extra
passes/contracts, not the original-corpus 1/5 population. Two initial trace setups
failed before scenarios when temp overrides encountered WSL anonymous-tempfile
behavior; retained, not corpus results. Corrected traces used the inherited environment.
Single traced elapsed times are not untraced performance benchmarks.

Task 4 preserved **real encoding children** for `unicode-locale` and `import-unicode`:
UTF-8 byte round trips under child-observed overlays without mutating pytest/Node
parent environments. Stable replies are precomputed; three controller/filesystem
boundary scenarios still use children. Task 5 retains real parse/validation children.
Its exhaustive 85×3 order sweep is migration evidence, not recurring PR work: five
representatives run forward/reverse/seeded order (15 requests), plus A→B→A/protocol
and locale coverage. All **87 formations / 183 setup originals** remain; no one-shot
duplicate path. Task 7's lifecycle/VM-error regressions explain the extra module cases.

## Reproduction and finalization boundary

Each `E/task-8-{serial,xdist-hosted}/attempt-NN/` retains `run.json`, `jobs.json`
(all job/step timestamps and URLs), logs/ZIPs, both OS artifact ZIPs and extracted
`pytest-result.xml` / `pytest-timing.json`, full JUnit inventories and assessments.
Artifact IDs/digests are in the reports; do not substitute latest-run same-name artifacts.
Recompute summary values offline from the retained reports, from the worktree root:

```python
import json, math, statistics
from pathlib import Path
root = Path('.superpowers/sdd/ci-test-strategy-phase-1-plan')
for name in ('task-8-serial-report.json', 'task-8-xdist-hosted-reconciled-report.json'):
    attempts = json.loads((root / name).read_text())['attempts']
    for label, rows in (('all', attempts), ('accepted', [a for a in attempts if a['accepted']])):
        for metric in rows[0]['metrics']:
            values = sorted(a['metrics'][metric] for a in rows)
            print(name, label, metric, len(values), statistics.median(values),
                  values[math.ceil(.95 * len(values)) - 1])
```

Full `tests/` remains on both OSes; release/autorelease/build retain pytest then Cargo;
required status names are unchanged. Task 7 and ten serial hosted runs support restored
source; no full rerun solely for Markdown. Gates: `E/task-8-finalization-report.md`.
Controller owns review, commit and final PR validation, not an X9 retry or benchmark sample.
