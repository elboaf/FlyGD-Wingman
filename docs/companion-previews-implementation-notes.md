# Companion previews — implementation

## Current direction

Implement the actual user-facing feature now: Settings > Previews, explicitly
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
- [ ] Rendered page check and practical Windows companion smoke, recorded honestly.
- [ ] Final diff explanation and reviewable PR; no automatic merge or release.

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

The card is first in Settings → Previews. It uses existing page-owned dialogs,
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

**Production companion smoke: NOT YET RUN.** No whole/region capture, activation,
restart, source geometry or Quit observation is inferred from the prototype,
OS doubles or Chromium fixtures. The short checklist is in
`docs/smoke-checklist.md#companion-previews`; no capacity/DPI matrix is required.
No specific application's visual DWM limitations have been established by this
production build yet. Protected, cloaked, inaccessible, hung and ambiguous
application-frame sources are refused; there is no alternative capture path.

The branch contains the already-reviewed runtime foundation beneath the feature.
Nothing has been merged or released. Remaining review attention should focus on
native Windows presentation and the ordinary independent-family/quit smoke,
not another foundation-only test program.

## Reviewer knowledge check

1. What distinguishes a persisted source descriptor from a live source binding?
2. Why can the first prepared candidate become stale after its save succeeds?
3. Which event proves a candidate or picker can release its selection lease?
4. How does committed reselection differ from a label/title-policy edit?
5. Why may a moved preview remain at its new position after a failed save?
