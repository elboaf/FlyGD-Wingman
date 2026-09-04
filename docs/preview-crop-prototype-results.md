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

## Machine and environment facts

Filled once, from the actual probe run(s). Record one row per distinct
machine/monitor/build combination used across the whole probe.

| Field | Value |
| --- | --- |
| Date | (not yet run) |
| Wingman commit | (not yet run) |
| Windows build | (not yet run) |
| CPU | (not yet run) |
| GPU | (not yet run) |
| RAM | (not yet run) |
| Monitor topology (count, resolution, scale, arrangement) | (not yet run) |
| Measurement tool(s) used (e.g. Task Manager, PerfMon, GPU vendor tool) | (not yet run) |
| `WINGMAN_LOG_LEVEL` / `WINGMAN_PREVIEW_PERF` set during the run | (not yet run) |

## Monitor scales and client resolutions exercised

| Scale | Client resolution(s) tested | Notes |
| --- | --- | --- |
| 100% | (not yet run) | (not yet run) |
| 125% | (not yet run) | (not yet run) |
| 150% | (not yet run) | (not yet run) |
| 200% | (not yet run) | (not yet run) |
| Negative-coordinate monitor | (not yet run) | (not yet run) |

## Correctness results (picker mapping)

| Scale | Expected edge (source px) | Observed edge (source px) | Delta (px) | Pass/fail |
| --- | --- | --- | --- | --- |
| 100% | (not yet run) | (not yet run) | (not yet run) | (not yet run) |
| 125% | (not yet run) | (not yet run) | (not yet run) | (not yet run) |
| 150% | (not yet run) | (not yet run) | (not yet run) | (not yet run) |
| 200% | (not yet run) | (not yet run) | (not yet run) | (not yet run) |

Real EVE client geometry/maximized-state check: (not yet run)

## Performance results by stage

Baseline is primary previews only, no crops. Each stage column is that many
simultaneous load crops alongside as many running clients as the machine
allowed (design doc: 2, 5, 10, 20 running clients where the client count
permits).

| Metric | Baseline | Stage 1 (1 crop) | Stage 2 (2 crops) | Stage 4 (4 crops) | Stage 8 (8 crops) |
| --- | --- | --- | --- | --- | --- |
| Running clients | (not yet run) | (not yet run) | (not yet run) | (not yet run) | (not yet run) |
| Crop-click p50 latency (ms) | N/A | (not yet run) | (not yet run) | (not yet run) | (not yet run) |
| Crop-click p95 latency (ms) | N/A | (not yet run) | (not yet run) | (not yet run) | (not yet run) |
| Primary-preview activation p95 baseline (ms) | (not yet run) | — | — | — | — |
| Drag p95 worst inter-event gap (ms) | (not yet run) | (not yet run) | (not yet run) | (not yet run) | (not yet run) |
| Drag max inter-event gap (ms) | (not yet run) | (not yet run) | (not yet run) | (not yet run) | (not yet run) |
| Primary-preview drag p95 (ms), crop stage active | N/A | (not yet run) | (not yet run) | (not yet run) | (not yet run) |
| Wingman+DWM CPU median, 60s idle (%) | (not yet run) | (not yet run) | (not yet run) | (not yet run) | (not yet run) |
| DWM GPU engine utilization median, 60s idle (%) | (not yet run) | (not yet run) | (not yet run) | (not yet run) | (not yet run) |
| Wingman working set after 60s settle (MiB) | (not yet run) | (not yet run) | (not yet run) | (not yet run) | (not yet run) |
| Working-set increase over baseline (MiB) | — | (not yet run) | (not yet run) | (not yet run) | (not yet run) |
| Working-set threshold (`8 + 4×crops` MiB) | — | 12 | 16 | 24 | 40 |
| Prototype crop HWND count | 0 | (not yet run) | (not yet run) | (not yet run) | (not yet run) |
| HWND count after closing stage | — | (not yet run) | (not yet run) | (not yet run) | (not yet run) |
| DWM HRESULT warnings observed | (not yet run) | (not yet run) | (not yet run) | (not yet run) | (not yet run) |
| Repeated warning every ~700ms sweep? | (not yet run) | (not yet run) | (not yet run) | (not yet run) | (not yet run) |
| Pass/fail | N/A | (not yet run) | (not yet run) | (not yet run) | (not yet run) |

## Lifecycle results

| Scenario | Observed | Pass/fail |
| --- | --- | --- |
| Close source client | (not yet run) | (not yet run) |
| Logout to character select | (not yet run) | (not yet run) |
| Character select (cold start, no invented identity) | (not yet run) | (not yet run) |
| Rebinding on a new HWND (same character) | (not yet run) | (not yet run) |
| Minimize/restore source client | (not yet run) | (not yet run) |
| Picker cancel | (not yet run) | (not yet run) |
| Client-loss cancellation | (not yet run) | (not yet run) |
| Full shutdown / teardown | (not yet run) | (not yet run) |

## Minimized-client crop content

Recorded, not gated: the design doc does not require the first crop release
to solve minimized content, only to state it and avoid an unbounded recovery
loop.

| Scenario | live / frozen / black / stale | Notes |
| --- | --- | --- |
| Source client minimized | (not yet run) | (not yet run) |
| Source client restored | (not yet run) | (not yet run) |

## Cap determination

| Stage | Ran? | All criteria pass? | Notes |
| --- | --- | --- | --- |
| 1 crop | (not yet run) | (not yet run) | (not yet run) |
| 2 crops | (not yet run) | (not yet run) | (not yet run) |
| 4 crops | (not yet run) | (not yet run) | (not yet run) |
| 8 crops | (not yet run) | (not yet run) | (not yet run) |

**Resulting production live-crop cap:** (not yet run — set only after the
probe records every applicable stage above)

## Go/no-go

(not yet run)

Once the probe is complete this section records one of:

1. Go, with the cap above.
2. Go, with a narrowed production design and the evidence-backed limitation
   that requires it.
3. No-go, with the findings retained and no production schema work started.
