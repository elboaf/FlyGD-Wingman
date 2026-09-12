# Companion previews — implementation

## Current direction

Implement the actual user-facing feature now: Settings > Companions, explicitly
selected auxiliary windows, whole-window and selected-region modes, persisted
definitions, independent family toggles, movement/resizing/activation, reselection
and removal. Default off, at most eight enabled companions. No build-time flag,
Phase 0 blocker, capacity qualification matrix or staged-release program.

The user redirected work away from the standalone Phase 1 manual check to this
feature. This worktree stacks on the reviewed/rebased runtime at `df28297e` rather
than blocking implementation on a separate merge. It does not authorize a merge
or release. The earlier native prototype worked; that is not a claim that this
production implementation has been manually exercised.

## Discovery constraints

- `preview/runtime.py`: one runtime owns host startup/shutdown; independent EVE
  and companion demand and selection leases already exist.
- `preview/host.py`: Phase 1 acknowledges companion activity without native
  resources. Feature integration must replace those acknowledgments with actual
  family ownership/cleanup, not introduce another owner.
- `preview/croppicker.py`: character crop policy must remain an adapter over any
  extracted generic picker. Source dimensions and identity remain authoritative.
- `settings.update()` rolls back failed writes. Native candidates stay hidden
  until complete definitions persist; old committed views survive reselection.
- `PRODUCT.md` forbids source geometry/input automation. Sources and owned
  destination/picker handles must be distinct in tests.
- `DESIGN.md` requires hydrated field commits, literal bridge handlers, page-owned
  dialogs and preserved drafts. Native callbacks cannot evaluate JavaScript.
- Packaging already includes `wingman.preview`; new modules remain within it.
  New page scripts still require index loading and executable/lexical guards.

Remaining implementation risks are cross-boundary ordering, source identity
reverification, shared picker admission and incomplete native cleanup. These
follow the approved contracts; no unresolved product decision blocks work.

UI preflight: context=pass, product=pass, command_reference=product,
shape=approved user brief, image_gate=skipped (existing utility controls, no image
assets), mutation=open. Repository tokens, typography, wrappers and em-dash house
style take precedence over generic design advice.

## Work checklist

- [x] Validated immutable definitions, source descriptors and normalized regions.
- [x] Safe source catalog, owned companion windows and generic region picker.
- [x] Transaction controller, shared runtime integration and bridge facades.
- [x] Companion card and focused JavaScript response-ordering tests.
- [x] Integrated tests, polish/fixes and fresh normal repository gates (Windows
      environmental failures are recorded below, not suppressed).
- [x] Rendered page checks and practical Windows operator feedback, with the
      limits of those observations recorded below.
- [x] Final diff explanation and reviewable PR #209; no automatic merge or release.

## Verification environment

Linux uses `/tmp/wingman-companions-venv` with locked dev dependencies and the
release settings codec built/installed in this worktree. Windows uses
`%TEMP%\wingman-companions-dev\venv`; its codec is copied from the runtime checkout
with unchanged Rust sources. Node 26.5.0 is available. Tests use isolated state;
no live source windows are manipulated during automated verification.

## Engineering result

Initial feature commit: `63d163b`. Reviewed corrections: `fbf0513`. The actual
card and both capture modes are implemented, not hidden behind a release flag.
The optional lock interaction was omitted; movement and resizing remain explicit
left/right drag gestures. There are no companion alerts, cycle binds, source
input/geometry automation, or new dependencies.

A selected window produces an opaque chooser token. The pump verifies its full
runtime identity, opens the generic picker for region mode, and prepares a hidden
DWM destination. The controller's single worker persists the complete definition
before requesting promotion. Failed persistence discards the candidate while
preserving any previous committed preview. Successful persistence followed by
source loss remains a real saved definition, with an honest runtime status.

A runtime-only committed selection hint preserves an explicit choice across the
first family activation, which legitimately invalidates the old prepared token.
Fresh reconciliation verifies that hint and creates a newly authorized view;
it never retags stale candidate authority. A separate selection generation stops
committed replacement definitions from inheriting the previous source. Neither
hint nor native identity crosses persistence or the page bridge.

The native family retains incomplete window, picker, thumbnail and query-handle
cleanup. Picker construction can return a cleanup-only owner rather than a live
picker; callbacks acknowledge completion only after those resources release.
Destination geometry is debounced by the controller and generation/revision
fenced. A failed geometry save leaves the current physical position with a
session-only warning, not a false durable success.

The card lives in its own Settings → Companions section, independent of the
EVE-tools navigation gate. It uses existing page-owned dialogs,
field commits and keyed drafts; terminal operation receipts remain recoverable
when events beat replies or the page is left and re-entered. Existing EVE-tools
navigation remains unchanged. `WM.choose` gained an optional field label so this
chooser says Source while existing copy dialogs retain Copy from.

## Polish and verification actually performed

A four-role polish pass reviewed integration, native/silent failures, comments
and data contracts. Reproduced findings were fixed with regressions: incorrect
old-source retention after committed reselection, lost first-add choice among
identical descriptors, replacement geometry handoff, stale successful-promotion
errors, malformed-region overflow, post-normalization Unicode bounds, and picker
creation losing retained resources or allocating a null-HWND thread timer.
Moved-picker safety guards and new callback/test-host seams were updated without
weakening source protections. Independent scoped re-review approved all eleven
reported correction items. Final diff and formatter edits were inspected.

- Linux full: `UV_PROJECT_ENVIRONMENT=/tmp/wingman-companions-venv uv run --no-sync
  python -m pytest tests/ -q -rs --junitxml=/tmp/wingman-companions-linux.xml`:
  **10,830 passed, 11 Windows-only skips**, 242.53 seconds.
- Windows full, prepared venv with isolated APPDATA/LOCALAPPDATA, portable Node
  and the real codec: `python -m pytest tests/ -q -rs --junitxml <temp report>`:
  **10,779 passed, 56 skips, six failures**, 246.03 seconds. All six failures
  are unchanged symlink-permission tests in `test_setup_catalog.py` and
  `test_ui_setup_controller.py`, raising `WinError 1314`. No privileges, skip
  policy or unrelated tests were changed. The complete Windows suite is
  therefore **not claimed green**. All companion tests ran and passed.
- Windows initially exposed two newly added tests assuming Python-style Unicode
  case expansion; Windows' native case mapper differs. The tests now inject an
  expanding normalizer on both platforms. Both focused model runs passed
  **18 tests**, followed by the Windows full run above. Production code did not
  change for this test correction.
- `ruff check .` and `ruff format --check .`: passed, 405 Python files.
- `cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml`:
  **1 passed**. `node scripts/js_smoke.js`: all page modules loaded, including
  `companions.js`. `node scripts/test_companions_runtime.js`: **28/28 passed**.
- `git diff df28297e..HEAD --check`: passed.
- Chromium at **840×625** rendered empty, one, full, long-text, waiting,
  failed-save and unavailable fixtures without page errors or horizontal
  overflow. Card bounds were x=192–812, width 620 in an 840px viewport; card
  scroll width equalled its client width. Screenshot inspected. These are
  browser fixtures, not native DWM evidence.
- Actual Windows read-only `SourceCatalog` inspection returned seven eligible
  windows from six ordinary applications; EVE clients/launcher and Wingman were
  excluded, and query handles closed. This verifies real query bindings only,
  not captured pixels or source activation.

## Windows feature smoke and limitations

**Initial production tryout: operator feedback received; full smoke incomplete.**
The operator reported forced aspect ratio, an oversized source dropdown, and a
preference for a separate tab. The follow-up below addresses those observations.
No complete whole/region, activation, restart, source geometry or Quit result is
inferred from that report, the prototype, OS doubles or Chromium fixtures.
The short checklist is in
`docs/smoke-checklist.md#companion-previews`; no capacity/DPI matrix is required.
No specific application's visual DWM limitations have been established by this
production build yet. Protected, cloaked, inaccessible, hung and ambiguous
application-frame sources are refused; there is no alternative capture path.

The branch contains the already-reviewed runtime foundation beneath the feature.
Nothing has been merged or released. Remaining review attention should focus on
native Windows presentation and the ordinary independent-family/quit smoke,
not another foundation-only test program.

## Operator-feedback follow-up — `697ff87`, `1513f02`

- Companion right-drag no longer supplies an aspect ratio to `resize_result`.
  Width and height respond independently, including the minimum size. Existing
  EVE preview aspect settings and source rectangles are unchanged. Six real
  message-path regressions failed before the fix and pass after it.
- Companions now has its own Settings rail entry after Uploading. It remains
  accessible when EVE tools are hidden; remembered sections, hydration, drafts,
  source-flow ownership and keybind capture follow the new section. No saved
  definitions or settings schema changed.
- Source choice opts into a compact dialog and bounds native option captions
  to 44 Unicode code points, preventing long titles from sizing the popup.
  The full selected application/title remains wrapped below the dropdown and
  is associated with it for accessibility. Ordinary copy dialogs retain their
  original dimensions, captions and field label.

Fresh verification after polish and independent review:

- Linux full: **10,838 passed, 11 Windows-only skips**, 228.99 seconds, using
  the same venv/pytest command with `/tmp/companion-usability-linux.xml`.
- Windows focused preview, companion, Settings, shared dialogs, setup-page and
  screenshot-tool tests: **2,549 passed, no skips**, 22.86 seconds.
- Companion Node harness: **31/31**. Ruff lint/format, Cargo's one regression,
  all-page JavaScript smoke and diff checks passed.
- Chromium at 840×625: source dialog **360px**, select **318px**, three long-title
  options each bounded to 44 code points; selected 525-character application/title
  wraps without horizontal overflow. Open-popup screenshot inspected. Subsequent
  ordinary copy dialog remained **460px** with no compact styling or stale detail.
- Independent scoped review passed. Full verification also caught the setup DOM
  double missing standard `removeAttribute` and the screenshot inventory missing
  Companions; those test seams were updated without relaxing their assertions.

The running application must restart to load these changes. Operator recheck of
free resizing and the new chooser remains distinct from the automated evidence.

## Intermittent source enumeration follow-up

The operator reported “Source scan incomplete; close some windows and retry,”
then reported that it started working. Read-only Windows enumeration showed 511
top-level windows with only 45 visible; a later sample had 506 total and 43
visible. Most were hidden IME, text-service, browser and tool/helper windows.
The source catalog incorrectly counted these in its 512-window inspection cap.

The enumeration callback now collects only visible candidates; `_inspect` still
rechecks visibility and identity. Hidden windows do not incur process inspection.
More than 512 visible candidates and an actual `EnumWindows` failure both remain
refusals, with separate accurate messages. Neither produces a truncated list
that could be mistaken for a unique match. No source windows were manipulated.

A regression with 513 hidden helpers ahead of one visible source failed before
this change and passes after it. Focused verification: **575 passed, four
Windows-only skips on Linux; 579 passed with no skips on Windows**. Ruff
lint/format and diff checks passed. Actual Windows source enumeration returned
10 eligible sources and closed its query handles. This small fix does not claim
a fresh full-suite run or change the prior manual-smoke status; the running app
loads it on its next restart.

## Full-PR review corrections — `c8878fc0`, `84b8dbea`

After the updated production tryout, the operator reported “looks good” and
requested full-PR polish and CodeRabbit review. That feedback does not imply
individual confirmation of every smoke-checklist scenario. The actual CodeRabbit
CLI reviewed all 63 changed files and returned 19 findings; its severity labels
were checked against the current code, not accepted blindly. Malformed settings
and zero-size sources already have validated boundaries. The suggested missing-Node
skip and unproven native-handle discard were not adopted.

The four reproduced runtime/persistence findings and three smaller corrections
were implemented with test-first regressions:

- A failed primary `PostMessageW` refuses before admitting its payload or pending
  barrier. Accepted pre-HWND commands retain their existing delivery lane. This
  prevents a missing wake from permanently blocking Quit without dropping
  accepted work or starting a retry worker.
- Master changes and explicit layout edits share the existing short reservation.
  Retained cleanup or queued layout work produces an honest refusal rather than
  letting older writes undo an acknowledged Reset/Size. Final admission shares
  the shutdown fence, but closure never waits for already-admitted transactions.
- Re-review found that an empty command FIFO does not mean the debounce writer
  has finished. Offline Size now uses the already-injected `LayoutStore.replace`
  authority, superseding a pending delta and ordering behind an in-flight write.
  It preserves the latest position/lock and unrelated character deltas, retains
  failed-save recovery, and does not overwrite a later drag or move a window.
- Capture-failure suppression distinguishes changed source dimensions, observed
  unavailability/recovery and family epochs. An unchanged unsupported capture
  remains bounded; a source that becomes usable can recover without recreating
  the shared runtime.
- Native retirement is irreversible. Activation is revoked before cleanup;
  incomplete releases keep their slot and retry even if the source recovers.
  Replacement waits for release, and hidden/retiring windows cannot report Live.
- Help now advertises only supported left-drag movement/right-drag resizing.
  The Off note stays hidden until hydration, including re-entry. Runtime fixture
  teardown checks completion after attempting all owners.

There are 43 new Event/OS-double lifecycle and recovery cases across
`test_preview_polish_fixes.py` and `test_companion_recovery.py`. Additional coverage
pins the shared picker class name and browser hydration. Safe cleanup also
isolates the Unicode test patch from shared `ntpath`, removes unreachable message
IDs, clarifies test failures, and avoids repeated independent packaging checks.
No settings schema, public bridge payload, dependency, source-window policy or
release gate changed.

Fresh final verification:

- Linux full: `/tmp/wingman-companions-venv/bin/python -m pytest tests/ -q -rs
  -o faulthandler_timeout=60`: **10,884 passed, 11 Windows-only skips**, 237.24s.
- Windows focused: all `test_preview*.py`, `test_companion*.py`, `test_api*.py`,
  plus engine invariants, packaging, settings, EVE gate, Settings page and
  screenshot-tool tests: **2,812 passed, four existing permission/platform skips**,
  28.08s. Three require unavailable symlink privilege; one requires a directory
  unreadable to the current user. Node and native Windows preview tests ran.
  Report: `%TEMP%\wingman-companions-dev\polish-fixes-windows-final.xml`.
- Parent rerun of the new regression modules and API settings tests: **107 passed**.
  Ruff lint/format: passed, 407 files. All-page JS smoke: passed. Companion Node
  harness: **32/32**. Cargo's codec regression and diff checks passed.
- Independent scoped re-review approved the final storage correction after
  checking pending/in-flight writes, final admission, failure recovery, later
  drag state and retained owner boundaries. No further actionable finding
  remained in the correction scope.
- Chromium at 840×625 with the state reply deliberately held: Off note has
  `display: none` while Loading, becomes visible only after an acknowledged Off
  payload, and the corrected help renders without horizontal overflow or page
  errors. Screenshot inspected; this is browser evidence, not DWM acceptance.

The prior complete Windows run and its six unchanged symlink-privilege failures
remain recorded above; a new complete Windows run is not claimed. The running
application was not restarted or manipulated during these corrections. PR #209
is open and not draft; nothing has been merged or released.

## Reviewer knowledge check

1. What distinguishes a persisted source descriptor from a live source binding?
2. Why can the first prepared candidate become stale after its save succeeds?
3. Which event proves a candidate or picker can release its selection lease?
4. How does committed reselection differ from a label/title-policy edit?
5. Why may a moved preview remain at its new position after a failed save?
