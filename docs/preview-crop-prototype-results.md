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

### Scope revision — provisional experimental cap (approved)

After reviewing the observed evidence recorded below — stages 1, 2, 4, and
8 all functionally created and controlled crops; stage 8 remained
responsive by user report when clicking, moving, and resizing crops; the
stage-4 and stage-8 60-second automated CPU/working-set samples were each
individually within their committed thresholds; the short sampled DWM GPU
comparison at stage 8 was within its committed threshold as sampled; probe
processes cleaned up after every session; and one live keyboard-focus
defect was found, fixed, and reverified — the user approved revising
Phase 0's exit criteria.

Rather than requiring every one of the eight pass criteria and the cap
rule above to be fully measured before Phase 1 may begin, the user approved
letting Phase 1 begin with a **provisional, experimental cap of 8 live
crops**, on the explicit condition that this is not a production-release
approval. The quantitative criteria that remain unmeasured (listed in full
in the Decision section below) become mandatory **pre-release** blockers
instead of Phase-0-entry blockers: Phase 1 prototype-to-production
implementation planning may proceed under the provisional cap, but the
feature must not ship, and the cap may be lowered or the feature blocked
entirely, if those remaining gates fail when exercised. This revision does
not retroactively mark any unmeasured criterion as passed, and it does not
change any observed value recorded elsewhere in this document; the
original eight criteria and cap rule remain the complete gate for a full
production pass — they are now pre-release gates rather than Phase-0-exit
gates.

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
  running. Stage 4 was later exercised in a second session, and stage 8 in
  a third session (see below).
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

### Session 3 — stage 8 evidence

- A third session had ten named EVE clients available: Gustav Oswaldo,
  Guarzo Estuven, Guarzo Opper, Guarzo Togenada, Amelio Pellion, Umochi
  Tawate, Astrella Esubria, Sapphire Orewhisper, Suartad Arsten, and Isiga
  Ichinumi. Resolutions for these clients beyond the previously confirmed
  Amelio Pellion (1920x1080) were not measured and are not claimed here.
- With ten clients available, the user advanced the load harness through
  stages 1, 2, 4, and 8, and reported that stage 8 (8 simultaneous crops)
  felt responsive when clicking, moving, and resizing crops, then closed
  the session cleanly.
- An automated 60-second process sample was taken at stage 8 and compared
  against the existing 60-second baseline sample — the same baseline
  figures already recorded for the stage-4 comparison (probe CPU
  0.0065104167%, DWM CPU rounded 0%, working set 40.98046875 MiB, handles
  195), not a newly re-measured baseline for this session. See "Stage 8
  automated 60-second process sample and 10-sample GPU comparison" under
  the performance table for the exact figures and derived deltas.
- A separate 10-sample DWM GPU-engine counter comparison was taken between
  a zero-crop baseline and stage 8; see the same subsection below. This is
  10 discrete samples, not the required continuous 60-second window, so it
  is informational, not a formal pass.
- After the user closed stage 8, the reported remaining probe process
  count was 0 (`REMAINING_PROBE_PROCESSES=0`).
- A separate baseline process launched solely for the GPU comparison is
  expected to self-close; its exit was not independently confirmed in this
  report, so it is not used as evidence for the HWND/process-cleanup
  criterion.
- Process `HandleCount` (up 26 from baseline) is a per-process kernel
  handle count, not a Win32 HWND count, and does not by itself prove the
  crop HWND count criterion.
- Expected-vs-observed source-edge correctness measurements, activation
  latency, drag p95/max, 125%/150%/200% DPI scales, explicit
  negative-monitor picker mapping, and full lifecycle variants (logout,
  rebinding, minimize/restore, cancel, etc.) remain unmeasured in this
  session as well.

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
| Measurement tool(s) used (e.g. Task Manager, PerfMon, GPU vendor tool) | Ad hoc probe-process samples: 10-second indicative snapshots (session 1), 60-second automated process samples (sessions 2 and 3), and a 10-sample DWM GPU-engine counter comparison (session 3). Not a sustained 60-second GPU/PerfMon session; no GPU vendor tool was used. |
| `WINGMAN_LOG_LEVEL` / `WINGMAN_PREVIEW_PERF` set during the run | not recorded |

## Monitor scales and client resolutions exercised

| Scale | Client resolution(s) tested | Notes |
| --- | --- | --- |
| 100% | 1920x1080 confirmed for Amelio Pellion; other named clients (Isiga Ichinumi, Gustav Oswaldo, Guarzo Estuven, Guarzo Opper, Guarzo Togenada, Umochi Tawate, Astrella Esubria, Sapphire Orewhisper, Suartad Arsten) not measured | Only scale available on this machine; all three monitors report 100% (96 DPI). A later session ran with five named clients to reach stage 4, and a third session ran with ten named clients to reach stage 8; only Amelio Pellion's resolution is confirmed in any session. |
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
| Running clients | 2 (Amelio Pellion, Isiga Ichinumi); 5 (Gustav Oswaldo, Guarzo Opper, Amelio Pellion, Umochi Tawate, Astrella Esubria) in the stage-4 session; 10 (Gustav Oswaldo, Guarzo Estuven, Guarzo Opper, Guarzo Togenada, Amelio Pellion, Umochi Tawate, Astrella Esubria, Sapphire Orewhisper, Suartad Arsten, Isiga Ichinumi) in the stage-8 session | 2 | 2 | 5 (Gustav Oswaldo, Guarzo Opper, Amelio Pellion, Umochi Tawate, Astrella Esubria) | 10 (Gustav Oswaldo, Guarzo Estuven, Guarzo Opper, Guarzo Togenada, Amelio Pellion, Umochi Tawate, Astrella Esubria, Sapphire Orewhisper, Suartad Arsten, Isiga Ichinumi) |
| Crop-click p50 latency (ms) | N/A | not measured | not measured | not measured | not measured (user reported crops felt responsive when clicking, moving, and resizing, but no quantitative latency was captured) |
| Crop-click p95 latency (ms) | N/A | not measured | not measured | not measured | not measured (same qualitative-only report as p50) |
| Primary-preview activation p95 baseline (ms) | not measured | — | — | — | — |
| Drag p95 worst inter-event gap (ms) | not measured | not measured | not measured | not measured | not measured (qualitative responsiveness reported only) |
| Drag max inter-event gap (ms) | not measured | not measured | not measured | not measured | not measured (qualitative responsiveness reported only) |
| Primary-preview drag p95 (ms), crop stage active | N/A | not measured | not measured | not measured | not measured |
| Wingman+DWM CPU median, 60s idle (%) | Probe process CPU 0.0065104167%; DWM CPU rounded to 0% (automated 60-second sample from the stage-4 session; also used as the comparison baseline for stage 8; see notes below). Earlier 10-second indicative sample also recorded below. | not measured at 60s (see 10s indicative sample below) | not measured at 60s (see 10s indicative sample below) | Probe process CPU 0.0086805556%; DWM CPU rounded to 0% (automated 60-second sample; see note below) | Probe process CPU 0.1822916667%; DWM CPU rounded to 0% (automated 60-second sample; see note below) |
| DWM GPU engine utilization median, 60s idle (%) | not available (no GPU sample obtained) | not available (no GPU sample obtained) | not available (no GPU sample obtained) | not available (no GPU sample obtained) | 10-sample comparison only, not the required continuous 60-second window: DWM median 0% (zero-crop baseline) vs. DWM median 0% (stage 8) — 0 pp median delta, within the 5.0 pp threshold as sampled; see note below for max values and the sampling caveat |
| Wingman working set after 60s settle (MiB) | 40.98046875 MiB (automated 60-second sample from the stage-4 session; also used as the comparison baseline for stage 8; see notes below). Earlier 10-second indicative sample also recorded below. | not measured at 60s (see 10s indicative sample below) | not measured at 60s (see 10s indicative sample below) | 41.1640625 MiB (automated 60-second sample; see note below) | 44.93359375 MiB median / 45.2109375 MiB max (automated 60-second sample; see note below) |
| Working-set increase over baseline (MiB) | — | not computable from 60s data | not computable from 60s data | +0.18359375 MiB (within the 24 MiB threshold; see note below) | +3.953125 MiB (within the 40 MiB threshold; see note below) |
| Working-set threshold (`8 + 4×crops` MiB) | — | 12 | 16 | 24 | 40 |
| Prototype crop HWND count | 0 | not counted numerically | not counted numerically | not counted numerically as HWNDs (process handle count 195 recorded — see note below; not equivalent to an HWND count) | not counted numerically as HWNDs (process handle count 221 recorded — see note below; not equivalent to an HWND count) |
| HWND count after closing stage | — | not counted numerically (qualitative only: all probe processes exited and no probe process remained after closure) | not counted numerically (qualitative only: all probe processes exited and no probe process remained after closure) | not counted numerically (qualitative only: both automated measurement probe processes exited cleanly, none remained) | not counted numerically (qualitative only: reported remaining probe process count 0 after the user closed stage 8; a separate GPU-comparison baseline process is expected to self-close but its exit was not independently confirmed — see note below) |
| DWM HRESULT warnings observed | not inspected/recorded | not inspected/recorded | not inspected/recorded | not inspected/recorded | not inspected/recorded |
| Repeated warning every ~700ms sweep? | not recorded | not recorded | not recorded | not recorded | not recorded |
| Pass/fail | N/A | insufficient evidence — cannot be scored against the committed pass criteria | insufficient evidence — cannot be scored against the committed pass criteria | insufficient evidence — CPU and working-set deltas fall within their individual thresholds, but GPU, activation/drag latency, DPI-scale correctness, HWND-count, and full lifecycle criteria remain unmeasured for this stage, so it cannot be scored as a pass | insufficient evidence — CPU, working-set, and (10-sample, non-60-second) GPU-median deltas fall within their individual thresholds, but expected-vs-observed correctness, activation/drag latency, DPI-scale correctness, numeric HWND counts, and full lifecycle criteria remain unmeasured for this stage, so it cannot be scored as a pass |

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

### Stage 8 automated 60-second process sample and 10-sample GPU comparison

A 60-second automated sample of the measurement probe process was taken
during stage 8 (eight simultaneous crops, ten named clients running),
compared against the same 60-second baseline sample used for the stage-4
comparison above (not a newly re-measured baseline for this session):

| Metric | Baseline (60s) | Stage 8 (60s) | Delta |
| --- | --- | --- | --- |
| Probe process CPU | 0.0065104167% | 0.1822916667% | +0.17578125 percentage points |
| DWM CPU | rounded 0% | rounded 0% | rounded 0% |
| Process working set (median) | 40.98046875 MiB | 44.93359375 MiB | +3.953125 MiB |
| Process working set (max) | — | 45.2109375 MiB | — |
| Process handles | 195 | 221 | +26 |

The CPU delta (+0.17578125 pp) is within the 2.0 percentage point
threshold, and the working-set delta (+3.953125 MiB) is within the
`8 + 4×8 = 40` MiB threshold for eight crops. As with the stage-4 sample,
"probe process CPU" stands in for criterion 4's "Wingman CPU" term only as
an approximation, since the checkout-only harness process was measured,
not the installed production Wingman application. Process `HandleCount`
(+26) is a per-process kernel handle count, not a Win32 HWND count, and
does not by itself satisfy criterion 7's HWND-count check.

A separate 10-sample DWM GPU-engine counter comparison was taken between a
zero-crop baseline and stage 8:

| Metric | Zero-crop baseline (10 samples) | Stage 8 (10 samples) |
| --- | --- | --- |
| DWM GPU engine utilization, median | 0% | 0% |
| DWM GPU engine utilization, max | 4.0644717243% | 4.4748848954% |

No separate probe-process GPU engine appeared in either sample. The median
delta (0 percentage points) is within the committed 5.0 percentage point
threshold as sampled, but this is 10 discrete samples, not the committed
continuous 60-second idle window, so it does not satisfy criterion 5 as a
formal pass — it is recorded as directional context only, the same
treatment given the 10-second indicative CPU/memory samples elsewhere in
this document.

**This is still not a stage-8 pass.** Even though the measured CPU,
working-set, and (informally sampled) GPU-median deltas are each within
their respective thresholds, criterion 1 (expected-vs-observed source-edge
correctness and DPI-scale coverage), criterion 2 (activation latency),
criterion 3 (drag p95/max), criterion 7's numeric HWND count, and criterion
8's full lifecycle variants (logout, rebinding, minimize/restore, cancel,
etc.) remain unmeasured for stage 8, and a stage must pass every applicable
criterion to count. The user's qualitative report that stage 8 "felt
responsive" when clicking, moving, and resizing crops is recorded as a
functional observation, not a measured pass of criteria 2 or 3.

After the user closed stage 8, the reported remaining probe process count
was 0 (`REMAINING_PROBE_PROCESSES=0`). A separate baseline process launched
solely for the GPU comparison above is expected to self-close; its exit
was not independently confirmed in this report, so it is not counted as
HWND-cleanup evidence.

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
| Full shutdown / teardown | All probe processes exited and no probe process remained after closure (process-level observation only; no HWND-count or DWM-relationship check was recorded). Reconfirmed in the stage-4 session (both automated measurement probe processes exited cleanly) and again in the stage-8 session, where the user reported `REMAINING_PROBE_PROCESSES=0` after closing stage 8 — though the separate baseline process launched only for the stage-8 GPU comparison is expected to self-close and its exit was not independently confirmed. | insufficient evidence for a full pass — process exit confirmed on three occasions, remaining sub-checks (numeric HWND count, DWM relationship) not recorded, and one GPU-comparison process's closure remains unconfirmed |

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
| 8 crops | Yes (user reported responsive clicking/moving/resizing then a clean close; ten named clients available; automated 60-second CPU/working-set sample and a 10-sample GPU comparison recorded) | Cannot be determined | CPU (+0.17578125 pp) and working-set (+3.953125 MiB) deltas are individually within their thresholds, and the 10-sample GPU median delta (0 pp) is within threshold but is not a formal 60-second pass; expected-vs-observed correctness, activation/drag latency, DPI-scale correctness, numeric HWND counts, and full lifecycle criteria remain unmeasured for this stage. |

**Resulting production live-crop cap under the original eight-criterion
gate:** Still not determined by measurement alone — no stage has had every
applicable criterion measured and passed. Stages 1, 2, 4, and 8 all ran and
functionally created crops; stages 4 and 8 additionally have real automated
60-second CPU/working-set samples whose deltas sit within their individual
thresholds, and stage 8 has an informal 10-sample GPU-median comparison
also within threshold. Expected-vs-observed source-edge correctness,
activation latency, drag p95/max, mixed-DPI (125%/150%/200%) coverage, a
continuous 60-second GPU sample, numeric HWND counts, and full lifecycle
variants remain unmeasured for every stage, so no stage can be scored as
passing or failing under the complete cap rule.

See the "Scope revision" note above and the Decision below: the user has
separately approved a **provisional, experimental cap of 8 live crops** for
Phase 1 planning purposes, subject to the pre-release blockers listed in
the Decision section. That approval is a scope-revision decision, not a
claim that stage 8 (or any stage) satisfied every criterion above.

## Decision

**GO — Phase 1 experimental cap: 8 live crops.** This is a provisional,
experimental cap for Phase 1 planning and implementation, **not a
production-release approval**. The user reviewed the observed evidence in
this document and approved this scope revision on the basis that: stages
1, 2, 4, and 8 all functionally created and controlled crops; stage 8
remained responsive by user report when clicking, moving, and resizing
crops; the stage-4 and stage-8 60-second automated CPU/working-set samples
were each individually within their committed thresholds (stage 4: CPU
+0.0021701389 pp, working set +0.18359375 MiB; stage 8: CPU +0.17578125
pp, working set +3.953125 MiB); the short 10-sample DWM GPU comparison at
stage 8 was within its committed threshold as sampled (0 percentage-point
median delta); probe processes cleaned up after every session; and one
live keyboard-focus defect (Enter not reaching the picker) was found,
fixed in commit `402db94`, and reverified by the user.

**This decision does not claim that any unmeasured criterion passed.** The
following remain mandatory pre-release blockers and must be exercised
before a production release, not merely before Phase 1 planning begins:

- Quantitative expected-vs-observed source-edge accuracy (criterion 1),
  including at 125%, 150%, and 200% display scaling and an explicit
  negative-coordinate-monitor picker exercise.
- Activation latency (criterion 2) — measured, not user-reported.
- Drag responsiveness p95/max inter-event gap (criterion 3) — measured,
  not user-reported.
- A continuous 60-second GPU sample (criterion 5) — the existing GPU
  evidence is a 10-discrete-sample comparison, not the committed window.
- Numeric HWND/DWM accounting (criterion 7) — process handle counts were
  recorded but are not HWND counts, and no formal HWND-before/after or
  DWM-relationship check has been performed.
- The full lifecycle matrix (criterion 8): minimize/restore,
  partial/full occlusion, alert-pulse-while-dragging, logout to character
  select, character-select cold start, same-character HWND rebinding, and
  picker cancel/client-loss cancellation.
- Stuck-capture behavior after a lost mouse capture (part of criterion 8's
  lifecycle matrix, named separately because nothing in Phase 0 could
  exercise it): neither prototype window handles `WM_CAPTURECHANGED`, so a
  drag whose capture is taken away mid-gesture — a UAC prompt, Win+D, a lock
  screen, or another window grabbing capture — may leave a crop or the
  picker believing a drag is still in progress. The production gate is that
  capture loss returns both to a clean idle state, with no phantom
  move/resize following the pointer and no drag that has to be cleared by
  clicking again.
- Settings-dependent inherited behavior the Phase 0 CLI never wired, so no
  probe run could have exercised it: locked-crop inertness under
  `preview.locked` (the probe passes no `locked`/`lock_default` provider) and
  hide-on-lost-focus lockstep with the primary previews (it passes no
  `hide_on_lost_focus` provider). Both are listed as pre-release gates in
  `docs/smoke-checklist.md`.

**The provisional 8-crop cap may be lowered, or the crop feature blocked
entirely, if any of the above fail when exercised.** Phase 1 implementation
planning and prototype-to-production work may proceed under this
provisional cap, but no production release may ship until every criterion
above is measured and passes, or the scope is again explicitly revised
with the user's approval.
