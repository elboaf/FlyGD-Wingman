# Preview crop prototype — acceptance thresholds and results

Phase 0 of `docs/preview-evolution-crops-design.md`. This document is
committed **before** the Windows probe runs. It fixes every pass/fail
threshold in advance so the probe (Task 8) only fills in observed numbers —
it never invents, rounds favorably, or adds a criterion after seeing a
result. If a threshold here turns out to be wrong for the real hardware, that
is a design revision to this file with its own reasoning, not a silent edit
made while filling in results.

Cells in every table below are filled only with values actually observed
during the Task 8 probe. Until then they read **(not yet run)**. A cell that
is not applicable to a stage (for example, a stage skipped for insufficient
clients) reads **N/A — stage skipped**, never a fabricated pass.

## Pass criteria

These eight criteria and the cap rule are the complete gate. A stage is
recorded as failing if it fails ANY applicable criterion below; a stage
skipped for insufficient clients does not pass and cannot pass any criterion
by default.

1. **Correctness.** Every selected source edge is within 2 source pixels of
   the expected edge at 100%, 125%, 150%, and 200% display scaling, and no
   crop action changes any real EVE client's geometry or maximized state.
2. **Activation.** No accepted crop click exceeds 500 ms to observed
   foreground. p95 crop-click latency is no more than 50 ms slower than the
   primary-preview activation baseline.
3. **Drag responsiveness.** p95 worst inter-event drag gap is at most 32 ms
   and no individual gap exceeds 100 ms. Crop stages may not increase
   primary-preview drag p95 by more than 50% over the baseline.
4. **CPU.** Median combined Wingman + Desktop Window Manager (`dwm.exe`) CPU
   over a 60-second idle sample increases by no more than 2.0 percentage
   points above baseline at a passing stage.
5. **GPU.** Median Desktop Window Manager GPU engine utilization over the
   same 60-second idle sample increases by no more than 5.0 percentage
   points above baseline at a passing stage.
6. **Memory.** Wingman working-set increase is at most `8 MiB + 4 MiB × live
   crops` above baseline, measured after a 60-second settle once the stage's
   crops are up.
7. **Resources.** Each load crop adds exactly one prototype crop HWND.
   Closing a stage returns the HWND count to baseline, and no DWM failure
   (`DwmRegisterThumbnail failed` / update HRESULT warning) repeats on every
   ~700 ms sweep.
8. **Lifecycle.** Close, logout to character select, character select,
   rebinding on a new HWND, minimize/restore, cancellation, and shutdown all
   leave no orphan process, HWND, DWM relationship, or repeated warning.

### Cap rule

The production live-crop cap is the greatest of the staged counts — 1 crop,
2 crops, 4 crops, or 8 crops — that passes every applicable criterion above.
A stage that is skipped because the machine had fewer running clients than
the stage requires does not pass and cannot set the cap; the cap is the
greatest **fully run and passing** stage below it. If the 1-crop stage itself
fails, the result is a no-go — there is no cap, and production work does not
start from this probe.

## Automated gates (Linux, current branch)

Rerun per Task 8 Step 1 at commit `402db94` (current branch head, one commit
after `e981400`, which added the picker `SetFocus` fix and its regression
test):

- `uv run --no-sync python -m pytest tests/` — 4834 passed, 11 skipped.
- `uv run --no-sync ruff check .` — all checks passed.
- `uv run --no-sync ruff format --check .` — 249 files already formatted.

Note: an earlier record at `e981400` (before the focus fix) showed 4833
passed, 11 skipped; the one-test difference is the new focus-fix regression
test added in `402db94`, not a flake.

## Narrative notes from this run

- Two named EVE clients were running throughout this session: Amelio
  Pellion and Isiga Ichinumi, both at 1920x1080.
- First live `pick` attempt: primary previews and the picker eventually
  became visible, and drag selection worked, but pressing Enter did not
  create a crop. Diagnosis found the picker was not calling `SetFocus` on
  left-button-down, so keyboard input (Enter) never reached its window
  procedure. Fixed with TDD in commit `402db94` ("fix: focus the crop
  picker on left-button-down so Enter reaches it"). After relaunching with
  the fix, the user confirmed selection → Enter → crop appeared as
  expected.
- The user confirmed stage 1 (1 crop) and stage 2 (2 crops) crop
  functionality worked in this session, with only two named clients
  running. Stage 4 was later exercised in a second session (see below);
  stage 8 has still not been exercised in any session.
- All probe processes exited and no probe process remained after closure.
- The following were not fully evidenced in this run: 125%/150%/200% DPI
  scales, explicit negative-monitor picker mapping, measured click latency
  and drag p95, and minimize/occlusion/alert-pulse details.

### Session 2 — stage 4 evidence

- A later session had five named EVE clients available: Gustav Oswaldo,
  Guarzo Opper, Amelio Pellion, Umochi Tawate, and Astrella Esubria. Only
  Amelio Pellion's resolution (1920x1080, confirmed in session 1) is known;
  the other four clients' resolutions were not measured in this session and
  are not claimed here.
- With five clients available, the user advanced the load harness through
  stages 1, 2, and 4, and reported that stage 4 (4 simultaneous crops)
  functioned correctly.
- Stage 8 was not run: only five named clients were available, one short of
  the eight distinct named clients stage 8 requires.
- An automated 60-second process sample was taken at stage 4, and a
  matching automated 60-second baseline sample (primary previews only, no
  crops) was taken later in the same session. See "Stage 4 automated
  60-second process sample" under the performance table for the exact
  figures and derived deltas.
- Both automated measurement probe processes (the stage-4 sample and the
  matching baseline sample) exited cleanly; no probe process remained after
  either.
- GPU utilization remains unavailable for this session. The automated
  sample's process `HandleCount` is a per-process kernel-handle count, not a
  count of Win32 HWNDs, and does not by itself satisfy the pass criteria's
  HWND-count resource check.

## Machine and environment facts

Filled once, from the actual probe run(s). Record one row per distinct
machine/monitor/build combination used across the whole probe.

| Field | Value |
| --- | --- |
| Date | not recorded (partial probe run; exact calendar date not captured) |
| Wingman commit | `402db94` (fix: focus the crop picker on left-button-down so Enter reaches it) |
| Windows build | Windows 11 Pro, build 26100 |
| CPU | AMD Ryzen 9 5900X, 24 logical CPUs |
| GPU | NVIDIA RTX 4060 Ti, driver 32.0.15.7700 |
| RAM | 127.9 GiB |
| Monitor topology (count, resolution, scale, arrangement) | Three monitors, all API-reported 100% scale (96 DPI): rects `0,0`–`1920,1080`; `3840,291`–`6400,1731`; `-2560,306`–`0,1746` (the last is the negative-coordinate monitor). |
| Measurement tool(s) used (e.g. Task Manager, PerfMon, GPU vendor tool) | Ad hoc probe-process samples, 10-second indicative snapshots only (see "Indicative 10-second samples" note under the performance table); not the required 60-second gate. No PerfMon or GPU vendor tool session was recorded. |
| `WINGMAN_LOG_LEVEL` / `WINGMAN_PREVIEW_PERF` set during the run | not recorded |

## Monitor scales and client resolutions exercised

| Scale | Client resolution(s) tested | Notes |
| --- | --- | --- |
| 100% | 1920x1080 confirmed for Amelio Pellion; other named clients (Isiga Ichinumi, Gustav Oswaldo, Guarzo Opper, Umochi Tawate, Astrella Esubria) not measured | Only scale available on this machine; all three monitors report 100% (96 DPI). A later session ran with five named clients (Gustav Oswaldo, Guarzo Opper, Amelio Pellion, Umochi Tawate, Astrella Esubria) to reach stage 4; only Amelio Pellion's resolution is confirmed. |
| 125% | not exercised | No 125% display available on this machine. |
| 150% | not exercised | No 150% display available on this machine. |
| 200% | not exercised | No 200% display available on this machine. |
| Negative-coordinate monitor | not exercised | A negative-coordinate monitor exists (rect `-2560,306`–`0,1746`), but picker mapping was not explicitly exercised there during this run. |

## Correctness results (picker mapping)

| Scale | Expected edge (source px) | Observed edge (source px) | Delta (px) | Pass/fail |
| --- | --- | --- | --- | --- |
| 100% | not measured | not measured | not measured | insufficient evidence — no expected-vs-observed edge measurement was recorded; only qualitative confirmation that a drag selection followed by Enter produced a crop |
| 125% | not exercised | not exercised | not exercised | N/A — scale unavailable |
| 150% | not exercised | not exercised | not exercised | N/A — scale unavailable |
| 200% | not exercised | not exercised | not exercised | N/A — scale unavailable |

Real EVE client geometry/maximized-state check: not explicitly verified. No
pre/post rectangle or `IsZoomed` comparison was recorded for either named
client during this run.

## Performance results by stage

Baseline is primary previews only, no crops. Each stage column is that many
simultaneous load crops alongside as many running clients as the machine
allowed (design doc: 2, 5, 10, 20 running clients where the client count
permits).

| Metric | Baseline | Stage 1 (1 crop) | Stage 2 (2 crops) | Stage 4 (4 crops) | Stage 8 (8 crops) |
| --- | --- | --- | --- | --- | --- |
| Running clients | 2 (Amelio Pellion, Isiga Ichinumi); 5 (Gustav Oswaldo, Guarzo Opper, Amelio Pellion, Umochi Tawate, Astrella Esubria) in the later stage-4 session | 2 | 2 | 5 (Gustav Oswaldo, Guarzo Opper, Amelio Pellion, Umochi Tawate, Astrella Esubria) | N/A — stage skipped, insufficient clients (5 available, 8 required) |
| Crop-click p50 latency (ms) | N/A | not measured | not measured | not measured | N/A — stage skipped |
| Crop-click p95 latency (ms) | N/A | not measured | not measured | not measured | N/A — stage skipped |
| Primary-preview activation p95 baseline (ms) | not measured | — | — | — | — |
| Drag p95 worst inter-event gap (ms) | not measured | not measured | not measured | not measured | N/A — stage skipped |
| Drag max inter-event gap (ms) | not measured | not measured | not measured | not measured | N/A — stage skipped |
| Primary-preview drag p95 (ms), crop stage active | N/A | not measured | not measured | not measured | N/A — stage skipped |
| Wingman+DWM CPU median, 60s idle (%) | Probe process CPU 0.0065104167%; DWM CPU rounded to 0% (automated 60-second sample from the stage-4 session; see note below). Earlier 10-second indicative sample also recorded below. | not measured at 60s (see 10s indicative sample below) | not measured at 60s (see 10s indicative sample below) | Probe process CPU 0.0086805556%; DWM CPU rounded to 0% (automated 60-second sample; see note below) | N/A — stage skipped |
| DWM GPU engine utilization median, 60s idle (%) | not available (no GPU sample obtained) | not available (no GPU sample obtained) | not available (no GPU sample obtained) | not available (no GPU sample obtained) | N/A — stage skipped |
| Wingman working set after 60s settle (MiB) | 40.98046875 MiB (automated 60-second sample from the stage-4 session; see note below). Earlier 10-second indicative sample also recorded below. | not measured at 60s (see 10s indicative sample below) | not measured at 60s (see 10s indicative sample below) | 41.1640625 MiB (automated 60-second sample; see note below) | N/A — stage skipped |
| Working-set increase over baseline (MiB) | — | not computable from 60s data | not computable from 60s data | +0.18359375 MiB (within the 24 MiB threshold; see note below) | N/A — stage skipped |
| Working-set threshold (`8 + 4×crops` MiB) | — | 12 | 16 | 24 | 40 |
| Prototype crop HWND count | 0 | not counted numerically | not counted numerically | not counted numerically as HWNDs (process handle count 195 recorded — see note below; not equivalent to an HWND count) | N/A — stage skipped |
| HWND count after closing stage | — | not counted numerically (qualitative only: all probe processes exited and no probe process remained after closure) | not counted numerically (qualitative only: all probe processes exited and no probe process remained after closure) | not counted numerically (qualitative only: both automated measurement probe processes exited cleanly, none remained) | N/A — stage skipped |
| DWM HRESULT warnings observed | not inspected/recorded | not inspected/recorded | not inspected/recorded | not inspected/recorded | N/A — stage skipped |
| Repeated warning every ~700ms sweep? | not recorded | not recorded | not recorded | not recorded | N/A — stage skipped |
| Pass/fail | N/A | insufficient evidence — cannot be scored against the committed pass criteria | insufficient evidence — cannot be scored against the committed pass criteria | insufficient evidence — CPU and working-set deltas fall within their individual thresholds, but GPU, activation/drag latency, DPI-scale correctness, HWND-count, and full lifecycle criteria remain unmeasured for this stage, so it cannot be scored as a pass | N/A — stage skipped |

### Stage 4 automated 60-second process sample

A real 60-second automated sample of the measurement probe process was
taken during stage 4 (four simultaneous crops, five named clients running),
alongside a matching 60-second automated baseline sample (primary previews
only, no crops) taken later in the same session:

| Metric | Baseline (60s) | Stage 4 (60s) | Delta |
| --- | --- | --- | --- |
| Probe process CPU | 0.0065104167% | 0.0086805556% | +0.0021701389 percentage points |
| DWM CPU | rounded 0% | rounded 0% | rounded 0% |
| Process working set (median/max) | 40.98046875 MiB | 41.1640625 MiB | +0.18359375 MiB |
| Process handles (median/max) | 195 | 195 | 0 |

These are real 60-second samples of the automated measurement probe
process, not the installed production Wingman application; "probe process
CPU" stands in for criterion 4's "Wingman CPU" term only as an
approximation, and it was not explicitly confirmed that either sample
window was otherwise idle. GPU utilization was unavailable for both
samples. `HandleCount` is a per-process kernel handle count, not a Win32
HWND count, and does not by itself satisfy criterion 7's HWND-count check.

**This is still not a stage-4 pass.** Even though the measured CPU
(+0.0021701389 percentage points) and working-set (+0.18359375 MiB) deltas
are each individually within their respective thresholds (2.0 percentage
points and 24 MiB for four crops), criteria 1 (correctness/DPI scaling), 2
(activation latency), 3 (drag responsiveness), 5 (GPU), 7 (HWND count), and
8 (lifecycle) remain unmeasured for stage 4, and a stage must pass every
applicable criterion to count.

### Indicative 10-second samples (informational only — NOT the required 60-second gate)

Short ad hoc samples taken during the run, kept separate from the table
above because they do not meet the pass-criteria measurement window and
must not be read as a gate pass:

- Baseline (actual probe process, 10s sample): ~40.09 MiB working set, 195
  handles; CPU and DWM both rounded to 0%.
- Stage 1 (10s sample): ~39.99–40.00 MiB working set, 195 handles; probe
  CPU ~0.0065%; DWM rounded to 0%.
- Stage 2 (10s sample): ~42.94–43.08 MiB working set, 219 handles; CPU and
  DWM both rounded to 0%.
- No GPU sample was obtained at any stage.

These numbers are clearly insufficient for the 60-second CPU/GPU/memory
gates in the pass criteria above and are recorded here only as directional
context, not as evidence of a pass.

## Lifecycle results

| Scenario | Observed | Pass/fail |
| --- | --- | --- |
| Close source client | not exercised | N/A — not exercised |
| Logout to character select | not exercised | N/A — not exercised |
| Character select (cold start, no invented identity) | not exercised | N/A — not exercised |
| Rebinding on a new HWND (same character) | not exercised | N/A — not exercised |
| Minimize/restore source client | not exercised | N/A — not exercised |
| Picker cancel | not exercised | N/A — not exercised |
| Client-loss cancellation | not exercised | N/A — not exercised |
| Full shutdown / teardown | All probe processes exited and no probe process remained after closure (process-level observation only; no HWND-count or DWM-relationship check was recorded). Reconfirmed in the later stage-4 session: both automated measurement probe processes (stage-4 sample and matching baseline sample) exited cleanly with none remaining. | insufficient evidence for a full pass — process exit confirmed twice, remaining sub-checks (HWND count, DWM relationship) not recorded |

## Minimized-client crop content

Recorded, not gated: the design doc does not require the first crop release
to solve minimized content, only to state it and avoid an unbounded recovery
loop.

| Scenario | live / frozen / black / stale | Notes |
| --- | --- | --- |
| Source client minimized | not exercised | Recorded, not gated, per the design doc — but this run did not exercise it. |
| Source client restored | not exercised | Recorded, not gated, per the design doc — but this run did not exercise it. |

## Cap determination

| Stage | Ran? | All criteria pass? | Notes |
| --- | --- | --- | --- |
| 1 crop | Yes (user confirmed crop creation worked) | Cannot be determined | Functional confirmation only; correctness/activation/drag/CPU/GPU/memory/resources criteria were not measured against the committed thresholds. |
| 2 crops | Yes (user confirmed crop creation worked) | Cannot be determined | Same limitation as stage 1. |
| 4 crops | Yes (user confirmed crop creation and function worked, five named clients available; automated 60-second CPU/working-set sample recorded) | Cannot be determined | CPU (+0.0021701389 pp) and working-set (+0.18359375 MiB) deltas are individually within their thresholds, but GPU, activation/drag latency, DPI-scale correctness, HWND-count, and full lifecycle criteria remain unmeasured for this stage. |
| 8 crops | No | N/A — stage skipped | Only five named clients were available (Gustav Oswaldo, Guarzo Opper, Amelio Pellion, Umochi Tawate, Astrella Esubria); eight distinct named clients are required. |

**Resulting production live-crop cap:** INCOMPLETE — no production cap
selected. Stages 1, 2, and 4 ran and functionally created crops, and stage
4 additionally has a real automated 60-second CPU/working-set sample whose
deltas sit within their individual thresholds, but GPU, activation/drag
latency, mixed-DPI (125%/150%/200%) correctness, and stage 8 remain
unmeasured for every stage, so no stage can be scored as passing or
failing under the complete cap rule.

## Decision

**INCOMPLETE — no production cap selected.** Stages 1 and 2 ran with two
named EVE clients (Amelio Pellion and Isiga Ichinumi) and, after fixing a
picker focus defect (commit `402db94`), functionally created crops as
confirmed by the user. In a later session with five named clients (Gustav
Oswaldo, Guarzo Opper, Amelio Pellion, Umochi Tawate, and Astrella
Esubria), stage 4 also functioned correctly per the user, and a real
automated 60-second sample now exists for stage 4's CPU and working-set
behavior against a matching 60-second baseline: CPU +0.0021701389
percentage points and working set +0.18359375 MiB, both individually
within their committed thresholds. Stage 8 was not run because only five
named clients were available (eight are required). This evidence still
does not permit a GO decision: GPU utilization, activation and drag
latency, mixed-DPI (125%/150%/200%) correctness, and stage 8 remain
entirely unmeasured across every stage, and a stage must pass every
applicable criterion — not just CPU and memory — to set the cap. Real EVE
client geometry/maximized-state was not explicitly compared before and
after either session. **Phase 1 must not begin until the remaining gates —
125%/150%/200% DPI scales, explicit negative-monitor picker mapping,
measured click latency and drag p95, GPU utilization, and the 8-crop
stage — are exercised, or this scope is explicitly revised.**
