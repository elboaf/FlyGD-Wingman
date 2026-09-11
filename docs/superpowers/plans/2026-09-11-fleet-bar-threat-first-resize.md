# Fleet Bar Threat-First Resize Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a threat-first, horizontally resizable Fleet Bar whose preferred content width persists independently from monitor clamping and whose passive display never steals focus.

**Architecture:** Extend the existing frameless-window WndProc in `wingman/ui/chrome.py` with a horizontal-only policy. Persist WebView content width in settings, keep applied native geometry private to the Fleet Bar lifecycle, and separate user-owned width settlement from page-owned height fitting. Add token-bound page methods for resize, activation, deactivation, reset, and Hide while leaving telemetry and fleet-sharing protocols unchanged.

**Tech Stack:** Python 3.11+, ctypes/Win32, pywebview 6.2.1, plain HTML/CSS/ES5 JavaScript, Node `node:test`, headless Chromium over CDP, pytest, Ruff.

**Spec:** `docs/superpowers/specs/2026-09-11-fleet-bar-threat-first-resize-design.md`

## Global Constraints

- Width means WebView content width in logical CSS pixels. Bounds are 420 through 720 and the initial default is 500.
- Native outer width adds measured left and right resize insets exactly once.
- Monitor clamping never overwrites preferred content width.
- Only left and right edges resize; automatic fitting owns height only.
- Do not attach ordinary pywebview resize, move, or show event handlers.
- Preserve the 64-character lowercase-hex page-token gate for every standalone callback.
- Passive reveal retains `WS_EX_NOACTIVATE`; only an explicit header action can start an activation session.
- Never move or resize an EVE client window.
- Preserve local-first ordering, remote expiry and takeover, protocol v1, and exact DPS semantics.
- Keep every non-method `Api` attribute underscore-prefixed.
- Add no framework, bundler, runtime dependency, browser dependency, worker, or pywebview upgrade.
- Follow TDD for every behavior: failing test, observed expected failure, minimal implementation, passing focused tests, then commit.

## Final Interfaces

```python
# wingman/settings.py
FLEET_BAR_MIN_CONTENT_WIDTH = 420
FLEET_BAR_DEFAULT_CONTENT_WIDTH = 500
FLEET_BAR_MAX_CONTENT_WIDTH = 720
```

`validated_fleet_bar()` produces `preferred_content_width: int` in addition to the existing enabled, position, seen, and hidden fields.

```python
# wingman/ui/chrome.py
ALL_EDGES = frozenset({"left", "right", "top", "bottom"})
HORIZONTAL_EDGES = frozenset({"left", "right"})

@dataclass(frozen=True)
class ResizeInsets:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def horizontal(self) -> int: ...

def enable_horizontal_resize(
    window,
    *,
    pad: int = INSET,
    min_content_width: int,
    max_content_width: int,
) -> ResizeInsets | None: ...
```

The existing `enable_resize(window, pad=INSET) -> bool` remains source-compatible and all-edge.

```python
# wingman/ui/fleetbar.py
def outer_width_for_content(content_width, insets) -> int: ...
def content_width_for_outer(outer_width, insets) -> int: ...
def activate_bar(bar, *, user32=None) -> int | None: ...
def deactivate_bar(bar, return_hwnd, *, main_hwnd=None, user32=None) -> bool: ...
def reveal_bar(bar) -> bool: ...
def hide_bar(bar) -> bool: ...
```

```python
# wingman/ui/api.py
def settle_fleet_bar_resize(self, page_id=None, content_width=None, x=None) -> dict | None: ...
def fit_fleet_bar_height(self, page_id=None, height=None) -> None: ...
def activate_fleet_bar(self, page_id=None) -> dict | None: ...
def deactivate_fleet_bar(self, page_id=None) -> None: ...
def reset_fleet_bar_page_width(self, page_id=None) -> dict | None: ...
def hide_fleet_bar(self, page_id=None) -> dict | None: ...
def reset_fleet_bar_width(self) -> dict: ...
```

Field results use `{applied: bool, persisted: bool, error: str | None}`.

## Task 1: Persist Preferred Content Width

**Files:**
- Modify: `wingman/settings.py`
- Test: `tests/test_fleet_bar_settings.py`

**Produces:** Validated and normalized `fleet_bar.preferred_content_width`.

- [ ] Add tests asserting a fresh document and an old document without the field resolve to 500.
- [ ] Add a parameterized test for 420, 500, 720, clamping 419/721, and rejecting booleans, strings, and `None` to the default.
- [ ] Add direct-save and load/save round-trip tests proving unknown or invalid values cannot bypass normalization.
- [ ] Run `uv run --no-sync python -m pytest tests/test_fleet_bar_settings.py -q`; confirm failures are caused by the missing field/constants.
- [ ] Add the three constants, default field, integer-only validation, and bounded normalization in `wingman/settings.py`. Absence migrates to the default without a settings-version bump.
- [ ] Run `uv run --no-sync python -m pytest tests/test_fleet_bar_settings.py tests/test_settings.py -q`.
- [ ] Commit with `feat: persist Fleet Bar preferred content width`.

## Task 2: Add Horizontal-Only Native Resize Chrome

**Files:**
- Modify: `wingman/ui/chrome.py`
- Test: `tests/test_chrome.py`
- Compatibility test: `tests/test_window.py`

**Produces:** Shared edge policy, `ResizeInsets`, and `enable_horizontal_resize()`.

- [ ] Add pure hit tests proving left/right middle and corners produce only `HTLEFT`/`HTRIGHT`, top/bottom produce no resize code, interior is unchanged, negative coordinates work, and the default all-edge behavior remains unchanged at 100/125/150/200% scales.
- [ ] Add attachment tests proving minimum/maximum outer track widths include left/right insets, vertical track bounds remain untouched, logical inset reporting tolerates one-pixel DPI rounding, and an inset is removed if WndProc installation fails.
- [ ] Run `uv run --no-sync python -m pytest tests/test_chrome.py -q`; confirm missing policy/API failures.
- [ ] Refactor the private attachment core to capture an edge policy. Keep `enable_resize()` all-edge and add `enable_horizontal_resize()` using left/right inset only.
- [ ] Chain the original WndProc before applying horizontal `WM_GETMINMAXINFO` bounds, retain callback keepalive, and prevent Python exceptions crossing the native message pump.
- [ ] Run `uv run --no-sync python -m pytest tests/test_chrome.py tests/test_window.py -q`.
- [ ] Commit with `feat: support horizontal-only frameless resize chrome`.

## Task 3: Separate Preferred Width, Applied Geometry, and Height Fit

**Files:**
- Modify: `wingman/ui/fleetbar.py`
- Modify: `wingman/ui/api.py`
- Test: `tests/test_fleet_bar.py`
- Test: `tests/test_api_remote_fleet.py`

**Produces:** Content/outer conversion, resize attachment, runtime applied geometry, resize settlement, Reset, and height-only fit.

- [ ] Add pure tests such as `outer_width_for_content(500, ResizeInsets(6, 0, 6, 0)) == 512` and the inverse. Add negative-monitor and narrow-work-area cases proving applied width/x clamp without changing preferred settings.
- [ ] Add creation tests proving the native title uses Fleet Bar, outer width adds insets, horizontal chrome receives 420/720 bounds, attachment finishes before page publication, and attachment failure publishes a fixed-width fallback without a stale inset.
- [ ] Add API tests proving `fit_fleet_bar_height(page, height)` preserves current outer width on every retry and aborts safely after replacement, disable, or shutdown.
- [ ] Add resize-settlement tests for right-edge width-only persistence, left-edge width+x persistence, one-pixel rounding, bounds, stale tokens, and persistence failure retaining session-applied width with a warning.
- [ ] Add Reset tests for visible and absent bars, monitor-edge re-clamp, native failure, persistence failure, and `fleet_bar_ready()` returning resize capability.
- [ ] Run the two focused files and confirm missing-helper/endpoint failures.
- [ ] Implement conversion and work-area helpers in `ui/fleetbar.py`; all rectangles remain logical and one named boundary adds/subtracts inset.
- [ ] Add underscore-prefixed resize state to `Api`, publish/reset it atomically with page identity, and implement height-only fitting and shared tokenless/token-bound Reset orchestration.
- [ ] Keep old fitting endpoints temporarily until the page migrates in Task 5.
- [ ] Run `uv run --no-sync python -m pytest tests/test_fleet_bar.py tests/test_api_remote_fleet.py tests/test_fleet_presentation_worker.py tests/test_api.py -q`.
- [ ] Commit with `feat: separate Fleet Bar width from automatic height fitting`.

## Task 4: Add Explicit Activation and Transactional Hide

**Files:**
- Modify: `wingman/ui/fleetbar.py`
- Modify: `wingman/ui/api.py`
- Test: `tests/test_fleet_bar.py`
- Test: `tests/test_startup.py`

**Produces:** Token-bound activation session and honest Hide outcomes.

- [ ] Add injected-`user32` tests proving activation records foreground, removes only `WS_EX_NOACTIVATE`, requests foreground, verifies success, and restores no-activate immediately on failure.
- [ ] Add deactivation tests proving no-activate is restored before guarded focus return, destroyed/unrelated HWNDs are ignored, and only the main Wingman HWND or an HWND matching the existing EVE title predicate is eligible.
- [ ] Add token/session tests for omitted, malformed, stale, replaced, and retired page IDs; repeated activation keeps the original return HWND; Reset retains the session; Escape/blur/Hide/replacement/shutdown end it once.
- [ ] Add the Hide matrix: persistence refusal; persist+hide success; native hide failure with successful persisted rollback; native hide failure with rollback persistence failure and session-only enabled state.
- [ ] Assert every branch publishes one authoritative visible runtime state to main-window controls and never changes fleet sharing.
- [ ] Run focused tests and confirm missing lifecycle behavior.
- [ ] Implement ctypes primitives beside existing tool-window helpers and orchestration under `_fleetbar_lifecycle_lock`; restore no-activate before any return-focus call.
- [ ] Factor both tokenless Off and token-bound Hide through one internal transaction. Return standard field results and verify native visibility rather than logging success blindly.
- [ ] Run `uv run --no-sync python -m pytest tests/test_fleet_bar.py tests/test_startup.py tests/test_fleet_presentation_worker.py tests/test_fleet_runtime_integration.py -q`.
- [ ] Commit with `feat: guard Fleet Bar activation and hide lifecycle`.

## Task 5: Migrate the Standalone Page Lifecycle

**Files:**
- Modify: `scripts/test_fleetbar_runtime.js`
- Modify: `wingman/web/fleetbar.js`
- Modify: `wingman/web/fleetbar.html`
- Modify: `wingman/web/dev.js`
- Modify: `wingman/ui/api.py`
- Test: `tests/test_bridge_contract.py`
- Test: `tests/test_fleet_bar.py`
- Test: `tests/test_api_remote_fleet.py`
- Test: `tests/test_dev_harness.py`

**Produces:** Debounced width settlement, height-only fit, sibling drag/actions, and final bridge surface.

- [ ] Extend the Node DOM double for resize/blur/keyboard/pointer/click events, deterministic timers, focus/activeElement, bounding width, and all final bridge methods.
- [ ] Add tests proving initial and telemetry renders call only height fit; telemetry never persists width; resize bursts settle once after 150ms; unchanged width does not persist; fit pauses during resizing and resumes once; delayed continuations retain their creation token.
- [ ] Add tests proving pointerdown activates before Reset/Hide, activation failure shows the main-window fallback, Reset retains activation, Escape/blur deactivate, Hide uses only the token-bound endpoint, and action/error display does not change header height.
- [ ] Run `node --test scripts/test_fleetbar_runtime.js`; confirm expected failures against production JS.
- [ ] Split header markup into sibling `.fleet-drag.pywebview-drag-region` and `.fleet-title-end` regions. Add Reset width and Hide buttons outside the drag region and reserve their geometry with opacity/visibility.
- [ ] Implement the 150ms resize debounce and activation promise. Compare settled content width with a one-pixel tolerance and keep height fitting deferred while resize events arrive.
- [ ] Update dev doubles and `test_bridge_contract.py` signatures.
- [ ] Remove `Api.fit_fleet_bar`, `Api.move_fleet_bar`, old dev doubles, and their callback inventory only after production JS has no callers. Retain drag-position saving.
- [ ] Run Node runtime, JS smoke, and focused Python bridge/lifecycle tests.
- [ ] Commit with `feat: add token-bound Fleet Bar resize and header actions`.

## Task 6: Implement Threat-First Rendering and Terminology

**Files:**
- Modify: `scripts/test_fleetbar_runtime.js`
- Modify: `wingman/web/fleetbar.js`
- Modify: `wingman/web/fleetbar.html`
- Modify: `wingman/web/style.css`
- Modify: `wingman/web/index.html`
- Modify: `wingman/web/previews.js`
- Modify: `wingman/web/dev.js`
- Test: `tests/test_fleetbar_remote_page.py`
- Test: `tests/test_fleet_bar.py`
- Test: `tests/test_fleet_metrics.py`
- Test: `tests/test_api_remote_fleet.py`
- Test: `tests/test_page_conventions.py`
- Test: `tests/test_dev_harness.py`

**Produces:** Threat hierarchy, truthful relative rails, adaptive columns, Fleet Bar copy, and equivalent main-window Reset.

- [ ] Add Node tests for threat and EWAR-threat classes, no threat on outgoing-only/stale rows, exact values with combined EWAR, stale rows excluded from maxima and forced to `scaleX(0)`, current remotes included, and remote `SCRAM/POINT` announced as “Remote tackle: scram or point.”
- [ ] Add Python tests proving metric-only updates preserve supplied local-first sequence and existing membership-change semantics remain unchanged.
- [ ] Add lexical/DOM tests requiring Fleet Bar everywhere, `DPS · 10s`, `Show Fleet Bar`, a main-window Reset button, no user-visible DAMAGE, responsive body/shell widths, no threat side stripe, root threat tokens, and reserved action geometry.
- [ ] Run Node and focused Python tests to observe expected failures.
- [ ] Implement `isStaleRemote`, incoming-threat and EWAR-threat predicates. Skip stale rows in maxima, force their ratios to zero, retain exact stale text, and keep JS row order unchanged.
- [ ] Introduce `--fleet-threat-surface` and a restrained incoming token in `:root`; EWAR retains stronger `--warn`, outgoing stays neutral, and the full row receives the threat surface.
- [ ] Start adaptive tracks at `minmax(96px, 1fr) clamp(132px, 30vw, 184px) max-content`; allow measurement-only tuning in Task 7.
- [ ] Use verified recovery copy: `Set the Gamelog folder in Settings › Alerts.`, `Gamelogs have stopped updating.`, and `Gamelogs could not be read.` Avoid repeating identical live-region assignments.
- [ ] Wire main-window Reset through `previews.js`, standard field outcomes, and authoritative `onFleetBarState` publication.
- [ ] Expand `dev.js` fixtures for zero, outgoing, incoming, all local EWAR, combined threat, remote tackle, stale leader, missing logs, each health state, all hidden, long names, 128 rows, exact 10m, and >10m.
- [ ] Run the complete focused web/Fleet set and JS smoke.
- [ ] Commit with `feat: render Fleet Bar threats before activity`.

## Task 7: Add Rendered Chromium Measurements

**Files:**
- Create: `scripts/measure_fleetbar_layout.js`
- Modify if measurements require: `wingman/web/fleetbar.html`, `wingman/settings.py`, related tests
- Modify: `docs/smoke-checklist.md`

**Produces:** Dependency-free CSS geometry evidence separate from native acceptance.

- [ ] Build a loopback static server and CDP harness using built-in Node APIs. Launch an explicit Chrome path or discover Google Chrome/Chromium, use a temporary profile, and clean up browser/server/profile in `finally`.
- [ ] Load `fleetbar.html?dev=1` at 420, 500, and 720 content widths and exercise real `DEV.fleetBar(kind)` fixtures.
- [ ] Fail on shell width mismatch, horizontal overflow, clipping/overlap of exact 10m or full local/remote EWAR, Character width at or below the old approximate 92px floor, missing ellipsis metadata, indistinguishable threat/neutral surfaces, EWAR emphasis no stronger than incoming, header geometry shift, action overlap with drag region, non-sticky header, or unbounded long roster.
- [ ] Run `node scripts/measure_fleetbar_layout.js --chrome /usr/bin/google-chrome`.
- [ ] If 500/720 or track bounds fail, change assertions first, observe RED, update settings/CSS/tests atomically, and rerun. Do not lower 420.
- [ ] Record SHA, browser version, three track-width sets, shell/scroll widths, header before/after heights, roster client/scroll heights, and the statement “Chromium layout evidence only; not Windows/WebView2 native acceptance.”
- [ ] Commit with `test: measure adaptive Fleet Bar layout`.

## Task 8: Documentation, Audit, Polish, and Final Verification

**Files:**
- Modify: `docs/smoke-checklist.md`
- Modify: `README.md`
- Modify: `PRODUCT.md`
- Modify changed source/tests only for verified audit or polish findings

**Produces:** Current terminology, truthful verification record, and a review-ready branch.

- [ ] Replace stale claims that every pixel drags, the widget is fixed at 420px, or DAMAGE is the heading. Document dedicated drag/actions, content versus outer width, edge behavior, settlement, x persistence, monitor clamp, height-only fit, fallback, activation, Hide/Reset failures, and 100/125/150/200% Windows checks.
- [ ] Use Fleet Bar consistently in current README/PRODUCT/UI copy while leaving `docs/history/` untouched and retaining fleet-sharing protocol terms.
- [ ] Audit for superseded bridge calls, user-visible old names, ordinary pywebview Fleet resize handlers, geometry calls targeting anything except Fleet Bar, public `Api` state, placeholders, and debug output.
- [ ] Run JS smoke, Node runtime, Chromium measurement, and all focused Fleet/settings/chrome/bridge/page/startup/API pytest files with `-rs`.
- [ ] Run `uv run --extra dev ruff check .` and `uv run --extra dev ruff format --check .`.
- [ ] Install the required release settings codec in this worktree following `docs/overview-layout-sharing-verification.md#local-verification-prerequisites`, then run `uv run --no-sync python -m pytest tests/ -rs`. Node/native skips are not acceptable full-suite coverage.
- [ ] Run `polish-core --fix`, inspect every edit, and rerun every affected focused gate, Chromium measurement, Ruff, format, and full pytest.
- [ ] Obtain one independent different-family code review and address only verified in-scope findings.
- [ ] Record installed Windows/WebView2 items as UNVERIFIED unless actually executed: native insets/hit targets/cursor, vertical rejection, DPI, mixed monitors, no-focus reveal, activation/focus return, no-activate restoration, fixed-width fallback, frozen packaging, and screen-reader behavior.
- [ ] Commit documentation with `docs: verify resizable threat-first Fleet Bar`.
- [ ] Use `change-explainer` for the final reviewer-facing summary.

## Verification Boundaries

- **Python:** settings lifecycle, geometry arithmetic, injected native decisions, token admission, height-only fitting, transaction outcomes, stable ordering, and private bridge state.
- **Node:** production handler execution, debounce/order, no telemetry width writes, action routing, threat classes, stale scaling, exact values, remote truth, and ARIA.
- **Chromium:** real CSS geometry, overflow, track allocation, action reservation, sticky headers, and scrolling.
- **Installed Windows/WebView2:** native insets, hit targets, DPI, focus, activation, no-activate restoration, monitor behavior, and installed/frozen behavior. No browser or fake-native result substitutes for this tier.

## Explicit Exclusions

No fleet-sharing protocol change, telemetry parser/calculation change, threat sorting, Preview/Alert/EVE-client lifecycle refactor, generic auxiliary-window framework, pywebview upgrade, Playwright dependency, frontend framework, build step, or historical-document correction.
