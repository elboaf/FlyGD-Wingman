# Custom gamelog alerts — verification and acceptance record

## Checkpoint and authority

**Task 10 focused verification passes; final full-suite verification is PENDING.**
The first full run found four test-contract mismatches, corrected with parent
approval and freshly verified below. This is not final engineering or release
acceptance. Windows/WebView2/native audio/real EVE acceptance is **OPEN**.
Parent-owned broad polish and whole-branch review are not yet complete; broad
polish has reported two UI recovery shortcomings for a separate parent-owned
fix. No UI code was changed by Task 10.
Tasks 1–9 and Task 9's three review findings were reported reviewed/resolved by
the parent before this task; that does not substitute for the final broad review.

- User approved plan commit `7faa7d6b0bdf81a14905eb2a8ed551a08fe3d228` for
  test-first implementation, including **both §3.1 interpretations**:
  1. A new or cleared blank search is valid disabled configuration. Executable
     searches require 3–200 normalized characters; blank cannot be enabled.
  2. Initial, known and retired sources baseline at EOF; genuinely new paths
     discovered after startup read from byte zero. Truncation baselines rewritten
     contents at EOF. Shared-reader replay semantics must not change silently.
- Authoritative design: `2a22f640b09000dc49e6f1beb7b9b3852d7852bf`,
  `docs/custom-gamelog-alerts-design.md` (design branch, not copied here).
- Task 10 input/runtime/UI source: `66c4abc4fcfdf5b30425f9f37200ff0db1409c40`,
  `fix(alerts): preserve control intent and fence uncertainty recovery`.
- Branch: `feature/custom-gamelog-alerts`; linked checkout:
  `/mnt/c/dev/flygd-wingman/.worktrees/custom-gamelog-alerts-plan`.
- Original Task 10 scope: `tests/test_custom_alert_integration.py`, this record
  and `docs/smoke-checklist.md`. After the first full run, the parent explicitly
  approved narrow test-contract adaptations in `tests/test_alerts_patterns.py`,
  `tests/test_api_crops.py`, `tests/test_fleetsharing_worker.py` and
  `tests/test_settings.py`, preserving their behavioral assertions.
  No production correction, dependency, settings defaults-version, release-version
  or packaging-list change was needed.
  The task's commit is identified by subject
  `test(alerts): verify custom alerts across runtime boundaries` and recorded
  with its exact SHA in the task report after commit.

The approved immutable plan still contains planning-time pending-approval text.
The user's explicit approval above supersedes that historical status; neither
interpretation was silently changed during implementation.

## Integrated proof and boundaries

`live_alerts` writes real temporary settings before constructing readers, then
uses the production `build_alerts_controller`, `build_alert_policy` and
`build_telemetry` composition plus a real `Api`. Explicit scans consume real
Listener files through `GameLogStream`, coordinator admission, `AlertPolicy`,
and the real `PreviewHost` mailbox/token checks. Windows discovery, native pump
lifetime, window `arm_alert`, and audio playback are doubles. Existing no-op
thread factories keep scans/dispatches explicit; Event barriers control races
without sleeps. FleetMetrics and local/outbound pure projections remain real.

The integrated tests cover:

| Regression boundary | Observable evidence |
| --- | --- |
| Disabled Add → Api edit/enable → marked-up broadcast | Two custom rules flash for both Listeners; only Alice receives the built-in scram; five valid visuals and one `obey` sound; Fleet attributes SCRAM only to Alice. |
| Queued edit/clear/removal | Coordinator and native-mailbox generations are invalidated; fresh edited query can alert; clear disables atomically. Already started sound is explicitly not retracted. |
| Blocked save, commit and rollback | Scans and dispatch complete while persistence waits; prior snapshot, file and style remain effective. Successful save switches query/style; refusal retains old authority. |
| Startup, source replacement and partial lines | Active-rule restart does not replay history; known/new/retired/truncated paths obey approved EOF/byte-zero semantics; retired queued matches do not arm; partial text waits for newline. |
| Matcher exception/recovery and privacy | Exception injected inside real normalization contains sentinel query/line text; Fleet damage still advances. Idle poll and rename do not recover health; a successful zero-match invocation does. Logs captured through DEBUG, queues, health, native payloads and Fleet projections omit both sentinels. |
| Fleet-only off/on | Both master switches retire queued activation without replacing stream/dispatcher; inactive scans do zero custom normalization while Fleet damage continues. Immediate off/on before dispatch also rejects old work. |
| Capacity and stalled stream drainer | 64 real sources × eight rules fill the derived custom bound; repeated blocked-drain scans stay bounded, one coordinator sentinel remains, and all 192 outgoing damage facts reach Fleet (90 DPS per character). Native admission stays at its own ten-entry bound; one sound. |
| Focus and missing preview | Focused owner is timed/silent; another focused owner permits configured volume/persistence; an absent preview can sound but cannot redirect its ring to another character. |
| Test isolation | Test neither persists nor changes the committed snapshot or real cooldown; it draws timed previews and plays once. A subsequent real line still alerts, then real cooldown suppresses repeats. |
| Shutdown during delivery/save | Final close fences remaining custom audio and native arming; a pending edit may finish persistence but cannot reopen the closed runtime or Test endpoint. |

Every fixture finally stops the coordinator/stream and verifies exactly one
constructed stream/coordinator and disabled production sharing. All inputs and
settings are temporary. No app launch, live profile/window manipulation, active
EVE logfile modification, credential use or relay/network-share activation was
performed by this task. Native rendering and timing cannot be inferred from the
doubles, and bounded-count tests are not a native-latency benchmark.

### Test-first trace

Tests were written before documentation or any proposed production correction.
The first focused invocation had a test import error (`project` instead of the
actual `project_snapshot` API). After correcting the test helper, 18 passed and
four failed because the test's plain damage line omitted EVE's load-bearing
colour/`to</font>` markup. Reusing the existing marked-up outgoing-damage fixture
resolved those test-data failures: **22 passed in 3.46s**. These were harness
errors, **not production RED evidence**. Further focus and activation assertions
were added during local self-review. No artificial RED or production fix was
manufactured for behavior that already worked.

## Final automated gates

All commands run from the linked checkout on Linux. For every `uv` command,
the explicit prefix is
`UV_PROJECT_ENVIRONMENT=/tmp/wingman-custom-alerts-plan-venv`.
The preinstalled release codec uses
`/tmp/wingman-custom-alerts-codec-target`; this avoids build overhead on the
Windows-mounted filesystem without weakening native-codec integration.

The single full-suite invocation completed with **4 failed, 10,655 passed,
11 skipped in 427.59s**. All **25** new integration cases passed in that run.
JUnit: `/tmp/wingman-custom-alerts-full.xml` (10,670 cases, zero collection errors).
No second full-suite invocation was run: the parent owns the final full run
after separate polish fixes. Exact initial gate commands:

```bash
UV_PROJECT_ENVIRONMENT=/tmp/wingman-custom-alerts-plan-venv uv sync --locked --extra dev
node --version
cargo build --locked --release --manifest-path packaging/settings-codec/Cargo.toml --target-dir /tmp/wingman-custom-alerts-codec-target
UV_PROJECT_ENVIRONMENT=/tmp/wingman-custom-alerts-plan-venv uv run --no-sync python -m pytest tests/test_custom_alert_integration.py -q
UV_PROJECT_ENVIRONMENT=/tmp/wingman-custom-alerts-plan-venv uv run --no-sync python -m pytest tests/ -q -rs --junitxml=/tmp/wingman-custom-alerts-full.xml
UV_PROJECT_ENVIRONMENT=/tmp/wingman-custom-alerts-plan-venv uv run --no-sync ruff check .
UV_PROJECT_ENVIRONMENT=/tmp/wingman-custom-alerts-plan-venv uv run --no-sync ruff format --check .
node --check wingman/web/alerts.js
node --check wingman/web/dev.js
node scripts/test_alerts_runtime.js
node scripts/js_smoke.js
cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml --target-dir /tmp/wingman-custom-alerts-codec-target
git diff --check
```

| Gate | Actual result |
| --- | --- |
| Locked sync / Node | 56 packages resolved, 39 checked; Node **v26.5.0**. |
| Release codec | Build passed (0.16s); installed `packaging/bin/wingman-settings-codec` byte-identical to the release target; `codec_available()` true. |
| Final focused integration | **25 passed in 4.27s**, no skips. |
| First full pytest | **4 failed, 10,655 passed, 11 skipped in 427.59s**; retained historical result, not a passing final gate. |
| Four repaired node IDs | **4 passed in 5.89s**. |
| All four affected files plus integration | **273 passed in 24.07s**, no skips. |
| Final full pytest | **PENDING**, parent-owned after separate polish fixes. |
| Repo Ruff check / format | Passed; **378 files already formatted**. |
| JS syntax | Both `node --check` commands passed. |
| Alerts runtime harness | **51/51 passed**. |
| Executable JS smoke | Every module of index, Fleet Bar and Sig Bar loaded; passed. |
| Cargo regression | **1 passed**, zero failed/ignored. |
| Whitespace | `git diff --check` passed. |

Codec availability was checked without rewriting the already installed binary:

```bash
UV_PROJECT_ENVIRONMENT=/tmp/wingman-custom-alerts-plan-venv uv run --no-sync python -c "from pathlib import Path; from wingman.evesettings import codec; source = Path('/tmp/wingman-custom-alerts-codec-target/release/wingman-settings-codec'); target = Path('packaging/bin/wingman-settings-codec'); assert target.read_bytes() == source.read_bytes(); assert codec.codec_available(); print('Installed release codec byte-identical; codec_available=True')"
```

### First full-suite failures and approved test-only corrections

Before correction, all four reproduced without loading the new integration file
(**4 failed in 4.78s**). They were older test-contract/fake mismatches with the
implemented feature, not evidence of pollution from the new fixtures:

- `tests/test_alerts_patterns.py::test_events_and_severity_agree`: assumes renderer
  severity keys equal built-in EVENTS, despite approved custom-only renderer rank.
- `tests/test_api_crops.py::test_tentative_failed_master_off_does_not_drop_telemetry_session_revocation`:
  passes `FakeStream` as constructor; it rejects new `custom_snapshot` keyword.
- `tests/test_fleetsharing_worker.py::test_coordinator_cadence_and_local_metrics_continue_while_publish_is_held`:
  local stream double lacks `subscribe_batches` required by the coordinator.
- `tests/test_settings.py::test_defaults_are_the_documented_values`: expected
  defaults omit the new empty `custom_rules` list.

Focused reproduction command (same uv prefix as above):

```bash
UV_PROJECT_ENVIRONMENT=/tmp/wingman-custom-alerts-plan-venv uv run --no-sync python -m pytest tests/test_alerts_patterns.py::test_events_and_severity_agree tests/test_api_crops.py::test_tentative_failed_master_off_does_not_drop_telemetry_session_revocation tests/test_fleetsharing_worker.py::test_coordinator_cadence_and_local_metrics_continue_while_publish_is_held tests/test_settings.py::test_defaults_are_the_documented_values -q
```

The parent approved all four narrow test-only corrections after inspecting the
failures. Renderer coverage now compares built-in EVENTS against severity keys
excluding `custom`, and asserts custom ranks below every built-in. The crop
constructor adapter explicitly accepts `custom_snapshot` and verifies no Alerts
owner was supplied; it does not swallow arbitrary keyword arguments. The local
sharing stream fake exposes `subscribe_batches`. The exact defaults expectation
now includes `custom_rules: []`. Original crop revocation, sharing cadence and
defaults assertions remain intact; no production code changed.

The four-node reproduction command above then passed **4 tests in 5.89s**.
Fresh file-level verification (including all new integration tests) passed
**273 tests in 24.07s with no skips**:

```bash
UV_PROJECT_ENVIRONMENT=/tmp/wingman-custom-alerts-plan-venv uv run --no-sync python -m pytest tests/test_alerts_patterns.py tests/test_api_crops.py tests/test_fleetsharing_worker.py tests/test_settings.py tests/test_custom_alert_integration.py -q -rs
```

Repository Ruff check/format and `git diff --check` passed again after these
corrections. A focused pass does not turn the first full-run result into a full
pass. Final full-suite verification remains pending with the parent.

### Skip inspection

All 11 JUnit skip entries were inspected. **No Node or native-codec tests
skipped.** Remaining skips require Windows facilities:

| Location | Count | Reason |
| --- | ---: | --- |
| `test_evesettings_profilecopy.py:279,318,650` | 3 | Requires a real Windows junction. |
| `test_eveskills_dpapi.py:45` | 1 | Requires real DPAPI. |
| `test_eveskills_dpapi.py:52` | 1 | Requires real WinDLL. |
| `test_preview_host.py:1361` | 1 | Needs a real message pump and window station. |
| `test_preview_win32.py:147,162,186` | 3 | Binds user32/gdi32/dwmapi. |
| `test_ui_setup_profile.py:458` | 2 | Requires real Windows junction (`core_char_31.dat`, `prefs.ini`). |

Local self-review/polish is scoped to Task 10 since the named input `66c4abc4`,
including the uncommitted test/document additions. No subagents were dispatched;
parent owns the broader `7faa7d6..HEAD` polish and whole-branch review after this
commit. Ruff import ordering/formatting was applied only to the new test file;
the four approved test-contract adaptations required no formatting changes.
Local review confirmed those adapters preserve original behavioral assertions;
there is no final engineering approval implied by this checkpoint.

## Browser evidence — supplied by parent, not native acceptance

Read-only parent artifacts in
`.superpowers/sdd/custom-gamelog-alerts-plan/`:
`browser-check.cjs`, `browser-report.json`, and `browser-*.png`.
They were not modified or rerun by this task.

The final report identifies source
`66c4abc4fcfdf5b30425f9f37200ff0db1409c40`, browser
**Chrome/152.0.7977.64**, `ok: true`, and **18 scenario/viewport combinations**:
`full`, `literal`, `custom-only`, `master-off`, `reader-error`, `no-characters`,
`waiting`, `degraded`, and `failed-save`, each at **840x625** and **839x621**
(deviceScaleFactor 1). The actual dev page runs in an isolated Chromium context
against a loopback static server; external requests are blocked. `errors: []`
records no page/console errors. This is Chromium evidence, not Windows WebView2.

The eight-row expanded editor fits its card's right content edge at **795px**;
the cooldown control is **120px** wide and also ends at 795px. Settings-pane
`scrollWidth == clientWidth`: **626/626** at 840px and **625/625** at 839px.
The parent inspected the final full-editor screenshot and confirmed the inner
horizontal overflow had been fixed. The previous root-only overflow check had
missed that problem; the final harness measures card content and ancestor
scrollports. Cancel restored focus to `custom-alert-dev-custom-1-edit`.

This evidence does not assert Windows scaling, actual audio, native focus,
real-client rings, a complete keyboard/screen-reader pass or measured contrast.
Zero-rule/dynamic workflows and stale responses have Node coverage; the recorded
browser scenario list is not represented as broader manual acceptance.

## Open acceptance and review gates

- [ ] Parent's final full-suite run after separate polish fixes. The four
      original failures have fresh focused passes, not a replacement full pass.
- [ ] Parent's separate fixes for two UI recovery shortcomings found by broad
      polish, then completion of broad polish and whole-branch review.
- [ ] CI on both Ubuntu and Windows, including native codec and packaging/import
      regressions. Local Linux execution is not evidence of a Windows CI pass.
- [ ] Real Windows/WebView2 acceptance: complete every item in
      [the custom-alert checklist](smoke-checklist.md#custom-gamelog-alerts--windowswebview2-acceptance-gate).
      No Windows operator, candidate build, OS/WebView2 versions or native
      results have been recorded at this checkpoint.
- [ ] Record operator/date/build/scaling and failures, then obtain final release
      acceptance. Do not mark these gates complete from Linux/Node/Chromium.
