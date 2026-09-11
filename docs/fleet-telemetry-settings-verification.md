# Fleet telemetry Settings — implementation and verification

## Scope and worktrees

Wingman: `/mnt/c/dev/flygd-wingman/.worktrees/fleet-telemetry-settings`, branch
`ui/fleet-telemetry-settings`, based on freshly fetched upstream main `491bfd59`
(`Make Fleet Bar threat-first and horizontally resizable (#204)`). The earlier
[design](fleet-telemetry-settings-design.md) was written at `04e9e9b9`; the
implementation includes the newer Fleet Bar Reset width control.

Separate authGD copy patch: `/home/tng/workspace/authGD-fleet-telemetry-copy`, branch
`fix/fleet-telemetry-settings-copy`, based on `1abe5f8f926aa5a4289c3283079ef85d168fe727`.
Existing primary checkouts and worktrees were preserved; no live fleet state was
changed. The authGD patch remains separate from the Wingman PR. Neither patch
was deployed or released.

Before PR review the Wingman branch was fast-forwarded again to current upstream
`3143d2c5c14b81756c0abe15c51bd0a8535e2788` (#205, test-only changes). Those changes
were disjoint from this patch and preserve #204's native Fleet behavior.

## What changed and why

- Settings → Fleet telemetry now holds separate local Fleet Bar and Fleet sharing
  cards. Client previews, layouts, crops, cycling, and keybinds remain in Previews.
  The final scope correction extracts the independent Fleet Bar controller into
  `fleet.js`, loaded before `previews.js`. It retains its single boot hydration
  and status-strip handler even while Settings is closed. The new shortcut uses
  the same section event contract as the rail, disarming capture before entry.
- EVE-gated sections are checked at selection as well as rail visibility, so
  direct links and remembered-section entry cannot reopen hidden configuration.
- Source observations, local failures, pending commands, and in-flight bridge
  requests reconcile into case-insensitive keyed rows. Only settled ended rows
  enter Previous attempts; its count is derived from the actual history rows.
  Local failed Starts are not invented as server-ended history.
- Ended-only setups show reported reasons and prerequisite-aware next actions
  outside history, without inventing event chronology. Unknown current state
  retains same-binding last-known observations, not authorization. An
  authoritative empty snapshot replaces observations; binding changes discard
  old identity-bound observations and request feedback.
- Source request completion is processed even after section exit. Worker
  pending stages remain distinct from bridge queue acceptance. Selected boss,
  disclosure state, and correctly positioned keyed rows survive updates; focus
  moves to the history summary when a focused source settles into history.
- Wingman guidance and authGD's three affected pages now name Fleet telemetry.
  Python source changes are only the navigation guidance string and a placement
  comment. No worker, protocol, consent, journal, or native-window behavior changed.

## Integration boundary with the #204 follow-up session

Current upstream was re-fetched and confirmed as
`491bfd59c1a977dd6de4635aaaf4206dfaeba252` after the scope correction. No separate
follow-up worktree/ref was identifiable in the registered Wingman worktrees at
that first check. A subsequent check found `fix/fleet-bar-shared-compat` at
`/mnt/c/dev/flygd-wingman/.worktrees/fleet-bar-shared-compat`, also based on
`491bfd59`, with no working-tree changes at inspection time. This patch does not
merge or modify that session's branch; the overlap map below is the integration
boundary.

Overlapping files are intentionally limited:

- `previews.js`: remove the complete local Fleet Settings/status-strip IIFE into
  `fleet.js`; retain the new Fleet Settings shortcut and ordinary capture release.
  Any later changes to that controller should target `fleet.js`, not recreate it
  in `previews.js`.
- `index.html`: move the two Fleet cards intact, including `#fleetbar-reset`,
  register `fleet.js` before Previews, and add navigation/history markup.
- `ui/api.py`: only change the Settings guidance string. Preserve all new window
  callback signatures and implementations during integration.
- `tests/test_fleet_bar.py`: retarget two lexical controller-source lookups from
  `previews.js` to `fleet.js`, and replace the old same-file ordering assertion
  with the `fleet.js`-before-`previews.js` script order. Native runtime tests are
  unchanged here; the follow-up session is editing that same test file in its
  separate worktree, so preserve both sets of disjoint hunks when integrating.
- `scripts/test_previews_fleetbar_runtime.js` and its pytest wrapper: keep existing
  filenames to avoid CI/sibling rename conflicts, but execute the whole new
  controller and extend hydration/reset/closed-section toggle coverage.

Settings still calls tokenless `reset_fleet_bar_width`. The floating page still
uses token-bound `reset_fleet_bar_page_width`, `hide_fleet_bar`, activation and
deactivation, height-fit and resize lifecycle contracts. No fixed 420px behavior
or removed `fit_fleet_bar`/`move_fleet_bar` methods are restored. Saved preferred
content width remains default 500px and bounded 420–720px without format changes.

The mixed-row DPS alignment, obsolete height-fit retry, monitor-clamp preferred
width, and authGD joint-proof adapter/revision-pin fixes belong exclusively to the
other session. This patch leaves `wingman/ui/fleetbar.py`, `wingman/ui/chrome.py`,
`wingman/web/fleetbar.js`, `wingman/web/fleetbar.html`, native runtime/measurement
scripts, and authGD proof/adapter files unchanged from its base.

## Review and corrections

Independent design review accepted the approach after two clarifications:
case-insensitive source identity and connection-scoped retained state.

The post-implementation polish pass found two concrete UI issues, both reproduced
with failing regression tests and fixed:

1. Repainting after a rejected old preference payload must use `paint()`, not
   reaccept cached state via `render(state)`, which cleared failed-read authority.
2. A native select drops values absent from its current options. The desired boss
   is now retained separately through unknown reads, revalidated against the next
   authoritative roster, and cleared on binding change or confirmed removal.

A focused independent recheck found neither issue remaining:
**2 passed, 27 deselected in 4.09s**. No unrelated auto-refactoring was applied.
One old lexical test expected three Preview scroll shortcuts; it now checks the
remaining two local targets. The Fleet shortcut has executable section/capture
coverage instead.

The extraction received a focused independent polish review with **no findings**:
at that checkpoint its complete IIFE body equalled #204, and only one
`onFleetBarState` registration and one `fleet_bar_settings` boot fetch remained.
The later CodeRabbit-driven local row-reconciliation fix below is the only
behavioral change to that extracted controller. The new controller harness passed
**7/7** cases. The review's broader selection passed **412 tests** with **one
unbuilt-codec skip**; that was not a full-suite run or native acceptance. The
parent's final scoped verification below has no skips.

## Pre-PR review findings

CodeRabbit reviewed all then-changed files with:

```bash
coderabbit review --uncommitted --include-untracked --agent
```

It returned three findings, representing two distinct concerns:

- **Local character focus (major and duplicate minor): valid.** Unconditional
  reparenting of group headings and character rows discarded native checkbox
  focus on an unchanged heartbeat. This was reproduced in actual Chromium and
  in the complete controller harness, then corrected with position-aware
  reconciliation of both headings and rows. No native geometry or callback
  behavior changed.
- **Missing rejected-promise cleanup in source actions (major): false positive.**
  `WM.send()` catches underlying bridge rejections and resolves `null`; source
  action completion already removes its request and reports that failure. The
  new `bridge-source-rejection` regression rejects actual Start and Stop bridge
  calls under the real `app.js` wrapper and confirms cleanup and visible failure
  feedback: **1 passed, 29 deselected in 3.06s**. No redundant catch was added.

The full suite also caught the new section's missing screenshot registry entry.
`Screen("settings-fleet", ...)` was added to the existing registry; the whole
screenshot test module then passed **82 tests in 6.38s**. No new screenshot
fixture data was introduced outside `dev.js`.

## Automated Wingman verification

Commands below ran from the Wingman linked worktree. The existing development
virtualenv supplied the interpreter/tools; tests imported this worktree's source.

```bash
PYTHONDONTWRITEBYTECODE=1 /mnt/c/dev/flygd-wingman/.venv/bin/python -m pytest \
  tests/test_*fleet*.py tests/test_settings_page.py tests/test_characters_page.py \
  tests/test_settings_eve_gate.py tests/test_preview_wiring.py \
  tests/test_page_conventions.py tests/test_bridge_contract.py \
  tests/test_js_smoke.py tests/test_dev_harness.py tests/test_critique_flow_ui.py \
  tests/test_new_screenshots.py -q -rs -p no:cacheprovider
```

**2005 passed in 135.35s; no skips**, after the final controller extraction and
updated cross-module ordering guard. This includes Fleet API/runtime subscription
and pending-command ownership, sharing transport/state, local Fleet controls,
bridge contracts, page conventions, shell navigation, and executable JS tests.
The full repository pytest suite and independent settings-codec Cargo tests were
not run; no codec/native source changed. This is scoped coverage, not a full-suite
claim.

```bash
/mnt/c/dev/flygd-wingman/.venv/bin/ruff check .
/mnt/c/dev/flygd-wingman/.venv/bin/ruff format --check .
node scripts/test_previews_fleetbar_runtime.js
node scripts/js_smoke.js
git diff --check
```

Final results: **lint passed; 382 files already formatted; 7/7 complete Fleet
controller runtime cases passed; all page modules loaded; whitespace check
passed**. Focused frozen-web-tree packaging coverage also passed
**1 test, 87 deselected** without requiring a native codec. A formatting-only correction to the old
shortcut test was followed by **6 passed in 1.22s** for that file. No production
code changed after the 2005-test run.

Tests-first evidence includes the navigation red (**4 failed, 38 passed**) then
**42 passed**, source-history behavioral red (**12 failed, 12 passed**) and later
edge-case reds, plus the two review regressions (**2 failed**, then **2 passed**).
The final focused sharing page/hydration run passed **31 tests in 6.74s**.

## Rendered browser evidence — not Windows/WebView2 acceptance

An isolated headless Google Chrome profile loaded the actual
`wingman/web/index.html?dev=1` via `file://`, driven with installed
`puppeteer-core` from the browser-tools environment. No dependencies were added
to Wingman. HTTP requests were blocked during this browser pass; all fabricated
rendered data came from `dev.js`, never a live relay.

```bash
node /tmp/fleet-telemetry-browser.cjs
```

The final script passed at **840×625** and **839×621** CSS pixels (DPR 1), with no
page exceptions or horizontal overflow of the document or Settings pane. It
exercised:

- One active source and two expired historical attempts; ended-only visible
  reason/next action; hidden empty disclosure.
- Native Space/Enter disclosure interaction, open-state persistence, active
  Stop focus through heartbeats, and focus fallback on history settlement.
- Long and unbroken character names, visible controls, and scrolling.
- Mixed-case pending Start/Stop precedence over ended observations.
- Failed Refresh, unknown/unavailable state, same-binding native-select recovery,
  and binding-change clearing.
- Held Start/Stop replies across navigation; pending feedback until completion.
- Actual Preview/Bookmark capture buttons followed by shortcut/rail navigation:
  Tab and printable keys were not captured, and no bind/activation write escaped.
- Remembered Fleet section and EVE gate/deep-link behavior.
- Global status-strip toggle while Settings is closed still synchronizes the
  Settings checkbox without a sharing mutation. Settings Reset calls the
  tokenless endpoint with no arguments and does not toggle the bar.

Screenshots were visually inspected. Local temporary artifacts (not shipped):

- `/tmp/fleet-telemetry-local-840x625.png`
- `/tmp/fleet-telemetry-local-839x621.png`
- `/tmp/fleet-telemetry-840x625.png`
- `/tmp/fleet-telemetry-839x621.png`
- `/tmp/fleet-telemetry-ended-840x625.png`
- `/tmp/fleet-telemetry-ended-839x621.png`

The stale-preference/failed-Refresh combination is an executable DOM/bridge
regression; the dev preference completer issues a new version, so its browser
exercise is not falsely described as proving the stale-reply case.

## Separate authGD copy verification

The authGD agent reported and the parent inspected the five-file copy-only diff:

- `src/app/account/fleet-devices/page.tsx`
- `src/app/account/fleet-sharing/page.tsx`
- `src/app/fleet/pair/[id]/page.tsx`
- `e2e/fleet-devices.spec.ts`
- `e2e/fleet-access.spec.ts`

Verification performed there:

```bash
npm run test:e2e -- e2e/fleet-devices.spec.ts e2e/fleet-pair.spec.ts
E2E_FLEET_INTEGRATIONS=1 npm run test:e2e -- e2e/fleet-access.spec.ts \
  -g 'normal account keyboard journey'
npm run format:check
npm run typecheck
npx eslint src/app/account/fleet-devices/page.tsx \
  src/app/account/fleet-sharing/page.tsx 'src/app/fleet/pair/[id]/page.tsx' \
  e2e/fleet-devices.spec.ts e2e/fleet-access.spec.ts
git diff --check
```

**11 E2E tests passed**, plus **1 integration-enabled keyboard journey passed**;
format, typecheck, changed-file ESLint, and whitespace checks passed. An updated
copy assertion failed before production text was changed. Independent polish
found no issues in the authGD patch. Full authGD suites were not run.

Tests used a new worktree-specific test database/container, not live state. The
parent stopped that container after verification:
`authgd-e2e-authgd-fleet-telemetry-c-90c9f4` (test port 5894). It was not deleted.
`npm ci --ignore-scripts` reported seven existing dependency vulnerabilities;
these were not changed as part of a copy-only patch.

## Remaining manual acceptance

- Installed Windows/WebView2 keyboard capture release, native select/disclosure
  focus, and real frameless-window scaling at 100/125/150/200%.
- Local floating Fleet Bar show/hide, Reset width, and character visibility in
  the installed app; opening/leaving Fleet telemetry must not affect verification
  or sharing runtime ownership.
- Separately authorized real pairing/Fleet Read/relay acceptance, if required for
  release. This task did not repeat or claim that live acceptance.

Use the updated Fleet telemetry section of `docs/smoke-checklist.md`. Chromium
and DOM doubles do not prove these native/installed acceptance items.

## Changed Wingman files

- `wingman/web/app.js`
- `wingman/web/index.html`
- `wingman/web/previews.js`
- `wingman/web/fleet.js` (new, extracted controller)
- `wingman/web/fleetsharing.js`
- `wingman/web/dev.js`
- `wingman/web/style.css` (placement comment only)
- `wingman/ui/api.py` (guidance copy only)
- `wingman/settings.py` (placement comment only)
- `scripts/shoot_screens.py`
- `scripts/test_previews_fleetbar_runtime.js`
- `tests/test_previews_fleetbar_runtime.py`
- `tests/test_fleet_bar.py` (controller-source lookups only)
- `tests/test_settings_page.py`
- `tests/test_characters_page.py`
- `tests/test_critique_flow_ui.py`
- `tests/test_fleetsharing_hydration.py`
- `tests/fixtures/fleetsharing_page.cjs`
- `tests/test_fleet_navigation.py` (new)
- `tests/fixtures/fleet_navigation.cjs` (new)
- `AGENTS.md` (module ownership/order)
- `README.md`
- `PRODUCT.md`
- `DESIGN.md`
- `docs/smoke-checklist.md`
- `docs/fleet-telemetry-settings-design.md` (new)
- `docs/fleet-telemetry-settings-verification.md` (this document)
