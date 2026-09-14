# #212 implementation notes

Baseline: `d6fbd776a36481dc2d02db6204d4f2973a471592`, branch
`feature/preview-hide-active`. Behavior follows the approved
[design](preview-hide-active-design.md), whose independent opinion was SHIP/NONE.

## Final engineering verification — PASS

Reviewed and full-tested source/test commit:
`9b09030a0769482ad4514a972187306eb487c7cb`.
The final documentation-only corrections are separately inspected and are not
represented as CodeRabbit-reviewed bytes.

- Independent review and `/polish --fix` covered the complete24-file delta,
  including current-file EOF reads and the five correction files. GA212-1 was
  corrected and independently re-reviewed as CLOSED, with old/current native-show
  differential proof. No unresolved change-specific review findings remain.
- Actual CodeRabbit CLI ran once on that commit against the feature base and
  completed all24 files with two findings. Its major request for another checkbox
  rejection handler was **not applicable**: production `WM.send` already logs and
  converts rejected promises, synchronous exceptions and missing methods to null.
  The checkbox then drains pending, rolls back its owned value and keeps its queue
  alive. Independent review and a fresh coordinator probe using the actual bridge
  plus field IIFE confirmed this, including a rejected write followed by success.
  No redundant production catch was added.
- CodeRabbit's minor stale-design-status finding was valid. The approved strategy
  heading and obsolete phase wording now point to revision-specific results here.
  Design semantics are unchanged. There were no external-review retries, light
  mode or credits overrides; no review ID was emitted.
- Fresh coordinator full suite after external review: **12474 passed,13 skipped
  in330.58s**. Parsed JUnit:12487 total, zero failures/errors. Every skip identity
  and reason matches the earlier full gate and requires Windows; none is a Node
  or codec prerequisite skip.
- Fresh Ruff lint/format **437 files**, all three changed JS syntax checks,
  all-page Node smoke, whitespace checks and independent locked Cargo regression
  (**1 passed**) succeeded.
- The existing private Chrome14-check result applies to the unchanged UI; the
  follow-up production change was native host publication only. It is not a
  browser test of native timing. Real Windows/WebView2/DWM/DPI/EVE acceptance
  remains NOT RUN.

Exact coordinator commands from this linked checkout:

```bash
coderabbit review --agent --committed --base-commit d6fbd776a36481dc2d02db6204d4f2973a471592
unset PYTHONPYCACHEPREFIX
PYTHONDONTWRITEBYTECODE=1 /tmp/wingman-preview-hide-active-venv/bin/python -B -m pytest tests/ -q -rs --tb=short -p no:cacheprovider --basetemp=/tmp/wingman-preview-hide-active-final-9b09030a-coordinator --junitxml=.superpowers/sdd/preview-hide-active/post-review-final/full.xml
/tmp/wingman-preview-hide-active-venv/bin/ruff check --no-cache .
/tmp/wingman-preview-hide-active-venv/bin/ruff format --check --no-cache .
node --check wingman/web/settings.js
node --check wingman/web/dev.js
node --check scripts/test_settings_runtime.js
node scripts/js_smoke.js
cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml --target-dir /tmp/wingman-preview-hide-active-cargo
git diff --check d6fbd776..HEAD
```

Node26.5.0, Python3.11.15, editable Wingman5.6.3 resolving this checkout, and this
checkout's installed release codec availability/path were freshly verified.
All pytest data stayed under case-sensitive Linux `/tmp`, with bytecode/cache
creation disabled. Evidence lives in the ignored `post-review-final/` directory,
plus `coderabbit-9b09030a.log`, `coderabbit-report.md` and the actual bridge probe
output `coderabbit-bridge-check.log`. Earlier failures remain retained below.

Main advanced through tray-DPI PR229 to
`529cb9ed8a29af1a44c5469053cda15d04ba1ad8` during review. This branch was not silently
rebased or merged: its verified base remainsd6fbd776. Combined-tree CI/browser
acceptance must be distinguished from these branch results at publication.
No PR, merge, issue closure or native acceptance is implied by this record.

## Historical GA212-1 review correction — scoped verification

The follow-up to `629bca93d1660eac580ee08db7d3f6780a174d06` corrects a stale
foreground sample at primary publication. `_apply_selection` sampled A before
native focused/selected painting; the real foreground hook could observe B during
that paint, but the old nonzero argument still hid A and initially showed B's
primary and label. `PreviewHost._apply_visibility(libs)` now resolves current
`self._foreground` at publication. Both production callers and the existing test /
prototype override callers were updated; no unused sample argument remains.
Selection/alert bookkeeping, zero/no-hook fallback, EVE epoch fences and crop
policy/authority are unchanged. `host.py` is the only changed production file.

Seven new cases invoke the actual installed foreground callback during production
selection's native layered-paint seam and assert primary **and label ShowWindow
destinations**. They cover newer nonzero, zero fallback/unresolved, option-Off,
lost-focus client/stranger/Wingman, unchanged selection bookkeeping and no PID
probe with lost-focus hiding disabled. On unchanged production, six failed and
option-Off passed; Bob's primary+label handles appeared in native show records
when the expected set was empty. The assertion order was changed only to print
Bob's unwanted shows first; both RED artifacts were preserved. After correction:
123 targeted tests passed, then **1,558 related tests passed with one Windows-only
message-pump/window-station skip** in 41.69s. Ruff lint/format (437 files) and
all-page Node smoke passed.

```bash
unset PYTHONPYCACHEPREFIX
export PYTHONDONTWRITEBYTECODE=1 UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-hide-active-venv
uv run --no-sync python -m pytest tests/test_preview_hide_active.py -k foreground_hook_during_selection_paint -q --tb=short -rs -p no:cacheprovider --basetemp=/tmp/wingman-preview-hide-active-review-fix1-red-destinations --junitxml=.superpowers/sdd/preview-hide-active/review-fix-1/red-destinations.xml
uv run --no-sync python -m pytest tests/test_preview_hide_active.py tests/test_preview_crop_harness.py -q --tb=short -rs -p no:cacheprovider --basetemp=/tmp/wingman-preview-hide-active-review-fix1-green --junitxml=.superpowers/sdd/preview-hide-active/review-fix-1/green.xml
uv run --no-sync python -m pytest tests/test_preview_hide_active.py tests/test_preview_host.py tests/test_preview_window.py tests/test_preview_visibility.py tests/test_preview_cropcontroller.py tests/test_preview_cropwindow.py tests/test_preview_crop_harness.py tests/test_preview_metadata.py tests/test_settings.py tests/test_settings_preview.py tests/test_settings_committed_preview.py tests/test_settings_hide_active.py tests/test_preview_wiring.py tests/test_preview_runtime*.py tests/test_settings_runtime.py tests/test_page_conventions.py tests/test_bridge_contract.py tests/test_js_smoke.py -q --tb=short -rs -p no:cacheprovider --basetemp=/tmp/wingman-preview-hide-active-review-fix1-focused --junitxml=.superpowers/sdd/preview-hide-active/review-fix-1/focused.xml
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
node scripts/js_smoke.js
```

All data stayed under fresh Linux `/tmp` basetemp, caches/bytecode disabled;
XML/logs are retained under ignored `review-fix-1/`, with the complete command and
failure ledger in `review-fix-1-report.md`. The dedicated environment, checkout
imports, release codec and Node were reconfirmed. **No full-suite or browser run
was performed for this native-only correction**, per coordinator scope. The
12,467-pass full suite recorded below applies to `629bca93`, not this follow-up.
Fresh full verification follows scoped re-review and CodeRabbit under coordinator
ownership. Windows/native/WebView2/EVE acceptance remains NOT RUN.

## Boundaries and decisions

- `preview.hide_active_preview` defaults off and accepts only booleans. No
  migration/version bump. The new endpoint uses the existing serialized writer,
  and restyles only after an applied, persisted receipt. Host callbacks and the
  top-level `preview_hide_active_preview` hydration value read committed state.
- The existing foreground/selection path composes global lost-focus hiding with
  exact source-HWND hiding. Zero/unknown foreground never nominates a source.
  Sticky rings and pending activation targets are not policy inputs. The global
  mask remains global; excluded sources still independently govern their crops.
- Host primaries prepare hidden, including their labels, then explicitly reveal
  eligible windows even with the preference off. Epoch checks between reveals
  and a defaulted primary/label authority callback prevent Off during a native
  show from revealing later windows. Standalone creation defaults stay compatible.
- The production crop controller creates hidden, checks current session/runtime
  authority and supplies current presentation separately. `CropWindow.set_hidden`
  reevaluates that supplier **after DWM preparation, immediately before native
  show**. A suppressed committed crop remains live and consumes capacity; hiding
  is not failed admission. Candidates retain existing transaction authority.
- Existing `.check`, hint and field-local live region; ordered rapid writes,
  initial hydration gate and last-acknowledged rollback. No new CSS, route, clock,
  queue, worker or general visibility framework. No source-window geometry,
  companion, alert, cycle or Wanderer eligibility change.

## Actual verification

Commands ran from the linked worktree with:

```bash
unset PYTHONPYCACHEPREFIX
export PYTHONDONTWRITEBYTECODE=1
export UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-hide-active-venv
uv sync --locked --extra dev
cargo build --locked --release --manifest-path packaging/settings-codec/Cargo.toml --target-dir /tmp/wingman-preview-hide-active-cargo
# Installed that release binary into this checkout's ignored packaging/bin.
```

Python 3.11.15; editable Wingman 5.6.3 imports verified this checkout; Node v26.5.0.
The bundled resolver and `codec_available()` were verified before baseline and
full pytest. Installed release SHA-256:
`4a4b57f48829002be1aff6eda8193f9e1fb8257a9bef5666dd26b0e225e815b4`.
All pytest data used fresh Linux `/tmp` basetemp and `-p no:cacheprovider`; XML and
browser evidence remain in ignored `.superpowers/sdd/preview-hide-active/`.

| Evidence | Result |
| --- | --- |
| Unchanged focused baseline | 1,348 passed, 1 Windows-only skip |
| Initial native/policy/wiring RED | 18 failed, 9 missing-interface errors |
| Native/production-crop first GREEN | 137 passed |
| Settings RED | 21 failed, 2 passed; absent setting/endpoint plus corrected minimal-fixture setup |
| UI RED | Five new Node cases failed; existing 73 passed |
| Mutation RED | Four native-show failures when hidden-at-birth/post-DWM masking were removed; three authority cases still passed |
| EVE epoch RED | Later primary showed after first native reveal revoked admission |
| Final expanded focused | 2,885 passed, 5 Windows-only skips, 92.03s |
| Private Chrome | 14 checks, four screenshots, zero errors at 840×625 and 839×621 |
| Ruff lint / format | Passed; 437 files formatted |
| All-page Node smoke | Passed, all three pages |
| Independent Cargo regression | 1 passed, 0 failed/ignored |
| Initial full pytest (retained failure) | 12,466 passed, 13 Windows-only skips, 1 expected-defaults failure, 332.07s |
| Authorized fresh full gate after correction | **12,467 passed, 13 Windows-only skips, 0 failures/errors**, 339.42s |

Final expanded focused command:

```bash
uv run --no-sync python -m pytest tests/test_preview*.py tests/test_settings_hide_active.py tests/test_settings_preview.py tests/test_settings_committed_preview.py tests/test_settings_runtime.py tests/test_settings_page.py tests/test_page_conventions.py tests/test_bridge_contract.py tests/test_js_smoke.py tests/test_dev_harness.py tests/test_wanderer_integration.py tests/test_wanderer_companion_integration.py -q --tb=short -rs -p no:cacheprovider --basetemp=/tmp/wingman-preview-hide-active-focused-final --junitxml=.superpowers/sdd/preview-hide-active/focused-final.xml
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
node scripts/js_smoke.js
node .superpowers/sdd/preview-hide-active/browser.cjs
uv run --no-sync python -m pytest tests/ -q -rs -p no:cacheprovider --basetemp=/tmp/wingman-preview-hide-active-full --junitxml=.superpowers/sdd/preview-hide-active/full.xml
cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml --target-dir /tmp/wingman-preview-hide-active-cargo
```

The sole full-suite failure was the literal expected-defaults table in
`tests/test_settings.py`, missing the approved new false key. That in-scope
consumer was corrected without changing production code. The worker stopped and
made no commit over that failed gate. The correction's focused gate passed
**406 tests with no skips** in 17.88s, followed by Ruff lint/format and
`git diff --check`. The coordinator independently verified that evidence and
explicitly authorized one fresh full gate in `defaults-gate-ruling.md`.

That fresh gate passed **12,467 tests, 13 Windows-only skips, no failures/errors**
in 339.42s; JUnit independently confirms 12,480 total cases. Fresh Ruff lint,
format (437 files), all-page Node smoke and Cargo (1 passed, none failed/ignored)
also passed. No production or test code changed in this gate-only continuation.
Original `full.xml` and `defaults-correction.xml` remain byte-for-byte unchanged.

```bash
# Same dedicated environment and cache/bytecode isolation as above; new artifacts.
set -o pipefail
uv run --no-sync python -m pytest tests/ -q -rs -p no:cacheprovider --basetemp=/tmp/wingman-preview-hide-active-full-gate2 --junitxml=.superpowers/sdd/preview-hide-active/gate2-full.xml 2>&1 | tee .superpowers/sdd/preview-hide-active/gate2-full.log
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
node scripts/js_smoke.js
cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml --target-dir /tmp/wingman-preview-hide-active-cargo
sha256sum -c .superpowers/sdd/preview-hide-active/gate2-production-before.sha256
sha256sum -c .superpowers/sdd/preview-hide-active/gate2-retained-evidence.sha256
```

All 11 production SHA-256 values were recorded before the fresh run and rechecked
afterward. The manifest `gate2-production-before.sha256` has SHA-256
`abf340a15187a8a547616d99b669196c2217a3b3e616886ee643b9ab3ef2ca03`;
individual source hashes and exact command/result history are in the ignored
implementation report. Environment/import/Node and the installed release codec
were reconfirmed before testing. Browser evidence was not repeated because all
production bytes stayed unchanged. The local commit containing these notes is
the worker handoff; coordinator review/polish/CodeRabbit/final gate remain separate.

Earlier focused failures were causal test-native seams: older host doubles lacked
`set_hidden`, and metadata's real-window native double lacked `ShowWindow` now
that creation is hidden. Those seams now record the operation; no visibility
assertion was removed or production fallback added for tests. The minimal API
fixture needed committed normalization before its blocked-save scenario. The
initial browser driver scrolled the invisible input rather than its visible label;
visible-label clicks plus keyboard Space fixed the driver, not product CSS.
Original failed XML/browser evidence is retained.

## Remaining acceptance

All 13 full-suite skips were inspected: profile/setup Windows junctions (5),
DPAPI/WinDLL (2), native preview message pump (1), Win32 bindings (3), Windows tray
backend (1), Wanderer real DPAPI (1). No Node/codec skip. Browser checks use a
private temporary profile, loopback dev page and controlled bridge replies, not a
user browser/app/EVE/clipboard/settings. No image exploration was needed for the
approved existing-component checkbox. Screenshots show the intended control,
local refusal, focus ring and hint fitting both floors without new visual defects.

Windows native focus/DWM/WebView2/DPI/live-EVE acceptance remains **NOT RUN**;
[smoke checklist](smoke-checklist.md#hide-the-active-eve-clients-previews-212--windows-acceptance-not-run)
is the operator contract, not an acceptance claim. Coordinator independent
review/polish/CodeRabbit/final gate and all publication decisions remain separate.
