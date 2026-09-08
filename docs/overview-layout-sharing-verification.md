# Overview/layout sharing: verification record

## Engineering-approved acceptance candidate

**Verified source:** `fdc04b32b1195cef10c3fe906920b734dd70cf4e`.
The parent independently verified checkout
`527cb78cfdecd4175a3acfdd147336cbfe2b03c0` (the source plus its documentation).
Implementation, scoped polish, independent whole-branch review and the one final
fix-wave rereview are now complete. **No known code-review findings remain.**
This is an engineering-approved acceptance candidate, not a release-validated or
installed Windows build.

The whole-branch review covered every changed file in
`a38c7a09b268ca2c95805088e407056e8b7d1f31..b4b8fe7ffa155d2131bee9f2e1295bb01d3cdf9c`.
It confirmed the earlier three polish fixes and found one remaining Profiles
response-order race. The scoped rereview of `b4b8fe7..527cb78` marked that finding
**ADDRESSED / APPROVED**, with no new breakage: older state responses cannot undo
newer rendered state, and refresh promises, original payloads and follow-up
ownership remain intact. No second broad review or unreviewed source fix followed.

### Parent's independent final gates

```bash
UV_PROJECT_ENVIRONMENT=/tmp/wingman-task10-venv uv sync --locked --extra dev
# Passed: resolved 56 packages, checked 39.
UV_PROJECT_ENVIRONMENT=/tmp/wingman-task10-venv uv run --no-sync python -m pytest tests/ -q -rs --basetemp=/tmp/wingman-parent-final-fixed --junitxml=/tmp/wingman-parent-final-fixed.xml
# 8,254 passed, 11 skipped in 328.82s.
UV_PROJECT_ENVIRONMENT=/tmp/wingman-task10-venv uv run --no-sync ruff check .
# All checks passed.
UV_PROJECT_ENVIRONMENT=/tmp/wingman-task10-venv uv run --no-sync ruff format --check .
# 316 files already formatted.
node --check wingman/web/uisetup.js
node --check wingman/web/evesettings.js
node --check wingman/web/app.js
node --check wingman/web/dev.js
node --check tests/fixtures/formations_page.cjs
node --check tests/fixtures/ui_setup_page.cjs
# All six passed.
cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml
# 1 passed, 0 failed/ignored.
git diff a38c7a0..HEAD --check
# Passed; tracked worktree clean before this evidence-only update.
```

The parent also checked actual bundled-path codec availability and SHA-256
`4a4b57f48829002be1aff6eda8193f9e1fb8257a9bef5666dd26b0e225e815b4`.
JUnit independently confirmed 89 setup-page, 116 dev-harness and 11 integration
cases passed, with no codec/Node skips. All 11 skips are the Windows-only cases
listed below. The parent inspected representative final native-warning and
detached-publication-warning screenshots; browser execution remains the recorded
Task 8–11 runs, not a new parent browser or Windows run.

### Remaining acceptance, not unfinished implementation

- Hosted Ubuntu/Windows CI has not been dispatched.
- The frozen Windows archive/licence check is wired and source-tested; actual
  frozen imports, WebView2/DPI, native dialogs, OS clipboard and assistive-technology
  checks remain OPEN.
- A genuine fresh recipient and a deliberately different initialized recipient
  still need the actual Share → Import → Review → Create flow, EVE reload/fidelity
  and local-display checks, plus launcher restart/discovery/explicit selection.

No live profiles, EVE windows, launcher selections or real clipboard were changed
by this engineering verification. Nothing was pushed, merged, released or
installed into the user's app. Preserve the linked worktree and recovery evidence.
The manual checklist remains an acceptance contract, not a request for more
isolated schema experiments. Earlier checkpoints below retain their historical
pending gates and observations; this section supplies the current engineering
status.

## Final-review fix candidate (earlier checkpoint)

**Source candidate:** `fdc04b32b1195cef10c3fe906920b734dd70cf4e`
(`fix: admit Profiles refresh responses in request order`), over review-fix base
`b4b8fe7ffa155d2131bee9f2e1295bb01d3cdf9c`. The whole-branch review found one
Important race: Back read A can finish after the owned Create completion's read B
and undo its new profile list/selection. This checkpoint fixes only that finding.
**The parent's scoped rereview and independent fresh gates remain pending.**
No final review approval, engineering-candidate completion, hosted CI, Windows
runtime or manual acceptance is claimed here. Task 8–11 evidence below is retained
as prior evidence, not relabelled as verification of this new candidate.

Profiles now numbers refresh requests and renders a non-null response only if
no later request has already rendered. A pending or null/failed newer read does
not suppress useful older state. `refresh()` still returns its promise and each
request's original payload, including a superseded payload or null. Root-change
and account-roster `.then()` follow-ups still run; receipt handling, ordinary
mutation ownership, backend interfaces and persisted data are unchanged.

Eight new runtime cases execute the actual `app.js`, `evesettings.js` and
`uisetup.js` with the existing DOM/bridge-delivery seams. Three leave Back read A
pending, render B with a new profile first, then deliver old A. The new list and
selection stay rendered, route/focus stay unchanged, a newer setup review remains
authorized, and an ordinary copy keeps its busy/selection/follow-up ownership
until its own completion. Further cases cover in-order overlapping reads,
newer/older null results and both promise follow-ups. The unchanged production
bridge maps missing methods/rejected calls to null; these tests inject that
result, not a real pywebview transport failure.

### Fresh local results for this candidate

Commands ran in the linked worktree with the Task 10 venv. RED preceded the source
change; GREEN and the affected suites preceded scoped polish. The full suite and
all remaining gates below were run fresh **after** scoped `polish-core --fix`
(no additional edits/findings, no nested agents).

```bash
UV_PROJECT_ENVIRONMENT=/tmp/wingman-task10-venv uv run --no-sync python -m pytest tests/test_ui_setup_page.py -k 'refresh' -q --tb=short --basetemp=/tmp/wingman-final-review-fix-red
# RED: 5 failed, 3 passed, 81 deselected in 10.61s; stale-selection assertions.
UV_PROJECT_ENVIRONMENT=/tmp/wingman-task10-venv uv run --no-sync python -m pytest tests/test_ui_setup_page.py -k 'refresh' -q --tb=short --basetemp=/tmp/wingman-final-review-fix-green
# GREEN: 8 passed, 81 deselected in 10.54s.
UV_PROJECT_ENVIRONMENT=/tmp/wingman-task10-venv uv run --no-sync python -m pytest tests/test_ui_setup_page.py tests/test_profiles_page.py tests/test_bridge_contract.py tests/test_page_conventions.py tests/test_dev_harness.py tests/test_ui_setup_integration.py -q -rs --basetemp=/tmp/wingman-final-review-fix-focused
# 564 passed in 177.98s; no skips.
UV_PROJECT_ENVIRONMENT=/tmp/wingman-task10-venv uv run --no-sync python -m pytest tests/ -q -rs --basetemp=/tmp/wingman-final-review-fix-full --junitxml=/tmp/wingman-final-review-fix-full.xml
# 8,254 passed, 11 skipped in 326.10s.
UV_PROJECT_ENVIRONMENT=/tmp/wingman-task10-venv uv run --no-sync ruff check .
# All checks passed.
UV_PROJECT_ENVIRONMENT=/tmp/wingman-task10-venv uv run --no-sync ruff format --check .
# 316 files already formatted.
node --check wingman/web/uisetup.js
node --check wingman/web/evesettings.js
node --check wingman/web/app.js
node --check wingman/web/dev.js
node --check tests/fixtures/formations_page.cjs
node --check tests/fixtures/ui_setup_page.cjs
# All six explicit commands passed; Node v26.5.0.
cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml
# 1 passed, 0 failed/ignored.
git diff b4b8fe7ffa155d2131bee9f2e1295bb01d3cdf9c..HEAD --check
git diff --check
# Passed.
```

Actual `paths.codec_exe()` lookup and availability were asserted before testing.
Release and installed worktree codec hashes were checked before and after the
gates; both remain
`4a4b57f48829002be1aff6eda8193f9e1fb8257a9bef5666dd26b0e225e815b4`.
No rebuild or replacement of the Task 10 release codec was needed. JUnit confirms
89 setup-page, 116 dev-harness and 11 integration cases passed without skips.
All 11 full-suite skips remain Windows-only: ordinary junctions (3), setup
junctions (2), DPAPI (1), WinDLL (1), message pump/window station (1), Win32
bindings (3). No native-codec or Node test skipped.

No browser run was performed for this response-order-only fix; Task 8–11 browser
artifacts were not modified. Hosted CI, frozen Windows/WebView2, native dialogs,
OS clipboard, assistive technology and live recipient/EVE/launcher gates remain
OPEN. This changes page response admission, not backend snapshot versioning or
receipt recovery across process restarts.

## Current Task 11 engineering checkpoint

**Verified source commit:** `9b74f32bb227fe45df1784951bcb69145f90338e`
(`fix: retain setup creation outcomes after leaving the tool`). Tasks 1–10 are
implemented and independently task-approved through
`2b53cd22758bd0ee0a82e113e226a838478bce16`. This checkpoint completes Task 11's
scoped engineering corrections and local evidence, **not manual acceptance or
release validation**. Independent whole-branch review and final fresh verification
follow this checkpoint; hosted CI, frozen Windows/WebView2 and live EVE/launcher
acceptance remain OPEN. No operator actions were requested or performed.

### Corrections and ownership

- Create receipts outlive Back separately from private import drafts. A receipt
  holds only view/request/review correlation and completion state, never input
  text, local rosters or review authorization. Earlier receipts survive a later
  operation starting before their completion push is delivered.
- Owned outcomes appear in a Profiles-local live region beside the setup tools,
  not the upload-owned global strip. The sole completion owner requests fresh
  `eve_settings_state`, including after failure or publication warning. It does
  not settle ordinary `pendingMutation`, navigate, select the completion path,
  resurrect review, steal detached focus or alter a newer setup draft.
- Matching active drafts still receive their own result. Completion and explicit
  starter refusal retire receipts; duplicates/late starter replies are ignored.
  A lost/null/rejected starter is uncertain, keeps its receipt and cannot unlock
  editing as though no worker started. Private inputs and rosters still clear
  on route exit.
- Native parser warnings also occur in summary limitations. Their single owner
  is now the emphasized warning paragraph, preserving distinct limitations and
  additional warnings. The permanent display warning remains pinned. The shell's
  focused-route comment no longer hand-keeps a route count.

The new regressions execute **app.js, evesettings.js and uisetup.js**, including
real shell routing, Profiles opener/Back wiring and the sole completion owner.
They settle the first Back-triggered state read before delivering success,
failure or publication warning. They cover a newer review, two outstanding
Creates, an ordinary copy, another route, exact correlation, duplicates, early
completion, refusal and lost starter replies. An authoritative selection
intentionally differs from `payload.path`. Real parser summaries supply native
warning/limitation overlap; a distinct extra warning stays visible once.

### Fresh verification actually performed

All commands ran in the linked worktree on Linux. The source/test contents
committed at the SHA above were unchanged after these final runs.

```bash
UV_PROJECT_ENVIRONMENT=/tmp/wingman-task10-venv uv sync --locked --extra dev
# Passed: resolved 56 packages; checked 39 packages.
node --version
# v26.5.0
UV_PROJECT_ENVIRONMENT=/tmp/wingman-task10-venv uv run --no-sync python -m pytest tests/test_ui_setup_page.py tests/test_profiles_page.py tests/test_bridge_contract.py tests/test_page_conventions.py tests/test_dev_harness.py tests/test_ui_setup_integration.py -q -rs --basetemp=/tmp/wingman-task11-focused-final
# 556 passed in 173.96s; no skips.
UV_PROJECT_ENVIRONMENT=/tmp/wingman-task10-venv uv run --no-sync python -m pytest tests/ -q -rs --basetemp=/tmp/wingman-task11-full --junitxml=/tmp/wingman-task11-full.xml
# 8,246 passed, 11 skipped in 321.47s.
UV_PROJECT_ENVIRONMENT=/tmp/wingman-task10-venv uv run --no-sync ruff check .
# All checks passed.
UV_PROJECT_ENVIRONMENT=/tmp/wingman-task10-venv uv run --no-sync ruff format --check .
# 316 files already formatted.
node --check wingman/web/uisetup.js
node --check wingman/web/evesettings.js
node --check wingman/web/app.js
node --check wingman/web/dev.js
node --check tests/fixtures/formations_page.cjs
node --check tests/fixtures/ui_setup_page.cjs
# All six commands passed.
cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml
# 1 passed, 0 failed/ignored.
git diff --check
# Passed; staged diff check also passed before the normal scoped commit.
```

Actual `paths.codec_exe()` lookup was asserted to resolve this worktree's
`packaging/bin/wingman-settings-codec`, and `codec_available()` was true. The
Task 10 **release** binary was reused, not a debug test seam or PATH fallback.
Source release and installed SHA-256 were rechecked and both remained
`4a4b57f48829002be1aff6eda8193f9e1fb8257a9bef5666dd26b0e225e815b4`.
Cargo's independent regression builds a debug test executable; that does not
replace the installed release codec used by Python.

After reconciling current docs, the local release build/install recipe below was
also exercised: release build passed in 3.89s, install/availability passed and both
hashes stayed identical. Documentation/packaging consumers and native integration
were rerun without any production/test source changes:

```bash
UV_PROJECT_ENVIRONMENT=/tmp/wingman-task10-venv uv run --no-sync python -m pytest tests/test_ui_setup_integration.py tests/test_packaging_completeness.py tests/test_ui_setup_yaml.py tests/test_page_conventions.py tests/test_bridge_contract.py -q -rs --basetemp=/tmp/wingman-task11-docguards
# 451 passed in 27.77s; no skips.
UV_PROJECT_ENVIRONMENT=/tmp/wingman-task10-venv uv run --no-sync ruff check .
# All checks passed.
UV_PROJECT_ENVIRONMENT=/tmp/wingman-task10-venv uv run --no-sync ruff format --check .
# 316 files already formatted.
git diff --check
# Passed.
```

All 11 skips were inspected in `-rs` and JUnit: three ordinary profile-copy
Windows junction tests, two setup DAT/preference-shaped junction cases, DPAPI,
WinDLL, one real message pump/window-station test and three user32/gdi32/dwmapi
binding tests. **No native-codec or Node coverage skipped.** JUnit contains
81 setup-page runtime cases, 116 dev-harness cases and all 11 integration cases
(six lossless, five actual native), all passed.

TDD initially produced 15 failures in the selected receipt/warning cases:
missing detached refresh/ownership, missing Profiles outcome surface and the
native sentence rendered twice. Explicit surface assertions replaced two
incidental null dereferences before implementation. Runtime GREEN was 81 passed.
The first broader run was 555 passed/one failed: an old lexical guard required
the obsolete forwarding spelling. Its assertion was reconciled without removing
the no-ordinary-state-settlement checks; the final focused/full runs above passed.

### Focused browser evidence

```bash
node .superpowers/sdd/overview-layout-sharing-plan/task11-browser.cjs
# ok=true; 10 measurements, 10 screenshots, errors=[]; no console/resource errors.
```

Linux x86-64 `HeadlessChrome/152.0.0.0`, deviceScaleFactor=1. The driver owns an
ephemeral 127.0.0.1 server and a **new** page, installs clipboard stubs before
scripts, blocks non-local requests, runs the actual dev bridge/modules and defers
only semantic completion delivery. Back's initial state read settles before the
held result is delivered; a new authoritative read follows exactly once.
Only its page/server close; the shared browser is disconnected, not stopped.
No existing tabs, user browser profile, cookies, real clipboard, native dialogs,
private captures/profiles, EVE or launcher were accessed.

At **840x625 and 839x621**, both the native review and scrolled warning region
were checked, plus detached success/failure/publication-warning on Profiles.
DOM measurements and representative screenshots were inspected. Page and control
client/scroll widths agree; native actions remain at y=444–556 / 440–552, with the
permanent display notice inside the viewport. Profiles outcomes are at y=302–338
(success/warning) or 302–320 (failure), widths 774/773. Close ends at x=834/833.
Warnings retain their distinct emphasized colour and each sentence appears once.
Native Keep uses Space, review receives focus, Escape/Back restore the Import
opener, detached completion preserves that focus, and markup remains literal text.
The test server initially returned 404 for Chromium's automatic `/favicon.ico`;
a traced, harness-only 204 response removed that unrelated console failure. The
final run above has no filtered-out console errors.

Ignored evidence directory: `.superpowers/sdd/overview-layout-sharing-plan/`:
`task11-browser.cjs`, `task11-browser-report.json` and
`task11-{840,839}-{native-review,native-warnings,detached-success,detached-failure,detached-warning}.png`.
Task 8/9 historical browser artifacts were preserved, not overwritten or relabelled.

### Current gate matrix

| Gate | Status |
| --- | --- |
| Tasks 1–10 independent task review | APPROVED (parent ruling) |
| Three authorized whole-feature polish findings | FIXED with scoped TDD/source self-review |
| Local full Linux native/Node, Ruff, syntax, Cargo | PASS at the source SHA above |
| Scoped real-browser native/detached lifecycle and floors | PASS, browser-only |
| Independent whole-branch code review and final verification | OPEN, parent continuation |
| Hosted Ubuntu/Windows CI | OPEN, not dispatched |
| Frozen Windows archive/licence check and runtime imports | WIRED/source-tested; actual artifact OPEN |
| Windows/WebView2 DPI, dialogs, OS clipboard and assistive technology | OPEN |
| Fresh and distinct initialized recipient, control, live EVE reload/fidelity/display | OPEN |
| Launcher restart/discovery/explicit recipient selection | OPEN |

The [manual checklist](smoke-checklist.md#overview-and-layout-sharing-profiles--share-setup--import-setup)
remains an acceptance contract, not a new operator request. Preserve the worktree
and recovery data; no push, merge or release is authorized by these results.

## Local verification prerequisites

For a full local suite, **Node and the native settings codec are mandatory**, just
as in CI. Install Node and Rust/Cargo, then run from the intended linked checkout:

```bash
uv sync --locked --extra dev
node --version
cargo build --locked --release --manifest-path packaging/settings-codec/Cargo.toml --target-dir packaging/settings-codec/target
uv run --no-sync python -c "import os, pathlib, shutil; from wingman.evesettings import codec; name = 'wingman-settings-codec' + ('.exe' if os.name == 'nt' else ''); source = pathlib.Path('packaging/settings-codec/target/release') / name; target = pathlib.Path('packaging/bin') / name; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target); assert codec.codec_available(), 'Native integration tests require the built codec'"
uv run --no-sync python -m pytest tests/ -q -rs
```

This is the cross-platform local equivalent of the workflow's release build/copy
step. Task 11 exercised this recipe after its full run, reproducing the same Linux
release hash. Outputs stay ignored and local to the checkout.
`cargo test` alone does not install the runtime binary. A missing codec now fails
native setup integration rather than silently skipping it; inspect skip reasons
so missing Node cannot conceal runtime page coverage either. On Linux use `/tmp`
for a venv/basetemp if needed, as in the actual commands above. No live profile or
clipboard is needed by these tests.

## Historical Task 10 checkpoint

**The Task 10 evidence below is retained as recorded. Its then-open task-review
and polish statements are superseded by the current checkpoint, not rewritten as
if those later checks had already run.**

Tasks 1–9 of the [implementation plan](overview-layout-sharing-plan.md) are
implemented and task-reviewed. Task 10 adds focused facade-to-publication tests,
mandatory CI native/Node prerequisites and a post-freeze YAML contents check.
This checkpoint is based on `db13bc1d59a1e79c8d6d5495f7f27586f02f7131`; Task 10's
independent review and Task 11's whole-branch polish/review/fresh verification
remain separate. **This is not a release sign-off or live-EVE acceptance.**

The earlier parser checkpoint is retained below under
[Historical Tasks 1–3 parser checkpoint](#historical-tasks-13-parser-checkpoint).
Its statements about unimplemented tasks and the universal Task 4 stop describe
that past checkpoint, not the current branch or current work authorization.
The [reassessment](overview-layout-sharing-reassessment.md) and
[client evidence](ui-setup-client-evidence.md) record the intervening support
rulings. No private captures or real profiles were used in Task 10.

### Automated evidence and implementation scope

`tests/test_ui_setup_integration.py` calls the real Api facade, controller,
document adapter, manifest checks, hidden staging, codec verification and final
new-profile publication. Expected imported data is hand-checked literal data,
not the output of the adapter used as its own oracle. Source and recipient have
distinct identities, CRC presence, unrelated settings, filters, labels, local
preferences and geometry. The tests verify:

- Exact recipient IDs/non-owned sections and unselected DAT bytes; exact local
  YAML/INI bytes; unchanged original profiles and exclusion of non-settings cache.
- Effective source filter overrides and clearing imported recipient overrides
  without losing unrelated local definitions; eight tabs in three groups; all
  nine ordered labels with multiplicity and optional formatting; exact geometry
  and target/HUD values, without auto-fitting.
- Native YAML's explicit Keep refusal and successful configuration-only import:
  the recipient's deliberately different two-record label sequence and original
  label timestamp survive intact, supplied tabs become one primary group, surplus
  instances close, geometry stays local, supplied aggregates replace and omitted
  options remain local.
- Same-size unselected-DAT manifest changes, OS copy/publication failures, cleanup,
  correlation, one-shot creation and fresh-review recovery. Encode failure after
  the first staged document succeeds uses only the lossless transport seam.
  Native success/copy/publication/staleness cases use the real subprocess and
  bundled-path resolver without a debug-binary fallback or availability skip.

The broader controller/native suites are retained, not copied into another
controller or duplicate permutation suite. CI now checks Node, builds the locked
release codec, copies the platform-correct executable and asserts availability
**before** pytest on both unchanged Ubuntu/Windows matrix runners. Explicit bash
makes the multiline Python body valid on both. Existing action pins and the
independent Cargo regression step remain. Missing JUnit after a prerequisite
failure emits a notice rather than a second traceback. Pytest includes `-rs`.

Packaging inspection used the actual spec, shared Windows build action, locked
PyInstaller 6.22.2/hooks-contrib 2026.7 and PyYAML 6.0.3 sources. PyYAML is locked
at 6.0.3 (`pyproject.toml` declares `>=6.0.3`); no dependency or version changed.
`overview_yaml` imports `yaml` statically, and `yaml.cyaml` statically imports
`yaml._yaml`; SafeLoader itself is pure Python. No YAML hook or speculative
hiddenimport was needed. The shared build action now inspects the actual
`Wingman.exe` PYZ for the parser/YAML modules, verifies the wheel's optional C
extension under `_internal/yaml`, and checks the bundled versioned full MIT
licence. That check is wired and source-tested, **not run against a Windows
artifact in this session**. It does not prove frozen runtime imports.

### Commands actually run (Linux)

All commands used the linked worktree and Linux `/tmp` state. Dependency setup:

```bash
UV_PROJECT_ENVIRONMENT=/tmp/wingman-task10-venv uv sync --locked --extra dev --group build
# Passed; build group installed only for packaging source inspection.
UV_PROJECT_ENVIRONMENT=/tmp/wingman-task10-venv uv sync --locked --extra dev
# Passed; final test environment, build-only packages removed.
node --version
# v26.5.0
cargo build --locked --release --manifest-path packaging/settings-codec/Cargo.toml --target-dir packaging/settings-codec/target
# Passed, release profile [optimized].
```

The exact CI Python install body was executed through `uv run --no-sync python`
from the parsed workflow, copying only into this worktree's ignored
`packaging/bin`. Source and installed executable SHA-256 both were:

```text
4a4b57f48829002be1aff6eda8193f9e1fb8257a9bef5666dd26b0e225e815b4
```

This is an ELF x86-64 Linux release executable built with Cargo/rustc 1.91.0,
not a Windows PE or packaged-app test. Fresh final checks after scoped polish:

```bash
UV_PROJECT_ENVIRONMENT=/tmp/wingman-task10-venv uv run --no-sync python -m pytest tests/test_ui_setup_integration.py -v -rs --basetemp=/tmp/wingman-task10-integration
# 11 passed in 4.97s (six lossless, five native; no skips).
UV_PROJECT_ENVIRONMENT=/tmp/wingman-task10-venv uv run --no-sync python -m pytest tests/test_ui_setup_integration.py tests/test_ui_setup_controller.py tests/test_ui_setup_profile.py tests/test_evesettings_codec.py tests/test_packaging_completeness.py -q -rs --basetemp=/tmp/wingman-task10-focused
# 480 passed, 2 skipped in 29.27s (Windows-only junction cases).
UV_PROJECT_ENVIRONMENT=/tmp/wingman-task10-venv uv run --no-sync python -m pytest tests/ -q -rs --basetemp=/tmp/wingman-task10-full --junitxml=/tmp/wingman-task10-full.xml
# 8,233 passed, 11 skipped in 310.26s.
UV_PROJECT_ENVIRONMENT=/tmp/wingman-task10-venv uv run --no-sync ruff check .
# All checks passed.
UV_PROJECT_ENVIRONMENT=/tmp/wingman-task10-venv uv run --no-sync ruff format --check .
# 316 files already formatted.
node --check wingman/web/uisetup.js
node --check wingman/web/evesettings.js
node --check wingman/web/dev.js
node --check tests/fixtures/formations_page.cjs
node --check tests/fixtures/ui_setup_page.cjs
# All passed.
cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml
# 1 passed, 0 failed/ignored.
git diff --check
# Passed.
```

All 11 skips were inspected; **none is missing-codec or Node coverage**:

| Test locations | Count | Actual skip reason / remaining evidence |
| --- | ---: | --- |
| `test_evesettings_profilecopy.py:279,318,650` | 3 | Real Windows junction creation/cleanup |
| `test_eveskills_dpapi.py:45,52` | 2 | Real DPAPI / WinDLL bindings |
| `test_preview_host.py:1361` | 1 | Real Windows message pump/window station |
| `test_preview_win32.py:147,162,186` | 3 | user32/gdi32/dwmapi bindings |
| `test_ui_setup_profile.py:458` | 2 | DAT/preference-shaped Windows junction refusal |

The initial prerequisite RED failed for missing CI Node/native/frozen checks and
missing-JUnit handling; native integration explicitly failed before the codec
was built. A later added test assertion incorrectly expected physical integer
zero for `useSmallText`; the existing adapter deliberately normalizes that legacy
option to semantic False. Both focused/full runs exposed it. The test was
corrected to assert `is False` after inspecting that contract; no production
behavior was changed. The final passing commands above were rerun afterward.

### Evidence and open-gate matrix

| Gate | Status | Evidence / next required exercise |
| --- | --- | --- |
| Synthetic facade → controller → adapter → manifest → stage → publish | PASS on Linux | Final lossless and worktree release-native tests above |
| Existing native codec and Node runtime suites | PASS on Linux | Full suite, no codec/Node skips; syntax checks above |
| CI prerequisites and failure reporting | LOCAL PASS; hosted runs OPEN | Workflow body tests exercise missing build, copy/resolver, failed availability and absent/present JUnit; Ubuntu/Windows jobs not dispatched here |
| Developer browser rendering/lifecycle | PRIOR Task 8/9 evidence | Ignored per-task reports record Linux browser checks, including Task 9's 24 measurements/screenshots; not rerun for Task 10's test/CI-only change |
| Frozen YAML modules/extension/licence | WIRED; Windows artifact OPEN | New post-build contents assertion needs a Windows installer build; not a runtime import pass |
| Windows/WebView2 native UI and DPI | OPEN | Installed artifact, dialogs/clipboard, 100/125/150/200% scaling and logical viewport floor |
| Fresh independent recipient / no-change control / EVE reload | OPEN | Authorized operator initializes a disposable base, preserves a control and drives EVE; synthetic files do not establish EVE interpretation |
| Live groups/labels/windows/stacks/display preservation | OPEN | Authorized as-saved visual and byte checks from the smoke checklist, including different recipient labels and refusal paths |
| Launcher restart/discovery/explicit selection | OPEN | Operator action after publication, never inferred from Wingman selection |
| Task 10 independent review / Task 11 whole-branch reconciliation | OPEN | Parent review, then whole-branch polish/review and fresh checks; deferred Task 9 duplicate-warning Minor belongs there |

Use the [overview/layout smoke checklist](smoke-checklist.md#overview-and-layout-sharing-profiles--share-setup--import-setup)
for the remaining manual gates. No EVE, launcher, clipboard, live-profile mutation,
Windows binary execution, push, merge or release was performed in Task 10.

## Historical Tasks 1–3 parser checkpoint

**The remainder is the retained earlier record, not a current completion claim.**

## Status and scope

**Tasks 1–3 of the [implementation plan](overview-layout-sharing-plan.md) are
implemented and independently reviewed. Task 4 is incomplete.** Its universal
development stop has been superseded by the
[case-based reassessment](overview-layout-sharing-reassessment.md): pure adapter
work may proceed while unproved mutations refuse locally. This is not a finished
setup-sharing feature or a release sign-off.

Implementation base: `4ecab11`. Verified code checkpoint: `904d1a8`.

| Commit | Result |
| --- | --- |
| `5a457d0` | Evidence map and independent synthetic source/recipient fixtures |
| `f5c04a5` | Strict portable semantic model and Wingman JSON transport |
| `67acc4a` | Bounded native YAML compatibility; repeated preset groups preserved |
| `904d1a8` | Native JSON scalar fidelity correction found during task review |

No settings-document adapter/writer, profile constructor, new controller
endpoints, GUI, launcher action or live-profile mutation has been implemented
in this checkpoint. Existing probe-sharing behavior remains separate. The branch
has not been pushed or offered for merge as a completed feature.

## What changed and how it works

- `setup_model.py` owns the semantic schema, supported settings/enums/windows,
  limits, new-copy normalization and review-summary projection. Ordered labels,
  exact names and all six geometry integers are retained. It has no file or
  application effects.
- `setup_sharing.py` checks the UTF-8 byte budget, decodes JSON strictly and
  rejects duplicate fields/nonstandard constants. A complete Wingman envelope
  receives full-model validation. Native JSON values go directly to native
  normalization, without reinterpretation through YAML. Canonical export checks
  its output structure and bytes after normalization, as well as its input.
- `overview_yaml.py` uses PyYAML's maintained SafeLoader with a bounded event
  preflight before construction. It rejects unsupported tags, aliases, anchors,
  documents, fields, shapes and duplicate keyed records. Native normalization
  uses the same partial overview model and never supplies a layout component.
- Native tabs become one primary group. Missing native options remain missing;
  supplied aggregates replace rather than imply a union. Ambiguous label types
  retain every record and set an explicit ambiguity flag. A future review/apply
  path must require **Keep my ship labels** before using such an input; the
  parser alone does not enforce a not-yet-implemented GUI action.
- Synthetic fixtures distinguish sender and recipient identities, settings,
  local preference bytes, labels, active groups and stale cached geometry.
  Their helpers retain real codec snapshot/revision/verification/publication
  operations while optionally substituting only subprocess transport.
- PyYAML 6.0.3 was added to the lock, with its complete installed MIT licence in
  the shipped notices. No unrelated dependency version was changed.

The [field map](ui-setup-field-map.md) separates measured representations,
declared Wingman policies, unsupported variants and unproved EVE semantics.
Raw private evidence is not committed. Synthetic transport round-trips are not
proof that EVE interprets the proposed result correctly.

## Discoveries and deliberate decisions

### Preserve repeated group entries

The authorized native export contains repeated group IDs in four of its 42
filter definitions: 37 additional entries. Task 2 initially rejected these,
although the synthetic fixture passed. Task 3 corrected that restriction for
preset `groups` only, in both native and portable input.

**Entries and order are preserved, not deduplicated.** Every entry still counts
toward list/node/byte budgets. Unique named definitions, tab IDs, assignments and
other keyed records remain unique; unrelated membership validation was not
weakened. This avoids silently changing supplied data to make a test pass.

The real input was checked in memory: 42 definitions, eight tabs, one normalized
native group, nine label records, ambiguity true, no layout, and exact group
sequences preserved. These are parser results, not native reset or application
results. No source names, IDs or label text entered the synthetic fixture.

### Keep JSON semantics on the native path

Task review found that decoding native JSON and then reparsing its text with
PyYAML changed some values. Scientific notation could become a string, and
escaped supplementary Unicode could become separate surrogate characters.

Two regression failures reproduced the issue. The fix passes already-decoded
JSON values into the shared native normalizer. Equivalent YAML/JSON cases now
preserve exact names/references and numeric values/types. This did not bypass
JSON duplicate/constant checks or either format's resource/domain validation.

### Presence and conservative support limits

Full Wingman settings normalize absent supported overrides to explicit null
(clear/reset intent); partial native settings retain omission. False and empty
aggregates are distinct from either. Optional label formatting retains its
supplied presence. Semantic boolean fields accept both boolean values, not
arbitrary integers; this does not establish their physical EVE representation.

This initial model requires a nonempty full tab/group configuration and nonempty
non-whitespace preset/tab names, without rewriting accepted text. RGB/RGBA
components use the observed normalized 0–1 domain. Non-null label font/colour
variants, unproved sentinels and other unsupported variants refuse rather than
being transformed or discarded. These are supported-subset limits, not EVE-wide
claims.

## Verification actually performed

The following fresh controller-run checks passed at `904d1a8`, after task-local
polish and the reviewed correction:

```bash
uv run --no-sync python -m pytest tests/ --basetemp=/tmp/wingman-setup-prefix-final -q -rs
# 7,569 passed, 41 skipped in 190.42s

uv run --no-sync ruff check .
# All checks passed

uv run --no-sync ruff format --check .
# 307 files already formatted

git diff 4ecab11..HEAD --check
# Passed
```

The 41 skips comprise **32 unavailable bundled-codec cases and nine Windows-only
cases**. They are not counted as passed. Earlier Task 1 verification exercised
all four new fixture documents through the existing native executable via the
test seam: the 19-test focused run passed, including those four native cases.
That does not replace the broader native/Windows CI prerequisites in Task 10.

Other recorded task evidence:

- Task 1: 15 preparatory tests passed plus four availability skips; native-enabled
  run 19 passed; full suite 6,890 passed/41 skipped.
- Task 2: behavioral RED, 520 new tests plus 450 probe-sharing regressions passed;
  full suite 7,410 passed/41 skipped. A separate RED caught canonical output
  expansion exceeding the node budget; export now checks the expanded result.
- Task 3: initial RED 57 failed/589 passed, then 646 passed. Repeated-group
  correction had its own RED (five failed/two passed) and GREEN (seven passed).
  Focused final checks: 719 passed/five skipped; full 7,539 passed/41 skipped.
- Review fix: two scalar-fidelity RED failures, then 10 passed. Broader checks:
  1,241 passed/five skipped; full 7,569 passed/41 skipped.
- Locked dependency sync, repository lint/format, installed PyYAML licence/version
  coverage and scoped diff checks passed. Task-local polish changes were inspected
  before fresh checks.

Each task received an independent cross-family spec/quality review. Task 1 and
Task 2 were approved without findings. Task 3's Important scalar-fidelity finding
was corrected and scoped re-review found it addressed with no new breakage.
There is no final whole-feature review or release approval yet.

No browser, real clipboard, Windows/WebView2, frozen-build or live EVE acceptance
was run for this parser checkpoint. No GUI exists for this phase yet. The earlier
sender-clone experiment is never a fresh-recipient baseline.

## Original reasons for stopping Task 4

The concerns below remain relevant, but treating them as a universal prerequisite
for all adapter development was too broad. The
[reassessment](overview-layout-sharing-reassessment.md) records newer controlled
evidence, corrects the domain explanation and defines supported versus refused
cases. It supersedes the blanket manual-test/development-stop instruction below;
that instruction is retained here as the historical checkpoint, not a new user
request.

The retained corpus does not establish safe behavior for:

1. **Protected/default definitions.** Repeated `DefaultPreset_*` names do not
   prove an exhaustive built-in classifier or safe collisions with custom names.
2. **Selected-tab and cache references.** Stored active selections, tab names,
   profile metadata and related caches have uncertain replacement/reset rules.
   Deleting containing sections or choosing arbitrary defaults is not justified.
3. **Retiring surplus overview windows.** Grouping, open/state maps, geometry and
   stack references interact. No proved recipe currently authorizes removing or
   resetting them in a recipient.

The next step needs a controlled, explicitly authorized EVE observation session:
a genuinely fresh initialized disposable recipient, a no-change startup/shutdown
control, then separate before/after/reload captures for default/custom filter,
selected-tab, rename/filter replacement and secondary-group retirement operations.
The operator drives EVE; the assistant must not silently change launcher selection,
clone sender DATs into the fresh recipient, delete caches or modify originals.
Exact steps should be agreed before new live-profile work.

Until those observations establish the affected rules, do not implement a guessed
writer or bypass the gate merely because pure parser tests pass. Tasks 4–11 remain
unfinished. The existing linked worktree and ignored per-plan ledger are retained
for resumption.

## Rulings made during this checkpoint

These decisions remain reviewable; none permits unproved profile writes.

1. Use the configured named implementation/review agents rather than override
   models contrary to the global routing agreement. If wrong, capability may
   require escalation/rework.
2. Treat fixture assertions as preparatory contracts, not product/EVE acceptance.
   If a fixture is wrong, downstream schema work needs correction; the physical
   proof gate and actual-EVE acceptance must remain independent.
3. Continue only pure model/parser Tasks 2–3 while physical behavior remains
   unproved. If later evidence differs, parser work may need revision, not a
   rollback of user settings.
4. Accept semantic true/false flags and preserve independently optional supported
   formatting fields without default-filling. An admitted semantic value may
   still need an adapter refusal or revision until its encoding is proved.
5. Normalize full absent settings to null while preserving partial omissions;
   reject null for non-nullable supplied native values. A finer source distinction
   may require later revision before publication.
6. Require nonempty full tabs/groups and meaningful names, with normalized 0–1
   colours. Legitimate edge cases outside this initial subset may be refused and
   need evidence-backed expansion.
7. Preserve repeated preset group entries exactly and narrowly correct the model
   restriction. Later physical handling may still need a documented refusal,
   but no supplied entries are silently removed.

## Reviewer focus and knowledge check

Review resource guarantees at the real decoding boundaries, optional/absent data,
ordered labels, repeated groups, canonical output expansion and native JSON
scalar fidelity. Keep the demonstrated portable model distinct from the still
unproved EVE adapter behavior.

1. Why does full missing-setting normalization differ from partial native input?
2. Why are repeated preset group entries retained while tab assignments stay unique?
3. Which guarantees apply before YAML construction versus after JSON decoding?
4. Why must successful JSON values bypass YAML reinterpretation?
5. What additional evidence is required before a new profile can be published?
