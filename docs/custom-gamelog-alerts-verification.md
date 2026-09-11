# Custom gamelog alerts — verification and acceptance record

## Current status and authority

**Implementation, local engineering verification and code review are complete.**
The verified source revision is `28e6f6e84d9fabc15c93811aaf60d18fb7bbf915`.
All reported Important findings were corrected and cleared by scoped rereview.
This is **not Windows/WebView2 or release acceptance**; those gates remain open.
The branch has not been pushed or merged.

- Branch: `feature/custom-gamelog-alerts`; linked checkout:
  `/mnt/c/dev/flygd-wingman/.worktrees/custom-gamelog-alerts-plan`.
- User-approved plan: `7faa7d6b0bdf81a14905eb2a8ed551a08fe3d228`,
  [custom-gamelog-alerts-plan.md](custom-gamelog-alerts-plan.md).
- Authoritative design: `2a22f640b09000dc49e6f1beb7b9b3852d7852bf`,
  `docs/custom-gamelog-alerts-design.md` on its design branch, not copied here.
- The user explicitly approved both plan §3.1 interpretations:
  1. New/cleared blank searches are valid **disabled** configuration. Executable
     searches require 3–200 normalized characters; blank cannot be enabled.
  2. Initial, known and retired sources baseline at EOF; genuinely new paths
     discovered after startup read from byte zero. Truncation baselines rewritten
     contents at EOF. The shared reader's replay policy is preserved.

The immutable plan retains planning-time approval language; the approval above
supersedes that historical status. No new dependency, defaults-version bump,
release-version change, or package-list change was required.

## What changed and how it works

Settings > Alerts now provides up to eight custom literal, case-insensitive
rules, with inline name/search editing, colour, bundled sound, cooldown,
enable/disable, removal and presentation-only Test. Text commits on Enter or
Apply, never blur. Clearing a search disables the rule atomically. Retry reloads
uncertain authority without replaying an ambiguous mutation.

`AlertsController` owns settings transactions behind six small Api facades.
A successful save publishes one prepared composite: detached Preview state and
an immutable `AlertRuntimeSnapshot`. Failed saves retain prior committed
behavior. Producer/policy/native readers do not acquire the settings I/O lock.

The existing `GameLogStream` performs matching only when both masters and at
least one executable rule permit it. Ordered batches carry semantic facts and
custom matches together. Custom-only staging is bounded in both the stream and
coordinator; ordinary semantic/lifecycle/Fleet traffic retains its existing
lossless behavior. Independent matcher health does not poison reader/Fleet
health, and recovery requires a real successful current matcher invocation.

The policy chooses one audible winner across the whole coordinator batch while
retaining eligible visuals. Custom severity ranks below every built-in.
Rule generations, activation epochs, source identities and close admission
reject stale work through the native mailbox boundary. Test neither persists
configuration nor consumes real matching cooldowns. Raw matching lines and
queries are not added to downstream health, preview or Fleet payloads.

The UI separates committed authority, per-control intent and per-view ownership.
Late acknowledgments reconcile against fresh authority without erasing newer
drafts, moving focus, reviving removed rows or releasing uncertainty through an
older read. Source-local incremental UTF-8 decoding preserves valid characters
split across polls; matching still waits for newline.

## Scope rulings made during implementation

These are the implementation rulings, in order, rather than new product scope.
The two semantic interpretations above were approved by the user beforehand.

| Ruling | Why | Cost if wrong / review focus |
| --- | --- | --- |
| Use the existing colour regex with `fullmatch` in custom validation, without changing built-in validation. | Reject a trailing newline at the new strict boundary. | Custom colour compatibility; built-ins remain unchanged. |
| Adapt the existing private committed-snapshot test to the prepared composite. | The publication representation changed by design. | Preserve its identity/rollback assertions rather than weakening them. |
| Add the planned coordinator `custom_matcher_health()` delegation. | Api should not reach into the private stream. | Small interface addition; startup/lazy wiring tests cover it. |
| Update four older test contracts/fakes after the first full run. | Renderer severity now includes custom; constructors/batch subscriptions and defaults changed as approved. | Preserve original severity, crop revocation, sharing cadence and defaults assertions. |
| Add explicit read-only Retry and recovery-owned settled messages. | Temporary failed authority reads otherwise stranded editing or left misleading “checking” text. | UI-only recovery ownership; no mutation replay or new bridge endpoint. |
| Close Api's presentation owner in the adapted crop regression's outer `finally`. | Review exposed an existing real worker leak behind the repaired constructor mismatch. | Narrow test cleanup; original session/crop assertions remain intact. |
| Correct source-local incremental UTF-8 decoding and reset behavior. | The combined Unicode/partial-line contract failed on a valid split code point. | Shared-reader input handling; preserve malformed replacement, cursor and replay semantics. |

Other review corrections stayed within the planned behavior: independent
control acknowledgment reconciliation, post-outcome recovery-read fences,
scoped select sizing, and navigation-safe deferred acknowledgments.

## Integrated proof and boundaries

`tests/test_custom_alert_integration.py` uses real temporary settings and Listener
files through production builders, Api/controller, stream, coordinator,
FleetMetrics, policy and the real PreviewHost mailbox. Native discovery/pump
lifetime, final window arming and audio are doubles. Existing no-op thread
factories keep scans/dispatch explicit; Event barriers control races without
sleeps. Local/outbound pure Fleet projections remain real.

| Boundary | Observable evidence |
| --- | --- |
| Add/edit/enable and marked-up broadcast | Two custom rules match both Listeners; only the proven owner receives built-in scram; multiple visuals, one sound, correct Fleet attribution. |
| Queued edit, clear and removal | Coordinator/native generations invalidate stale work; fresh queries work; clear disables atomically. Already started sound is not retracted. |
| Blocked save and rollback | Reading/dispatch continue on old authority while persistence waits; success switches behavior and refusal retains old file/snapshot/style. |
| Source replay and partial input | Startup/known/retired/truncated EOF and new-path byte-zero behavior remain; no match before newline. Split 2-, 3- and 4-byte UTF-8, source isolation and resets have real-file regressions. |
| Matcher failure and privacy | Fleet damage continues; idle polls or renames do not fake recovery. A successful zero-match invocation recovers health. DEBUG logs, queues, health and projections omit private matching sentinels. |
| Fleet-only and master transitions | Inactive scans do zero custom normalization without stopping Fleet; off/on invalidates old work without replacing the owner. |
| Capacity | 64 sources × eight rules remain within the custom bound during blocked draining; one coordinator sentinel; all 192 outgoing damage facts reach Fleet. Native admission retains its own bound. |
| Focus, missing previews and Test | Focused owners are timed/silent; missing previews never redirect rings; Test does not save or consume real cooldown. |
| Shutdown and cleanup | Closing rejects pending custom presentation; late persistence cannot reopen runtime/Test. Started owners and subscriptions are cleaned up, including assertion-failure paths. |

Fixtures keep production sharing Off and stop their owners. No live app launch,
profile/window manipulation, EVE logfile modification, credential use or relay
activation was performed. Native rendering/timing cannot be inferred from
these doubles, and bounded-count tests are not latency benchmarks.

### Test-first and review evidence

Feature tasks used test-first development. Integrated coverage added after those
tasks already passed existing behavior; its initial import/fixture mistakes were
**not** counted as production RED evidence.

The first full run found **4 failed, 10,655 passed, 11 Windows-only skips**.
All four failures reproduced independently and were corrected as test-contract
adaptations, not hidden by skipping tests. Scoped coverage then passed.

Review and polish caught control-intent/recovery races, inner CSS overflow,
a test-owned worker leak, navigation reconciliation, and split UTF-8. Each
behavioral correction had a discriminating failing regression before its fix.
The final combined wave specifically reproduced **11 Node failures and nine
Python failures**, then passed **75 Node cases and 501 focused pytest cases**.
Whole-branch review plus scoped rereviews cleared all reported Important
findings. No source change followed the final verified revision.

## Final automated verification

All commands below ran from the linked checkout on Linux at source `28e6f6e8`.
The locked development environment and built release codec were installed before
testing. The installed codec was checked byte-for-byte against its release
build; `codec_available()` was true. Node was **v26.5.0**.

```bash
UV_PROJECT_ENVIRONMENT=/tmp/wingman-custom-alerts-plan-venv uv run --no-sync python -m pytest tests/ -q -rs --basetemp=/tmp/wingman-custom-alerts-parent-final-fixed --junitxml=/tmp/wingman-custom-alerts-parent-final-fixed.xml
UV_PROJECT_ENVIRONMENT=/tmp/wingman-custom-alerts-plan-venv uv run --no-sync ruff check .
UV_PROJECT_ENVIRONMENT=/tmp/wingman-custom-alerts-plan-venv uv run --no-sync ruff format --check .
node --check wingman/web/alerts.js
node --check wingman/web/dev.js
node scripts/test_alerts_runtime.js
node scripts/js_smoke.js
cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml --target-dir /tmp/wingman-custom-alerts-codec-target
node .superpowers/sdd/custom-gamelog-alerts-plan/browser-check.cjs
git diff --check
```

| Gate | Actual final result |
| --- | --- |
| Full pytest | **10,673 passed, 11 skipped in 411.24s**; zero failures/errors. |
| JUnit inspection | **10,684 cases**; all 11 skips require Windows; no Node/native-codec skips. |
| Repository Ruff check / format | Passed; **378 files already formatted**. |
| JS syntax | Both production-module syntax checks passed. |
| Executing Alerts Node harness | **75/75 passed**. |
| Executable JS smoke | Every module of index, Fleet Bar and Sig Bar loaded. |
| Cargo regression | **1 passed**, zero failed/ignored. |
| Browser | **20 scenario/viewport checks passed**, no page/console errors. |
| Whitespace | `git diff --check` passed. |

Earlier Ruff LSP checking of ten changed backend/runtime files returned zero
diagnostics; this was lint, not a separate Python type-checker. Final repository
Ruff was rerun after the last source correction.

### Inspected Windows-only skips

| Location | Count | Reason |
| --- | ---: | --- |
| `test_evesettings_profilecopy.py:279,318,650` | 3 | Real Windows junction. |
| `test_eveskills_dpapi.py:45` | 1 | Real DPAPI. |
| `test_eveskills_dpapi.py:52` | 1 | Real WinDLL. |
| `test_preview_host.py:1361` | 1 | Real message pump/window station. |
| `test_preview_win32.py:147,162,186` | 3 | user32/gdi32/dwmapi bindings. |
| `test_ui_setup_profile.py:458` | 2 | Real Windows junction, for `core_char_31.dat` and `prefs.ini`. |

## Browser evidence — not native acceptance

The temporary runner above executed from the SDD workspace. Its runner,
`browser-report.json` and screenshots were retained locally at
`/tmp/wingman-custom-alerts-browser-evidence/` before removing that plan's
orchestration workspace. These are session artifacts, not shipped files.
The final report identifies source `28e6f6e8`, **Chrome/152.0.7977.64**,
`ok: true`, 20 checks and `errors: []`. An isolated browser context served the
actual dev page over loopback, blocked external requests and was cleaned up.
The shared browser/profile and existing tabs were not closed or altered.

At both **840×625** and **839×621**, device scale factor 1, checks cover `full`,
`literal`, `custom-only`, `master-off`, `reader-error`, `no-characters`, `waiting`,
`degraded`, `failed-save`, and failed-initial-read Retry recovery. Retry performs
fresh state reads with zero mutation calls. Screenshots were inspected for the
expanded editor and representative states.

The expanded eight-row editor's cooldown is 120px wide and ends at the card
content edge, 795px. Settings scroll/client widths are **626/626** and **625/625**.
The original document-width check missed an inner horizontal overflow; the
strengthened check measures each editor control against card content and checks
ancestor scrollports. Cancel restores focus to the row's Edit button.

This is not evidence of WebView2 scaling, actual audio/native focus/rings, a full
keyboard/screen-reader pass, measured contrast, or live EVE behavior. Node
coverage of dynamic/async workflows is separate from rendered browser evidence.

## Reviewer focus and knowledge check

Concentrate on committed publication, custom-only admission, source/activation
fences, current-authority UI reconciliation and real native acceptance.

1. Why must the prepared Preview/alert composite be published only after persistence succeeds?
2. How do custom admission bounds preserve ordinary Fleet traffic while enforcing one audible batch winner?
3. Which identities and close gates reject stale matches between reading a line and native arming?
4. Why can a fresh owned authority read reconcile a checkbox while preserving newer text, and why is a health poll insufficient?
5. Which decoder reset and native acceptance boundaries are not established merely by a passing Node harness?

## Remaining acceptance gates

- [ ] Ubuntu and Windows CI, including codec and packaging/import regressions.
      Local Linux results do not prove a Windows CI pass.
- [ ] Real Windows/WebView2 acceptance: complete every item in
      [the custom-alert checklist](smoke-checklist.md#custom-gamelog-alerts--windowswebview2-acceptance-gate).
      Record operator/date/build, OS/WebView2 versions, scaling, focus, ring/audio,
      and shutdown results. No such native results were obtained in this session.
- [ ] Final release acceptance after those results. Do not mark it complete from
      Linux, Node or Chromium evidence alone.
