# Saved Preview layouts — implementation evidence (#213)

Status: executing the approved spec and plan; no feature acceptance claimed.

- Spec: [preview-layouts-design.md](preview-layouts-design.md)
- Plan: [preview-layouts-plan.md](preview-layouts-plan.md)
- Worktree: `/mnt/c/dev/flygd-wingman/.worktrees/preview-layouts`
- Branch: `feature/preview-layouts`
- Starting plan revision: `ad7aa79764476f034a4923027ddca09e0e0629b1`
- Source base: `76afd3dc34f20eb071c97f25cd6d891ae11c352a`
- Per-task briefs/reports/reviews/ledger: ignored `.superpowers/sdd/preview-layouts-plan/`.

## Baseline

Before any source change, a dedicated environment was created with
`UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-layouts-venv uv sync --locked --extra dev`.
Node `v26.5.0` was present. The release codec was built from this checkout with
`cargo build --locked --release --manifest-path packaging/settings-codec/Cargo.toml --target-dir /tmp/wingman-preview-layouts-codec`,
installed into this checkout's ignored `packaging/bin`, and
`codec.codec_available()` asserted true.

```sh
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-layouts-venv uv run --no-sync python -m pytest tests/ -q -rs --basetemp=/tmp/wingman-preview-layouts-baseline --junitxml=/tmp/wingman-preview-layouts-baseline.xml
```

Result: **12,502 passed, 13 Windows-only skips in 325.70s**. The skipped cases
require Windows junctions, DPAPI/WinDLL, native preview/message-pump APIs or the
Windows tray backend; no Node/codec prerequisites skipped. This is baseline
regression evidence, not proof of the proposed feature or Windows operator acceptance.

## Preflight ordering clarification

Task 2 must establish completion-bound ordinary visibility leases before Task 3
uses exclusive batches. Therefore the ordinary `refresh_primary_visibility`
primitive and shared `PrimaryLayoutLiveResult` record are introduced in Task 2;
Task 3 consumes the same interface and adds capture/apply records. This changes
internal task placement only, not product behavior or persisted schema.

## Task 1 — pure snapshots and lossless offline exclusions

Implemented only `SavedCharacter`, `SavedLayout` and the seven agreed pure model
functions in `preview/savedlayouts.py`; no native capture/commit/live-result types,
admission, controller, bridge actions or named-layout UI. Settings now defaults
`preview.saved_layouts` to an independent `{version: 1, items: []}` and normalizes
it on every write. Loading rejects malformed records whole, preserving valid
siblings and the working arrangement. Writes refuse malformed/duplicate proposals;
record revisions hash sorted-key JSON, independent of owner insertion order.

Snapshot owners use strict `crops.valid_owner` without casefolding. IDs remain
opaque nonempty strings like cycle-group IDs; later creation owns UUID generation.
Names are trimmed, nonblank and printable (control characters are refused even
at the ends). Geometry is strict signed-32-bit integers, positive dimensions,
and safe right/bottom arithmetic. Capture prefers actual live rectangles, then
retained `layout.Entry` geometry, then committed current geometry. Saved-only
owners contribute identity, not an older snapshot's geometry/visibility. Apply
validates first, preserves legacy geometry lock bits, changes only recorded
non-null rectangles and Preview choices, and retains absent owners unchanged.

Only `preview.excluded` passes `cap=None` to `roster.deserialize`; legacy roster
validation/deduplication is unchanged, and history/other policy caps remain 64.
`previews.js:rows()` now unions excluded-only owners through its existing
null-prototype map. The existing Node fixture proves a 65th excluded-only owner
and prototype-like names remain editable while Preview is Off, with the existing
inverted checkbox semantics. No markup, CSS, runtime or external resources changed.

### Task 1 verification

All Python/Ruff commands used
`UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-layouts-venv uv run --no-sync`.

- RED, before production edits: new model/settings files — **8 failed, 111 setup
  errors** (missing model/default, dropped `Pilot64`). Compatibility/page files —
  **3 failed, 86 passed** (missing default, capped exclusions, 64 rather than 67
  rows). The standalone roster `cap=None` characterization already passed because
  Python's old `out[:None]` slice was uncapped; the new annotation/branch makes
  that contract explicit without changing other callers.
- Initial required GREEN: **423 passed**. After self-polish/formatting, broader
  model, settings, layout/store/crop, committed reader, API field, bridge and
  packaging gates: **944 passed**. One earlier broader invocation used a nonexistent
  test filename and collected nothing; corrected to `test_api_settings_fields.py`.
- Ruff: initial test-only raw-regex/import-format findings corrected;
  `ruff check .` passed and `ruff format --check .` reported **442 files formatted**.
- `node scripts/js_smoke.js`: **PASS every page module loaded**.
- `cargo test --locked --offline --manifest-path packaging/settings-codec/Cargo.toml --target-dir /tmp/wingman-preview-layouts-codec`:
  **1 passed**, no network used.
- Full suite, run exactly once after Task 1 implementation:

```sh
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-layouts-venv uv run --no-sync python -m pytest tests/ -q -rs --basetemp=/tmp/wingman-preview-layouts-task1-full --junitxml=/tmp/wingman-preview-layouts-task1-full.xml
```

Result: **12,624 passed, 13 Windows-only skips in 307.18s**. No missing Node/codec
skips. Unique `/tmp/wingman-preview-layouts-task1-*` basetemps/logs retain RED,
GREEN, broader and full-run evidence. Detailed commands and self-review are in
the ignored task report; baseline/preflight contents above are preserved.

Self-review/polish was local only, as requested; no subagents, independent review,
network or GitHub operations. No unresolved Task 1 correctness finding. Native
ordering, browser rendering and Windows/WebView2/live-EVE acceptance remain for
later tasks/operator verification; these results do not establish them.

## Task 2 — foundation checkpoint, not completed integration

Status: **NEEDS_CONTEXT — Task 2 remains incomplete.** This checkpoint provides
verified foundations only. It does not establish a shared production admission
owner, move ordinary Reset off the pump, or implement the ordinary visibility
completion primitive. Do not begin Tasks 3–5 on the strength of these checks.

Implemented with RED/GREEN tests:

- `preview/layoutadmission.py`: frozen `PrimaryLayoutLease` and `AdmissionState`,
  shared/exclusive admission, exact-token ownership, idempotent finish, final
  close and timeout-aware idle waiting. A foreign gate's numerically equal token
  cannot retire a local lease. No callbacks, I/O, native code or fairness queue.
- `CropStore.submit_primary(action) -> Future[T]`: a typed `_Primary` item in the
  existing command queue. The retained worker executes actions outside its
  condition and preserves exceptions on futures; queued actions precede close.
  Startup factory/submission failures settle futures, and a retired dispatcher's
  queued job cannot execute them later. No second executor or submitted worker.
- `PreviewWindow` gesture callbacks: optional `on_gesture_begin`/`on_gesture_end`,
  with `finish_gesture(record=True)` for button-up, capture loss, cancel, native
  destruction, close and future host freeze integration. Classification-only
  left presses do not reserve geometry; a real drag rechecks admission before
  moving. A refused drag is not converted into activation or a crop toggle.
  Real clicks and locked-primary crop clicks remain independent.

**Not yet wired:** production host, `Api`, main, coalesced primary intents,
Copy's separate mailbox, retained stop/re-enable lifetime, default-size and
host-unavailable operations. The new window callbacks and queue method have
no production host consumers yet. The coordinator's task-placement ruling is
accepted but **not implemented at this checkpoint**:
`PrimaryLayoutLiveResult` and `refresh_primary_visibility(lease)` still belong
to the remaining Task 2 work, not Task 3.

### Retained integration risk / resume boundary

Before adding host leases, prove the asynchronous Reset continuation and its
failed-post/no-HWND cases. At this base `host._apply_primary()` pops and finally
retires a batch synchronously. Simply replacing the clear with
`submit_primary(clear)` either retires too early or permits a following already
posted Size to be persisted before the delayed clear erases it. Retaining the
batch while later OS signals are consumed requires an explicit continuation
that does not depend on a successful completion post. The brief restricts
worker callbacks to storing/posting completion. No additional worker or
unproven off-pump native/cache fallback was added at this checkpoint.

Related concrete boundaries remain unchanged: Off clears `_pending_layouts`;
`_host_proc` currently discards Copy behind stopping/epoch checks;
`_begin_stop` returns for `_primary_pending` before freezing native gestures;
`Api._preview_setting_change` retires on bridge return; and `build_preview_host`
constructs the layout writer after the platform gate. These are outstanding
integration work, not claims fixed by the new pure gate.

### Foundation verification (not final Task 2 acceptance)

All Python/Ruff invocations used
`UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-layouts-venv uv run --no-sync`.
Unique `/tmp/wingman-preview-layouts-task2-*` basetemps retain each run.

- Admission RED: **4 failed**, missing module; GREEN: **4 passed**.
- Crop worker RED: **5 failed**, missing `submit_primary`; admission + full
  cropstore GREEN: **59 passed**.
- Gesture RED: **6 failed**, missing callback parameters; admission + cropstore
  + full window GREEN: **200 passed**.
- Broader runtime/review/boundary/polish/host/window/crop/API checks:
  **2,100 passed, 1 Windows-only skip in 60.04s**.
- Local self-polish only: reviewed the diff and failure/cleanup paths; changed a
  premature comment claiming the host already consumed `finish_gesture` into
  conditional guidance. Ruff reformatted two touched files. No independent
  reviewer or subagent was used.
- `ruff check .`: **passed**; `ruff format --check .`: **444 files formatted**.
- `node scripts/js_smoke.js`: **PASS every page module loaded**.
- Offline independent Cargo regression: **1 passed**.

The requested checkpoint full run finished:

```sh
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-layouts-venv uv run --no-sync python -m pytest tests/ -q -rs --basetemp=/tmp/wingman-preview-layouts-task2-foundation-full --junitxml=/tmp/wingman-preview-layouts-task2-foundation-full.xml
```

Result: **12,639 passed, 13 Windows-only skips in 336.82s**. No missing
Node/codec skips. This is a foundation regression result, **not** proof of the
missing completion-bound ordinary operation/lifecycle integration. Use focused
and broader tests during the remaining integration; reserve the next full run
for the final complete Task 2 tree, per the coordinator checkpoint instruction.
