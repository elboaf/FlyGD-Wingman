# Saved Preview layouts — implementation evidence (#213)

Status: implementation and task-scoped reviews complete through Task 5;
[Task 6 documentation/acceptance preparation](#task-6--documentation-and-acceptance-preparation)
recorded below. Fresh final whole-branch review/polish and global gates remain
coordinator work. Windows/WebView2/live-EVE acceptance and authorized integration
remain pending; no feature acceptance or closure of #213 is claimed.

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

## Task 2 — completed ordinary-operation integration

Status: **implemented and verified; awaiting the coordinator's fresh review**.
The earlier NEEDS_CONTEXT checkpoint is historical. The coordinator explicitly
approved a single-claimed detached-cache/storage continuation after revocation
or where no native phase can be executing. A live authorized HWND with a failed
completion post retains readiness for the next existing pump turn. Neither case
adds a worker, executor submission, timer, polling loop or runtime owner.

Main now constructs one `LayoutStore`/`PrimaryLayoutAdmission` pair before the
platform builder and passes the same objects to host and Api, including the
host-unavailable path. Api rejects inconsistent injected resources and reuses a
real host's existing pair rather than constructing another writer. Default-size
writes and exclusions use shared admission and retain settings' concurrent-write
serialization; Size/Copy/Reset preserve the existing offline bridge reservation.
Master On needs exclusive admission. Off uses a separate short master reservation,
so ordinary layout ownership cannot prevent committed revocation, while a second
tentative master write is still refused. Final closure closes the shared gate.

Primary intents retain a list of every coalesced lease and readiness independently
of OS wakes. One claimed continuation spans preparation, existing-worker submission
and native completion. A Resize wake consumed while Reset awaits disk is retained;
a live failed completion post retries at an existing pump turn, not off-pump.
After revocation/no-HWND, detached geometry prepared on the pump (or retained
working entries where no window existed) permits storage/cache completion without
reading or changing a PreviewWindow. Preparation/submission failures terminalize
the head without losing successor readiness. Leases retire before lifecycle wakes.

Reset clear now runs on the existing CropStore queue. Typed Size also keeps its
lease through the existing writer's flush, not merely recording a debounce.
`LayoutStore.clear()` now returns a boolean for the ordinary completion path,
without adding Task 3 transactions or changing its legacy delta policy. Offline
Size/Copy use the same ordered writer; host-backed offline Reset waits on the
existing queue from the bridge thread. Copy retains separate mailbox leases
through native retirement; superseded payloads and Off do not drop their owners.
Its pending native lane also prevents a later offline Size from overtaking it.

Gesture callbacks are wired to the gate, without changing locks, click activation
or right-click crop meaning. Pending primary work freezes earlier gestures before
its asynchronous persistence, so a later Off freeze cannot resurrect Reset data.
Off immediately rejects further mouse movement. A small epoch/owner lease map
still authorizes only the admitted gesture's final geometry; retired callbacks
remain fenced. `_begin_stop` freezes before checking admission, and only detaches
crop commands once it can submit them — an early return never loses that mailbox.
Every initial/late/final-upgrade storage-barrier decision rechecks outstanding
primary admission, including an offline crop submission overlapping an admitted
Reset. Retained joins remain outside state locks.

**Coordinator task-placement ruling implemented:** `savedlayouts.py` now defines
frozen `PrimaryLayoutLiveResult(live: str, warning: str | None)` and the host has
`refresh_primary_visibility(lease) -> Future[PrimaryLayoutLiveResult]` plus
`release_primary_layout(lease)`. Ordinary exclusion promises wait on their bridge
thread for actual current-roster reconciliation/rebind. Offline/final delivery is
deferred; reconciliation failure preserves the committed choice and warns.
An executing native visibility phase cannot be completed early by Off. Discovery
and crop reconciliation continue; no named capture/apply/controller/UI was added.
Legacy live Size/Reset and Copy receipt timing stays unchanged; it is their
admission ownership, not those existing queue acknowledgements, that now persists
through completion.

### Integration verification and self-review

Event-controlled RED/GREEN cases cover consumed Size wakes behind Reset, live
failed completion posts, no-HWND/revoked completion, final barriers, Copy coalescing
and offline ordering, On refusal, worker/preparation failures, gesture freezing,
revocation during movement, late final-gesture persistence, visibility completion
and failure, and preserving crop commands during a primary drain. RED failures
and every intermediate result are recorded in the task report; no failure is
represented as a passing gate.

- Final broad lifecycle/window/cropstore/store/API/committed-reader/wiring run:
  **2,404 passed, 1 Windows-only skip in 54.92s**.
- The first complete-tree full run found **22 failures, 12,643 passed, 13 skips**:
  21 missed startup/custom-alert builder-double keyword signatures, plus default
  size's legacy concurrent retry being over-serialized by the bridge mode flag.
  The doubles now consume the shared pair; default-size writes use shared,
  non-mode-serialized admission. Resource ownership is checked structurally rather
  than against a monkeypatchable constructor symbol. Added a real-main composition
  assertion that the unavailable host and Api share the constructed pair.
- Focused composition/transaction/API follow-up: **944 passed in 41.40s**.
- Self-polish inspected the final diff and lifetime/lock-order paths locally.
  It caught and regression-tested the late closing-barrier race, crop mailbox
  detachment before a primary wait, and active drag movement after Off. Safe
  cleanup removed unused imports/default scaffolding, updated relevant doubles,
  corrected stale comments, and ran Ruff formatting. No independent reviewer or
  subagent was used.
- Fresh `ruff check .`: **passed**; `ruff format --check .`: **444 formatted**;
  Node all-page smoke: **PASS**. Independent offline Cargo regression: **1 passed**.

Final full verification, after all source/test fixes and formatting:

```sh
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-layouts-venv uv run --no-sync python -m pytest tests/ -q -rs --basetemp=/tmp/wingman-preview-layouts-task2-complete-full-verified --junitxml=/tmp/wingman-preview-layouts-task2-complete-full-verified.xml
```

Result: **12,666 passed, 13 Windows-only skips in 301.64s**. Node and release codec
coverage did not skip. The earlier failed complete-tree XML is retained separately
at `/tmp/wingman-preview-layouts-task2-complete-full.xml`. No network, GitHub,
real app/EVE/profile/clipboard operations, push or PR occurred. Windows/WebView2
operator acceptance remains outstanding; portable tests do not establish it.

## Task 2 — fix round 1, native boundary corrections

Base: `1cc9b93acbb1dd7b71b7ea9129434deeba9517ca`. All three Important findings
were reproduced at their actual caller seams before their production fixes:

- `PreviewWindow.move()` now rechecks EVE authority after cursor/snap work and
  before native/cache movement, including each resize-all target. A native call
  admitted earlier may finish; later targets are fenced. Single/bulk typed Size
  still persists its admitted requested rectangle if the window refuses delivery.
- `finish_gesture` releases only its own HWND's capture, using the existing
  `GetCapture` binding. Local state is detached before synchronous capture-loss
  reentry, while the outer lease remains owned through cleanup/recording.
  Duplicate button-up and blanket host-stop releases were removed so another
  family's capture is not stolen. The queued-Reset test now starts a real gesture
  and asserts native ownership, not only `_mode` or lease counts.
- `_apply_hotkeys(libs, table)` now returns the existing `PrimaryLayoutLiveResult`.
  Real unregister/register false returns produce `incomplete` with affected-chord
  warnings, propagated through visibility completion and the existing Api warning.
  Committed exclusions survive reload; unreleased registrations stay owned but
  excluded bindings cannot dispatch; successful retry removes the warning.

No new worker/timer, off-pump window access, state-lock native work, schema,
controller or later-task UI was introduced. The detached-continuation/readiness/
closing-barrier ruling remains unchanged. Local diagnosis/TDD and self-polish only;
no independent review, network, app/EVE/profile/clipboard or GitHub effects.

Verification uses `UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-layouts-venv uv run --no-sync`:
movement RED **5 failures** → **176 passes**; capture RED **7 failures** plus foreign
capture RED **1 failure** → **182 passes**; real rebind RED **2 failures** → **6
visibility passes**; typed-size preservation RED **2 failures** → **186 focused
passes**. Broad `tests/test_preview*.py tests/test_companion*.py tests/test_api*.py
 tests/test_settings_committed_preview.py tests/test_settings_transactions.py`:
**3,479 passed, 4 Windows-only skips in 104.20s**.

After local polish, Ruff lint/format passed (**444 formatted**), all-page Node
smoke passed, and offline Cargo regression passed (**1 test**). One final full run:

```sh
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-layouts-venv uv run --no-sync python -m pytest tests/ -q -rs --basetemp=/tmp/wingman-preview-layouts-task2-fix1-full --junitxml=/tmp/wingman-preview-layouts-task2-fix1-full.xml
```

**12,681 passed, 13 Windows-only skips in 306.56s**; no Node/codec skips.
Exact per-case commands, outputs, interfaces and self-review evidence are appended
in `.superpowers/sdd/preview-layouts-plan/task-2-report.md`. Coordinator re-review
and Windows/WebView2/live-EVE operator acceptance remain outstanding.

## Task 2 — fix round 2, crop input quiescence before primary drain

Base: `8c5a4e7fb57cd88bca98a4142bb38f4514df246b`. The re-review accepted all
three round-1 fixes but reproduced a crop gesture remaining captured/visible
across EVE Off while an admitted Reset held storage. This round leaves those
three fixes intact and addresses only that early-stop boundary.

`CropController.freeze_windows() -> None` marks stopping and reuses existing
crop lock/hide cancellation without submitting storage or canceling temporary
picker resources. The host calls it outside its lock, before the primary drain
wait can return. `begin_stop` reuses it in the original ordered phase; epoch
fencing, pending configuration, picker cancellation and drain/close ordering are
unchanged. Each crop releases only its own capture. No blanket release, new
worker/timer, off-pump native work or crop gesture-policy change.

New tests use real controller/window/picker paths: crop capture → Event-held
admitted Reset → Off quiescence (including transferred foreign capture and synchronous
release reentry); no crop stop barrier before Reset completion; retained candidate
and queued-disable work; and captured-picker/font cleanup ownership. Caller RED:
**2 expected failures**; combined host/controller RED: **4 failures** → **4 passes**.
Required focused files: **371 passed in 7.92s**. Local self-polish preserved
standalone `begin_stop`'s store-fence order before native hiding.

Final verification, with `UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-layouts-venv
uv run --no-sync`: `python -m pytest tests/test_preview*.py tests/test_companion*.py
-q -rs --basetemp=/tmp/wingman-preview-layouts-task2-fix2-broad` — **2,631 passed,
4 Windows-only skips in 82.28s**. Ruff lint/format (**444 files**) and all-page
Node smoke passed; `git diff --check` passed. No full-suite/Cargo rerun for this
small scoped fix; no external effects or independent review. Exact commands,
outputs and interfaces are appended to the Task 2 report. Coordinator re-review
and Windows/WebView2/live-EVE operator acceptance remain outstanding.

## Task 3 — acknowledged writer and checked native batches

Base: `4d0bb6fd295bf26f7fc560adc1265495ee2bed6c`. Implemented only the persistence
and host/window primitives; controller, bridge actions and UI remain later work.
`LayoutCommit` and `PrimaryLayoutCapture` use the agreed immutable records and
operation-owned detached Preview dictionary. `PrimaryLayoutLiveResult` and the
reviewed shared admission/store/runtime pair are reused, not replaced.

`LayoutStore.transact(mutate_preview)` orders behind debounce/replace/clear,
drains ordinary deltas/names under its short pending lock, merges before mutation,
and explicitly normalizes and prepares the receipt inside `settings.update()`.
Settings' final normalization is tested as a fixed point. Save/publication must
succeed before the sequence advances or the receipt returns. Any exception
restores drained work, with newer geometry winning and names replayed oldest
first; retained work is re-armed outside the writer lock. Snapshot-only changes
do not install captured live coordinates into the working arrangement.

The host adds `capture_primary_layout(lease)` and
`apply_primary_layout(lease, capture, commit, rectangles)` futures. The coordinator's
`Mapping[str, Rect | None]` ruling is implemented: every recorded key participates
in inclusion/failure checks, null geometry never moves a window, and absent members
are not painted or blamed. Geometry is taken from the durable commit, even when
persisted coordinates already match but the actual window differs. Full captured
sessions/epochs fence delivery and newly re-enabled live members receive explicit
geometry even with reopen Off. Later arrivals retain the global reopen behavior;
monitor rescue never rewrites preferred coordinates. Metadata membership follows
checked primary inclusion; hotkey rebind consumes the already-held desired table
and its reviewed real failure outcome.

Capture samples actual owned HWND rectangles on the pump, includes excluded live
sessions and retained offline/committed state, refuses a failed native read or
changed source, and never fabricates missing rectangles. Stable offline operations
use detached state without starting a pump or touching windows. A single claimed
request retains readiness through failed posts. Off/final closure can settle only
unstarted native work; executing callbacks keep their lease/future until unwound.
Release clears operation-local state before retiring admission and waking lifecycle.
Discovery/crops continue; a scoped inclusion view prevents a discovery wake in the
durable-commit/apply gap from performing the unchecked membership change first.

Supporting native corrections are necessary for truthful failure accounting:
`native_rect()` checks `GetWindowRect`; `move_checked()` checks `SetWindowPos`
before adopting geometry and shares successful label/thumbnail maintenance with
legacy `move()` (whose unchecked-success contract is preserved). Checked resizing
invalidates active alert frames before fallible follow-up rendering. Creation
rechecks authorization before later native stages. `close_checked()`/`close()`
return actual destruction success and retain failed handles; discovery/teardown
must not discard or replace them. Revoked creation with failed cleanup is also
retained by the host. Main injects the existing committed reader's snapshot callable;
this is one composition line, not a later-task controller/bridge command.

### Verification and self-review

All Python/Ruff commands used `UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-layouts-venv
uv run --no-sync`. Detailed commands, failed attempts and per-case evidence are in
`.superpowers/sdd/preview-layouts-plan/task-3-report.md`.

- Writer RED: **10 missing-transact failures** → writer/store/committed-reader
  **82 passes**. Native RED: **6 missing-seam failures**; first GREEN attempt
  exposed a missing local ctypes import, corrected before subsequent verification.
- Host RED: **15 missing-capture failures, 10 passes**. Event/native RED cases
  then caught unrecorded painting, lost retained authority on queued release,
  dropped failed-destruction ownership, stale source binding during creation,
  stale metadata membership, post-revocation follow-up rendering/rectangle reads,
  and revoked-creation cleanup loss. Every reproduced boundary was fixed and
  included in the final regression run. Initial test fixture mistakes used the
  wrong reopen key and an invalid/unregistered hotkey shape; corrected to real
  settings/hotkey interfaces rather than weakening production checks.
- Focused store/host/window/admission/runtime/metadata/committed-reader gate:
  **781 passed, 1 Windows-only skip**. Broad Preview/companions/API/transaction
  gate: **3,529 passed, 4 Windows-only skips in 106.19s**. Its earlier attempt
  exposed four metadata-fixture failures from missing native boolean returns;
  those fixtures now return the actual successful `DestroyWindow` contract.
- First full run: **2 failed, 12,729 passed, 13 Windows-only skips in 305.60s**.
  Both failures were the same missing destruction-success return in Wanderer's
  native fixture. Corrected that fixture; follow-up native/lifecycle/Wanderer gate
  **270 passed, 1 Windows-only skip** (also includes the last revoked-cleanup RED).
- Final completed-tree full run:
  `python -m pytest tests/ -q -rs --basetemp=/tmp/wingman-task3-full-final
  --junitxml=/tmp/wingman-task3-full-final.xml` — **12,732 passed, 13 Windows-only
  skips in 312.95s**. No Node/codec prerequisite skips. The failed full XML is
  retained separately as `/tmp/wingman-task3-full-verified.xml`.
- Fresh Ruff lint/format: **passed, 445 formatted**. Node all-page smoke: **PASS**.
  Offline Cargo regression: **1 passed**; release codec availability asserted.
  Final diff whitespace check passed. Self-polish was local only: inspected
  ownership/lock order, failure reporting, comments, interfaces and the final diff;
  applied safe import/format cleanup and the regression-tested corrections above.

No new executor, worker, runtime owner, schema, dependency or source-window action;
no subagents/reviewers, network/GitHub, real app/EVE/profile/clipboard, push/PR/merge,
other worktrees or hook bypass. Fresh coordinator review and Windows/WebView2/live
operator acceptance remain outstanding; portable/native doubles do not establish
visual or real-desktop acceptance.

## Task 3 — fix round 1, retained teardown and final delivery accounting

Base: `639ab5f149ea45051f295c5a48e797467c4d5eab`. All three Important findings
were reproduced before production changes. Only host/window primitives, their two
requested regression files and this evidence changed; no later-task commands/UI.

- `PreviewWindow` records `_teardown_started` before releasing presentation
  resources. Apply treats that retained HWND as incomplete, not healthy visible
  ownership. This remains true if ordinary full-session rebind restores only its
  thumbnail. The conservative approved option is intentional: no automatic repair
  owner/algorithm; existing removal retries real cleanup before healthy recreation.
  Null geometry, failed-HWND ownership and committed preferred geometry survive;
  immediate explicit restore-Off Apply and later-arrival default placement remain
  distinct.
- Final member accounting rechecks the full session in the existing `finally`,
  covering retirement during the last native presentation call as well as refused
  final stages. A check after selection prevents further delivery to a retired
  source. Deferred member context never hides an earlier genuine native failure.
- `_destroy_label_overlay() -> bool` now supplies shared checked retention for
  close and ordinary `set_labels(False)`. Failed label destruction keeps/hides the
  owned HWND; restyling/re-enabling reuses it instead of allocating a duplicate.
  Eventual successful cleanup still destroys the overlay before its primary.

Added 19 regressions using real settings, pump/window paths, native false returns
and actual roster replacements. An Event-held final `ShowWindow` proves release
cannot settle the executing future/lease early. No new worker/timer, off-pump
native work, admission/store/lifecycle rewrite, or real EVE geometry/activation.

Verification uses `UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-layouts-venv uv run
--no-sync`. Initial RED: **18 expected assertion failures** → selected GREEN:
**18 passes**; both requested full files: **215 passes**. Additional mutation RED
proved that thumbnail-only health and pre-final-call checks are insufficient:
**5 expected failures**, then restored the actual fixes before fresh verification.
Broad Preview/companion/Wanderer/API/committed-reader/transaction scope:
**4,018 passed, 5 Windows-only skips in 130.16s**. Local self-polish applied only
safe test formatting. Ruff lint/format passed (**445 formatted**), all-page Node
smoke passed, offline Cargo passed (**1 test**), release codec availability and
`git diff --check` passed.

One final full suite after all fixes:

```sh
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-layouts-venv uv run --no-sync python -m pytest tests/ -q -rs --basetemp=/tmp/wingman-task3-fix1-full --junitxml=/tmp/wingman-task3-fix1-full.xml
```

**12,751 passed, 13 Windows-only skips in 331.65s**; no Node/codec skips. Exact
commands, RED/mutation outputs, interfaces, local-polish scope and concerns are
appended to `.superpowers/sdd/preview-layouts-plan/task-3-report.md`. No subagents,
reviewers, network/GitHub, real app/EVE/profile/clipboard, push/PR/merge or hook
bypass. Coordinator scoped re-review and real Windows acceptance remain pending.

## Task 4 — controller, semantic bridge and revision-safe Preview choices

Base: `a0581968586c422b349a995437fc10d39069c7de`. Added one
`PreviewLayoutsController` and frozen ports over the existing shared store,
admission and host futures. Five one-line named-layout facades and the existing
exclusion facade delegate to it. No named-layout controls, new executor/runtime,
store, gate, schema or native-path rewrite. Main's existing pair is reused exactly,
including host-unavailable startup; production capture reads committed Preview
state and generated IDs use `uuid.uuid4().hex`.

Named operations reserve one nonqueueing slot. Save/Update/Apply acquire exclusive
leases; Rename/Remove and ordinary exclusions use shared leases. Borrowed bridge
threads wait through capture, acknowledged persistence and native settlement,
without controller locks spanning ports/futures/publication. Captures include all
session names, including excluded/failed-primary clients, without modifying the
host's exact capture token. Apply sends that exact token and lease plus every
recorded member key, nulls included; coordinates come from committed authority.
Snapshot-only operations never mirror captured geometry into the host.

Controller view revisions, canonical record hashes and successful store sequences
remain separate. Delayed older exclusion callbacks cannot replace newer accepted
choices; receipts return latest accepted state. A same-choice retry normally avoids
a write, but obtains a newer acknowledged store sequence when a prior successful
callback has not reached the cache. Refusals have no runtime effect. Postcommit
cache/page/native/release failures preserve durable acceptance and warning context;
native outcome is separate. Pending Apply state records successful persistence
while its native future is still unsettled. Final admission/publication closes
before page destruction; controller drain precedes runtime shutdown outside locks,
and timeouts retain both owners for retry.

`onPreviewLayouts` has one literal Api adapter, allowlist entry and production-page
handler. Existing hotkey hydration includes `layout_state` and mirrors its committed
exclusions. The page accepts exclusion state by revision across handlers, hydration
and per-attempt receipts, preserves other drafts/policies and screenshot isolation,
and does not bump the hotkey-table `pushes` counter. Native/external busy without
a pending named operation remains explicitly retryable without a new push or poll;
the maintainer's matching plan clarification is included. No new screen controls
or CSS changed.

### Verification and local self-polish

All Python/Ruff commands used `UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-layouts-venv
uv run --no-sync`. Detailed commands, failed attempts, interfaces and local review
are in `.superpowers/sdd/preview-layouts-plan/task-4-report.md`.

- Controller RED: **26 missing-module failures**. Additional RED caught delayed
  same-choice acknowledgement, release-error settlement and pending durable state.
  Page RED: **8 expected failures** after correcting the DOM-parser setup, covering
  stale hydration/refusal handling and the absent semantic handler.
- Initial integration: **2 failed, 407 passed**; updated legacy receipt assertions
  and a direct-dictionary exclusion fixture to the committed controller interface.
  First broad run: **3 failed, 3,861 passed, 4 Windows-only skips**. Its concurrent
  exclusion test rendezvous now precedes the shared writer instead of deadlocking
  inside its lock; the generated checkbox wrapper again sits immediately after the
  input type assignment. These are recorded failures, not passing coverage.
- Focused controller/page/bridge/API/wiring/transaction/committed-reader/conventions:
  **631 passed**. Includes real pump/controller composition proving actual capture,
  excluded-session membership, exact Apply delivery and unchanged reopen-Off policy.
- Fresh broad Preview/companions/API/bridge/committed-reader/transactions/page/JS/
  startup gate: **3,898 passed, 4 Windows-only skips in 130.43s**.
- Local polish inspected ordering, lock boundaries, final receipts, publication
  fences, legacy compatibility and final diff; safe import/format cleanup applied.
  Ruff lint and format passed (**448 formatted**), all-page Node smoke passed,
  independent offline Cargo passed (**1 test**), release codec availability and
  `git diff --check` passed.

One completed-task full suite:

```sh
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-layouts-venv uv run --no-sync python -m pytest tests/ -q -rs --basetemp=/tmp/wingman-task4-full-verified --junitxml=/tmp/wingman-task4-full-verified.xml
```

**12,809 passed, 13 Windows-only skips in 327.17s**; no Node/codec prerequisite
skips. No subagents/reviewers, network/GitHub, real app/EVE/profile/clipboard,
other worktrees, push/PR/merge or hook bypass. Task 5 controls and Task 6 remain
unimplemented; browser rendering and Windows/WebView2/live-EVE acceptance remain
unverified. No known unresolved Task 4 correctness blocker after local verification.

## Task 4 — fix round 1 cache-authority checkpoint; task gate open

Base: `aa6ee2c86e60f73a12a5af729ce1b6bdb72aefea`. The subsequent review found a
real cache-authority blocker, superseding the earlier local no-blocker claim.
This checkpoint fixes that finding only; the inherited pump-to-page publication
gap requires maintainer architecture approval. **Task 4 is not closed.**

Reproduced Rename through real settings/store while failing only the controller's
serialized geometry projection: disk and receipt acknowledged `Renamed`, but after
restoring serialization a fresh read still returned `Original`. The controller had
lost its successful `LayoutCommit` before recording authority, and owner-only
committed-reader sampling could not restore its records, hashes or exclusions.

`preview/layoutcontroller.py` now retains the latest immutable acknowledged commit
under its short condition before fallible projection/publication, ordered strictly
by the store sequence. `state()` retries a missing projection from that retained
receipt without another mutation, settings write or restart. Failed projection
leaves the previous usable view and logs the failure; successful recovery advances
the view revision. Projection runs outside the condition and rechecks latest
commit identity/sequence before installation, so delayed recovery cannot supersede
a newer accepted generation. Named preflight validation and same-choice exclusion
acknowledgement use immutable authority even while its presentation cache is broken.
No port/wait/page work under locks; no new executor, worker, timer, state writer,
public interface, schema or native-delivery path. Exact capture/lease forwarding,
null-member Apply maps and truthful postcommit persisted results remain unchanged.

Eight new cases in `tests/test_preview_layoutcontroller.py` cover Rename/new-hash
recovery and retry, all other mutations/exclusions, stale sampled dictionaries,
validation and write-free no-op acknowledgement while projection is broken, and
Event-delayed older projection versus newer accepted authority. Existing lifecycle,
reversed-commit, native identity and lock-boundary cases remain green.

All Python/Ruff invocations used `UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-layouts-venv
uv run --no-sync`. Exact commands/XML paths are appended to the ignored Task 4
report. Rename RED: **1 expected failure, 37 deselected**. Expanded controller RED:
**8 expected failures, 37 passed** → controller GREEN: **45 passed**. A mutation
that removed only the post-projection authority check produced **1 expected failure**
(dropped the newer exclusion), then was restored before fresh verification.

Fresh focused gate:

```sh
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-layouts-venv uv run --no-sync python -m pytest tests/test_preview_layoutcontroller.py tests/test_preview_savedlayouts_page.py tests/test_api.py tests/test_preview_wiring.py tests/test_bridge_contract.py tests/test_settings_transactions.py tests/test_settings_committed_preview.py tests/test_preview_layout_admission.py tests/test_preview_layout_batch.py tests/test_preview_runtime.py tests/test_preview_runtime_boundaries.py tests/test_preview_runtime_review.py tests/test_preview_store.py tests/test_page_conventions.py tests/test_js_smoke.py -q -rs --tb=short --basetemp=/tmp/wingman-task4-fix1-cache-focused --junitxml=/tmp/wingman-task4-fix1-cache-focused.xml
```

**811 passed in 33.13s, no skips.** Local `polish-core --fix` reviewed the final
diff, authority/lock/exception paths and tests; only safe Ruff formatting was
applied. Fresh `ruff check .` passed, `ruff format --check .` reported **448 files
already formatted**, all-page Node smoke passed, and `git diff --check` passed.

Fresh broader gate:

```sh
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-layouts-venv uv run --no-sync python -m pytest tests/test_preview*.py tests/test_companion*.py tests/test_api*.py tests/test_bridge_contract.py tests/test_settings_committed_preview.py tests/test_settings_transactions.py tests/test_page_conventions.py tests/test_js_smoke.py tests/test_startup.py -q -rs --tb=short --basetemp=/tmp/wingman-task4-fix1-cache-broad --junitxml=/tmp/wingman-task4-fix1-cache-broad.xml
```

**3906 passed, 4 Windows-only skips in 131.00s**. Skips require the real native
pump/window station or user32/gdi32/dwmapi; no Node/codec prerequisite skips.
No full-suite/Cargo rerun: the coordinator explicitly says no full suite is needed
for this bounded checkpoint.

The inherited native pump → hotkey callback → Api page-publication gap remains
unresolved and untouched; these results do not establish the no-page-work-on-pump
guarantee. The coordinator's architecture investigation found that satisfying the
blanket rule requires broadening the existing Fleet presentation owner/startup and
capture-session interface, or explicitly narrowing the rule to new operation-local
deferral. Either needs maintainer approval; **neither handoff is implemented here**.
The coordinator will ask the maintainer after this clean checkpoint. Do not route
Preview through the conditional recording-folder watcher scheduler or add another
executor/timer. Task 5 per-row feedback/geometry hydration and controls remain
deferred. No subagents/reviewers, network/GitHub, real app/EVE/profile/clipboard,
push/PR/merge/amend or hook bypass. Browser and real Windows/WebView2/live-EVE
acceptance remain unverified.

## Task 4 — approved shared-presentation continuation

Base: `b2b12d70713f8493878c34e76f5b4b4c7df97545`. Implemented the approved
option 1, not operation-local deferral. Api's **same** FleetPresentationWorker
now calls a small dispatcher that drains bounded Preview state before running
the existing Fleet iteration and returning its deadline. Main starts it before
Preview even with Fleet Off, telemetry unavailable and no recording directory.
Starting the retained owner is separate from attaching the Fleet subscription.
No new worker/executor, persistence owner, scheduler, timer or runtime owner.

Main's real native adapters now reach data-only Api ingress: primary dirty bit,
saved-layout dirty bit, newest host-revisioned crop snapshot and one identified
capture event. Every discovered name still reaches LayoutStore.record_character
immediately. Payload sampling/serialization and both WebView deliveries occur
outside mailbox/controller/host/writer/lifecycle locks. Existing worker wakeup
semantics preserve notifications admitted during a blocked delivery. Exceptions
in hotkey/layout/crop presentation do not discard another domain's detached work;
Preview failure cannot bypass Fleet's turn. Wanderer's detached metadata handoff
is unchanged. Final closure clears/rejects queued Preview work before native
teardown and rechecks delivery before each WebView; an already-entered call keeps
the same timed-out worker reference and cannot authorize a replacement.

Capture retains its boolean first argument and adds an optional positive
JavaScript-safe integer session: `set_bind_capture(armed, session=None)` →
`Host.set_capture(armed, session=None)` → native consume →
`push_bind_captured(gesture, session=None)` → `{gesture, session}`. The page uses
one monotonically increasing counter across row switches, section/tab navigation
and screenshot staging. Host admission rejects stale arm/disarm, disarm-before-arm
retires the session, and consume disarms immediately. Untagged legacy calls and
one-argument native callbacks remain supported until identified capture is used;
untagged requests cannot subsequently disarm an identified session. Page results
must match the current session; delayed arm replies and local parse replies retain
their existing attempt ownership. Native-unavailable local keydown still works.
No identity is persisted. This counter is scoped to the one main-page lifetime;
a forced developer reload against a surviving host is not a new page-epoch
protocol or verified acceptance case.

**Coordinator placement ruling applied:** a provisional
`request_working_state_presentation` port was added and tested under the original
amendment, then reported and removed when the coordinator froze geometry as a
coherent Task 5 foundation. Its two controller and two Off/companion-only refresh
cases were also removed. The final controller/ports remain unchanged from the
base. Task 5 must add `refresh_geometry`, its sampler, receipt.geometry,
onPreviewGeometry and getter/Size/keybind guards together, using a geometry-only
dirty bit on this shared owner. This continuation does **not** claim whole-hotkey
refresh establishes geometry ordering or fixes the remaining Off-Apply UI gap.
The coordinator's updated design, plan and amendment text is preserved in the
commit. No Saved layouts controls were added.

### Continuation verification

New Event-held native regressions install the actual main.build_preview_host
callbacks into the existing native pump fixture with the exact shared store/gate.
They exercise discovery, rebind, normal geometry, crop notification, named layout
capture/Apply, visibility and identified key capture while page delivery is held;
native futures, a later pump command and writer flush all complete. Intermediate
seen names survive coalescing, crop delivery retains only revision 50 after 50
notifications and an older arrival, and current state is eventually delivered.
Tests also cover domain failures, deadline preservation, startup independence,
A→B while A's delivery is entered, rejected stale/invalid capture identities,
section/screenshot/local-keydown ownership, both-WebView fences and timed-out
owner retention. Existing synchronous-push tests now drain the real presentation
owner; existing JS callers assert the new optional capture argument explicitly.

All Python/Ruff invocations used
`UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-layouts-venv uv run --no-sync`.
The detailed RED/GREEN commands and failures are in the ignored presentation report.
Initial native RED reproduced synchronous evaluate_js on the pump. Capture RED
rejected the absent session interface/page argument. A later serialization RED
proved a failed crop payload could discard a detached capture; the domain guard
fixed it. Focused and broad checks were run during implementation.

- Broad shared/native/API/page gate: **5,024 passed, 4 Windows-only skips** in
  209.66s (before the coordinator moved the four provisional geometry cases).
- An initial full run found **4 failed, 12,836 passed, 13 Windows-only skips**:
  older Companions/settings-tab harnesses still expected one capture argument,
  and Wanderer's sliced capture harness omitted captureSequence. Only those
  harness contracts needed updating; no Wanderer production changes.
- After the placement ruling and harness corrections, focused native/controller/
  page/startup plus Companions/settings/Wanderer regression: **146 passed**.
- Completed-source full suite:

```sh
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-layouts-venv uv run --no-sync python -m pytest tests/ -q -rs --basetemp=/tmp/wingman-task4-presentation-final-full --junitxml=/tmp/wingman-task4-presentation-final-full.xml
```

**12,836 passed, 13 Windows-only skips in 351.34s**. No missing Node/codec skips.
Node v26.5.0 and release codec availability were checked. `node scripts/js_smoke.js`
passed every page; independent offline Cargo regression passed **1 test** using
`/tmp/wingman-preview-layouts-codec`. Ruff lint passed, format reported **449 files
already formatted**, and git diff --check passed. Local polish inspected final
ownership/exception/capture paths and test seams, removed an orphaned test import
and applied Ruff formatting; no external reviewer/subagent was used. A final
test-only cleanup uses main's explicit store/gate injection rather than patching
its constructor. Post-polish focused verification reran **146 passed in 31.62s**
(`/tmp/wingman-task4-postpolish.xml`), followed by fresh green Ruff lint/format,
all-page Node smoke and diff whitespace checks. No production change followed
the completed full suite.

Task 4 shared-presentation continuation is implemented and verified, pending the
coordinator's review. Geometry ordering/Off refresh/per-row feedback/controls stay
Task 5. Portable regressions do not establish browser rendering or real Windows/
WebView2/live-EVE acceptance. No network/GitHub, app/EVE/profile/clipboard access,
other worktrees, push/PR/merge, amend or hook bypass occurred.

## Task 5 — settled geometry and explicit Saved layouts controls

Base: `11f68b30b76835a48509a82586fee35a2e1b883d`. Task 5 only; the approved
shared presentation owner and Tasks 1–4 remain in place. No Task 6 integration,
new settings, host generation, worker, JavaScript module or route.

### Geometry producer/consumer foundation

Api now serializes fresh committed-Preview and detached host-memory observations
under `_preview_geometry_lock`. Every successful sample advances
`geometry_revision`, including unchanged geometry. Size defaults use committed
layouts/configured defaults; Copy uses retained host layouts even while Off;
Size eligibility combines eligible live names and committed geometry; client
sizes are eligible host samples only. The full getter takes all four fields
from one sample. The now-unused `_preview_sizes` implementation was removed;
its tests exercise the real sampler and committed settings transactions.

The existing presentation mailbox gains only a geometry dirty bit and delivers
`onPreviewGeometry`. Main's data-only callbacks cover discovery, retained geometry,
eligibility and client-size changes. Store callbacks run after successful `_write`,
`replace`, `clear` and `transact` commits, outside writer/settings locks; callback
failure is logged without falsifying durable success. Default-size commits also
notify. Ordinary Reset/default-size refreshes no longer replace the keybind table.
No native, disk, controller-state or page work runs inside the sampling lock.

`PreviewLayoutsPorts.refresh_geometry` runs after native/retained settlement and
before lease release. Final receipts include `geometry`. A failed sample retains
the Api cache (or null), preserves durable success and adds a warning through the
narrow internal `PreviewGeometryUnavailable` exception. Page `acceptGeometry`
maintains one high-water mark for events, receipts and both full-state paths.
Geometry delivery never increments the keybind `pushes` counter. The optimistic
requested-size ACK patch is deleted, including the unsampled 500→600→Apply500 case.
Later ordinary Size/Copy/Reset and newer observations outrank delayed old replies.

### Controls and ownership

The existing Placement disclosure now contains a labelled, page-local selector
and wrapping Apply…, Save current as…, Update saved…, Rename… and Remove… rows.
Selection is never an active layout and makes no bridge call. Named operations
use existing page dialogs and exact record hashes; Save requires known owners.
Capabilities remain advisory for external busy state, preserving explicit retry
without polling. Named pending work blocks conflicting actions, not selection.
Missing hydration blocks every mutation. Names are rendered through DOM text.

Dialogs disarm capture on entry. Capture, navigation and screenshot boundaries
invalidate delayed dialog/parse continuations. A dialog keeps its invoker
focusable for panel.js's synchronous Cancel return; after acceptance, focus moves
locally only if that invoker still owns it. Settled receipts never restore focus.
Screenshot staging retains separate live geometry/layout/selection state and
buffers real receipts without authorizing fixture mutations. Existing group
name drafts and table/capture render ownership are preserved.

Exclusion feedback is visible, full-row and linked with `aria-describedby`.
Refusal, deferred/incomplete outcomes and transport failure remain per owner;
a retry cannot erase another row's error. The single layout status stays mounted.
Reopen-Off consequences use acknowledged settings and a narrow post-ACK event,
not the checkbox's uncommitted value. `settings.js` gained that event only.

`TextPageTree` feeds the production app/previews/panel Node harness.
`screenshot_dom.cjs` consumes opt-in static `node.text` before children; tests
prove real control text survives and structure-only fixtures remain unchanged.
Only `dev.js` and existing fixture transports fabricate data. Its revisioned
saved-layout/geometry fixtures support the new controls and ordinary geometry.

### Task 5 TDD and intermediate verification

All Python/Ruff invocations use
`UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-layouts-venv uv run --no-sync`.
The supplied Task 4 baseline was not rerun.

- Geometry RED: 11 expected missing-sampler/callback failures after correcting
  test setup to initialize Preview. Initial geometry/controller GREEN: 56 passed.
- Retained second-drag RED exposed the missing pre-debounce notification; the
  callback and post-commit tests now distinguish Copy and Size authorities.
- Four production-page geometry scenarios failed on missing onPreviewGeometry;
  the foundation gate then passed 233 tests, 35 DOM tests and all-page JS smoke.
- Fourteen control/per-row scenarios failed before markup/behavior existed.
  Subsequent RED cases covered rejected exclusion promises, stale Size-dialog
  navigation/capture, ordinary Reset replacing keybind state, acknowledged reopen
  events, and revisioned dev geometry.
- Broad intermediate gate: 3,363 passed, 4 Windows-only skips, 2 failures. The
  failures were an old test bypassing committed geometry and the lexical grid
  guard counting full-width feedback as a sixth collapsed cell; both corrected.
- Later page/settings/dev/shooter/wiring gate: 756 passed. Post-polish focused
  geometry/page/API/settings-field/wiring/dev gate: 465 passed in 31.91s.
- Ruff lint passed; format reported 450 files formatted. Node all-page smoke
  passed. Offline Cargo regression passed 1 test using the supplied target dir.

### Browser evidence — separate from Windows acceptance

Chrome `152.0.7977.64` at the supplied CDP endpoint. Each run created a new
isolated BrowserContext and pages, closed only that context and disconnected;
no existing tabs, cookies or profile were used. Requests were restricted to
`http://127.0.0.1:45063`, serving this worktree's web assets. An initial attempted
port 8767 was occupied by an older local checkout; actual DOM inspection caught
that mismatch before interaction, and it was not used as evidence.

At 840×625 and 839×621, document width equals the viewport, and the Preview
subpage has matching client/scroll widths (624/624 and 623/623). The saved selector
measures 592px/591px; all action edges fit. Two action rows retain wrapping.
The mounted status is 18px high for tested one-line outcomes. Keyboard Save,
Escape cancellation, destructive Cancel focus, selection/no-extra-read behavior,
pending selection, geometry-push scroll/focus and two independent row errors
were exercised. Browser checks caught and fixed the shared 150px select basis,
dialog invoker focus loss and inherited 24px indentation on later row feedback.
Screenshots were inspected for layout and readable errors, not only captured.

Portable evidence: `/tmp/task5-browser-evidence.json`,
`/tmp/task5-browser-final.cjs`, `/tmp/task5-browser-final.log`,
`/tmp/task5-empty-{840,839}.png`, `/tmp/task5-pending-{840,839}.png`,
`/tmp/task5-error-{840,839}.png`, `/tmp/task5-row-errors-{840,839}.png`.
These checks are **not Windows/WebView2/live-EVE acceptance**. No real app,
EVE, profile, clipboard, external network, GitHub, subagent/reviewer, push/PR,
merge/amend or hook bypass was used.

### Final gate status

Implementation commit: `ccecd376` — `feat(previews): publish settled geometry and
add saved layout controls`. Local polish used the explicit Task 5 base, no
subagents. It removed the orphaned Size helper, kept the new host callback at the
end of the positional signature, clarified shared/exclusive admission wording,
and applied Ruff's safe import/context/format corrections.

The first full run finished with **12,877 passed, 13 Windows-only skips and
6 failures in 392.02s** (`/tmp/wingman-task5-final-full.{log,xml}`). All six were
older harness assumptions: omitted `_devLayouts` in the group dev slice, omitted
`detailInteraction` in the Wanderer capture slice (two tests), fixture geometry/
exclusion edits without newer revisions (two tests), and expected group-dialog
writes after navigation/new capture. The recovery changed only those test seams;
no production correction was required. The focused recovery gate passed
**74 tests in 15.42s** (`/tmp/task5-harness-recovery`). The completed-source full
rerun was pending at that checkpoint. The test-only recovery is committed as
`4f05ea5d` — `test(previews): align legacy harnesses with settled geometry ownership`.

Completed-source final verification:

```sh
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-layouts-venv uv run --no-sync python -m pytest tests/ -q -rs --basetemp=/tmp/wingman-task5-verified-full --junitxml=/tmp/wingman-task5-verified-full.xml
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-layouts-venv uv run --no-sync ruff check .
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-layouts-venv uv run --no-sync ruff format --check .
node scripts/js_smoke.js
cargo test --locked --offline --manifest-path packaging/settings-codec/Cargo.toml --target-dir /tmp/wingman-preview-layouts-codec
git diff --check
```

**12,883 passed, 13 Windows-only skips in 367.94s**. No Node/codec skips.
Log: `/tmp/wingman-task5-verified-full.log`; XML as above. Fresh Ruff lint passed,
format reported **450 files already formatted**, every page passed JS smoke,
Cargo passed **1 test**, and diff whitespace checks passed. Final two-floor
browser verification also passed after the alignment/focus fixes, with zero
page errors. No source or test change followed the successful full run.

Task 5 is implemented and locally verified. The exact task report is
`.superpowers/sdd/preview-layouts-plan/task-5-report.md`. Windows/WebView2/live-EVE
acceptance remains explicitly unverified; Task 6 and branch integration were not
performed. No remaining portable gate or known Task 5 production correctness
finding from this local pass.

## Task 5 — fix round 1, page-lifetime corrections

Base: `891c9c743a580e548d837942399b5233f88209b3`. The coordinator's review
found three concrete gaps, superseding the earlier local no-finding claim.
**All three are fixed and verified below; Task 5's gate remains OPEN for scoped
coordinator re-review. Task 6 is untouched.**

### Changes / interfaces

- `web/previews.js` detaches the fixture's `state` target before invoking full
  hydration. `acceptLayouts`/`acceptGeometry` can no longer overwrite the retained
  live object while `screenshotLive` is not yet installed. Plain entry/exit with
  no live payload preserves geometry, exclusions, layout selection and feedback;
  existing independent revisions and real-reply buffering remain unchanged.
- Copy's chooser checks its captured `detailInteraction` and `copyAttempt` before
  any mutation or cancellation-side effect. Navigation, completed staging, newer
  Configure/capture/chooser attempts revoke **admission**, not settlement of work
  already sent. The existing admitted-Copy status/refresh path stays unchanged.
- `web/panel.js` tracks one internal `returnFocusOwned` boolean for the existing
  dialog queue. Focus outside the visible overlay revokes return ownership until
  that queue drains, even after blur or focus back into the dialog. Final `next()`
  skips obsolete restoration before promise continuations run. Ordinary owned
  Cancel, Escape, queue advancement, focus trap, scrim and rendered fallback stay
  intact. No per-dialog option or public signature was needed; no control was
  disabled as a focus workaround.
- Ten production app/previews/panel scenarios added; Saved/Size tests now assert
  `document.activeElement` identity and armed capture, not only labels and write
  count. The interactive fixture alone supplies bubbling `focusin`; the shared
  structure-only DOM helper is unchanged. No backend/sampler/native/runtime/store,
  schema, bridge, worker or source-window behavior changed.

### RED / GREEN and local polish

Every Python/Ruff command uses
`UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-layouts-venv uv run --no-sync` in the
existing `feature/preview-layouts` linked worktree.

- `python -m pytest tests/test_preview_savedlayouts_page.py -k 'roundtrip or copy
  or controls-capture or geometry-dialog-capture' -q --tb=short
  --basetemp=/tmp/task5-fix1-red-page --junitxml=/tmp/task5-fix1-red-page.xml`:
  **10 failed**. Fixture999x777 instead of live500x300 and stale Copy writes
  reproduced directly; cyclic-DOM assertion diagnostics caused three timeouts.
  Changing only the diagnostic assertions to boolean identity comparisons and
  repeating with `/tmp/task5-fix1-red-page2` and matching XML gave **10 failures
  in 5.61s**, including explicit Saved/Size focus theft. One extra admitted-Copy
  test had not actually changed tabs; corrected to Characters→Windows.
- Staging tests were corrected to use a rejected Save (not an authoritative
  duplicate-name receipt that itself excluded Bob) and to inspect Size before
  applying exclusions that intentionally disable that control. Staging GREEN:
  `python -m pytest tests/test_preview_savedlayouts_page.py -k '(roundtrip or
  staging or staged or admitted) and not copy-dialog' -q --tb=short
  --basetemp=/tmp/task5-fix1-green-staging2`: **6 passed in 3.90s**.
- Copy GREEN/focus RED: `python -m pytest tests/test_preview_savedlayouts_page.py
  -k 'copy or controls-capture or geometry-dialog-capture' -q --tb=short
  --basetemp=/tmp/task5-fix1-green-copy-red-focus`: **6 passed, 3 expected focus
  failures in 5.19s**. Copy now refuses stale sends; shared panel still stole
  Saved/Size/Copy capture focus before its fix.
- Queue/history RED: `python -m pytest tests/test_preview_savedlayouts_page.py
  -k 'dialog-focus-history or dialog-owned-cancel' -q --tb=short
  --basetemp=/tmp/task5-fix1-red-focus-history`: **1 expected failure, 1 passed**.
- After the panel guard, `python -m pytest tests/test_preview_savedlayouts_page.py
  -q --tb=short --basetemp=/tmp/task5-fix1-green-page
  --junitxml=/tmp/task5-fix1-green-page.xml`: **48 passed in 14.00s**.

Local diagnose/TDD/receiving-code-review and scoped blind-spot/polish passes only;
no independent reviewer, subagent or CodeRabbit. `polish-core --fix` inspected the
explicit-base diff and relevant hydration, queued focus and Copy consumers. Safe
cleanup removed one redundant local test-helper declaration; no further production
change. Repository ES5 and ownership conventions take precedence over generic
modern-JS simplification. Full per-command intermediate failures are retained in
`.superpowers/sdd/preview-layouts-plan/task-5-report.md` and matching `/tmp` logs.

### Portable final verification

An initial broader command used nonexistent `test_settings_tabs_runtime.py` and
collected nothing. Corrected gate:

```sh
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-layouts-venv uv run --no-sync python -m pytest tests/test_preview_savedlayouts_page.py tests/test_preview_crops_page.py tests/test_preview_labelmarkers_page.py tests/test_preview_group_backward.py tests/test_preview_warning_grouping.py tests/test_settings_runtime.py tests/test_settings_page.py tests/test_page_conventions.py tests/test_bridge_contract.py tests/test_dev_harness.py tests/test_shoot_screens.py tests/test_fittings_page.py tests/test_js_smoke.py -q -rs --tb=short --basetemp=/tmp/task5-fix1-broad-ui2 --junitxml=/tmp/task5-fix1-broad-ui2.xml
```

**814 passed in 85.91s**, no skips. Shared-panel Fittings consumers, settings/tab
runtime, Preview crop/marker/group owners, dialog/page conventions and dev/shooter
coverage justify this broader UI scope. Log `/tmp/task5-fix1-broad-ui2.log`.

One completed full suite after local polish, justified by shared-panel/interactive
DOM changes, not one per edit:

```sh
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-layouts-venv uv run --no-sync python -m pytest tests/ -q -rs --basetemp=/tmp/task5-fix1-final-full --junitxml=/tmp/task5-fix1-final-full.xml
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-layouts-venv uv run --no-sync ruff check .
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-layouts-venv uv run --no-sync ruff format --check .
node scripts/js_smoke.js
node --test tests/fixtures/screenshot_dom.test.cjs
cargo test --locked --offline --manifest-path packaging/settings-codec/Cargo.toml --target-dir /tmp/wingman-preview-layouts-codec
git diff --check
```

**12,893 passed, 13 Windows-only skips in 367.83s**, no failures/errors. Full log:
`/tmp/task5-fix1-final-full.log`; XML as above. All skips inspected: junctions,
DPAPI/WinDLL, real pump/user32/gdi32/dwmapi and Windows tray backend; no Node/codec
skips. Ruff lint passed; format reported **450 files already formatted**; all-page
JS smoke passed; DOM tests **35 passed**; offline Cargo **1 passed**; whitespace
check passed. No production/test changes followed the completed full suite.

### Browser DOM / screenshots — not Windows acceptance

`node /tmp/task5-fix1-browser.cjs` rechecked Chrome **152.0.7977.64** through the
supplied localhost:9222 endpoint, using a **new isolated BrowserContext** and new
pages only. No existing tabs/profile/cookies were used. Its temporary server served
only worktree web assets from a dynamically allocated loopback port, with all
nonmatching requests blocked; no outgoing request was attempted. It closed only
its own pages/context/server and disconnected, leaving the shared Chrome running.

Both **840×625** and **839×621** passed. Document width equals viewport; Preview
client/scroll widths **624/624**, **623/623**; selectors **592/591**. Original
wrapping, mounted status, keyboard Save/Escape, destructive Cancel, zero reads for
selection/subpages, pending selection, geometry focus/scroll and independent row
errors passed. New checks prove plain fixture entry/exit preserves live defaults,
choices, selection and feedback; old Saved/Size/Copy answers leave the actual active
focus on the newer still-armed capture; stale Copy staging/navigation/attempts send
zero writes; blur→dialog re-entry→queued settlement cannot revive old return focus.
Owned Size/Copy queue/Escape return and unavailable-invoker visible fallback pass.

Evidence JSON: `/tmp/task5-fix1-browser-evidence.json`; driver/log:
`/tmp/task5-fix1-browser.{cjs,log}`. Screenshots:
`/tmp/task5-fix1-{empty,pending,error,row-errors,focus}-{840,839}.png`.
**Both error and focus screenshots were read and visually inspected**: Saved
controls wrap and feedback fits; Zuelo Parvi's “Press a key…” has the visible focus
ring with no dialog left over it. Other screenshots were captured; their measured
assertions are DOM evidence rather than additional visual judgment.

Windows/WebView2/live-EVE, native focus/input, mixed-DPI/monitor rescue and actual
source bounds remain unverified. No real app/EVE/profile/clipboard, external
network/GitHub, push/PR/merge/amend/--no-verify or Task 6 action. Re-review focus:
pre-hydration detachment, chooser admission versus already-sent receipts, and the
shared queue's sticky return-focus ownership. Task 5 gate remains open.

## Task 6 — documentation and acceptance preparation

Documentation baseline: `c4a924cbef01cfdb369738a0ca59b977fc124427` —
`fix(previews): fence staging and revoked dialog ownership` on
`feature/preview-layouts`. Tasks 1–5 implementation and task-scoped reviews are
complete. In particular, the scoped Task 5 re-review accepted pre-hydration
fixture detachment, stale Copy admission fencing and sticky dialog return-focus
ownership, with no new Critical/Important finding. This supersedes the pending
Task 5 review status above, **not** the earlier run records or their limits.
The ignored `task-5-rereview-1.md` records that verdict and its separate isolated
Chrome scrim/fresh-queue probe. No review or browser exercise was rerun in this
documentation pass.

### Reviewer summary — boundaries and rulings

- **Controller/admission:** `preview/layoutcontroller.py` orchestrates named
  operations through ports on borrowed bridge threads. A nonqueueing named slot
  and the shared `PrimaryLayoutAdmission` are distinct: Save/Update/Apply are
  exclusive; metadata and ordinary exclusions can share admission. Geometry
  commands/gestures retain their exact leases through completion, not just a
  bridge queue ACK. Ports, waits and publication stay outside controller locks.
- **Store:** the existing `LayoutStore.transact` serializes with ordinary writes,
  drains pending geometry/names, merges the proposed snapshot change in one real
  settings transaction, and prepares normalized detached commit authority before
  saving. Failure restores drained work with newer pending geometry winning.
  Successful store sequence, controller view revision, record hash and geometry
  observation revision are different authorities. A committed receipt is retained
  before fallible cache projection, so a later read can repair the cache without
  writing or restarting. Named snapshots never become working-arrangement autosave.
- **Native:** the host pump alone captures actual owned rectangles and applies
  committed member batches, with full captured session/epoch checks. The Apply
  map includes null members for visibility/failure accounting, not geometry
  replacement; absent members are not touched. Immediate re-inclusion uses the
  snapshot even with reopen Off; later arrivals follow the preference. Monitor
  rescue changes applied Wingman rectangles, not preferred geometry. A commit
  survives source loss/Off/native failure with deferred/incomplete context; there
  is no desktop-wide atomic paint or native rollback promise.
- **Existing owners:** primary Reset runs through CropStore's retained command
  worker. The approved detached continuation may settle storage/cache after
  revocation or where no native phase can execute; live failed posts retain
  readiness for an existing pump turn. Off fences immediately, final admission
  closes before destruction, and entered work retains ownership through drain.
  Timeouts do not authorize overlapping replacement owners.
- **Presentation:** the maintainer explicitly approved reusing Api's existing
  `FleetPresentationWorker`, not another worker or an exception to the blanket
  no-page-work-on-pump rule. It starts before Preview independently of Fleet,
  telemetry and recordings. Callbacks admit seen names immediately and coalesce
  bounded dirty/crop/identified-capture notifications. Sampling/page delivery
  occurs outside native/writer/controller locks; final ingress/delivery fences
  cover both WebViews. A blocked page does not own native or writer completion.
- **Geometry/page:** one ordered fresh projection preserves committed Size
  defaults versus retained Copy geometry. Store and host dirty notifications are
  both required across debounce; equal observations still advance revision.
  Successful operations request a fresh sample after native/retained settlement,
  before release; sampling failure retains the last cache (or null), warns and
  does not downgrade durable success. Events, getters and final receipts use one
  page high-water mark, independently of layout/keybind revisions; ordinary Size
  ACKs are not geometry. Selection
  stays local, exclusions retain per-row feedback, fixture state is detached
  before hydration, and delayed dialogs must still own admission/focus. An
  already-sent Copy receipt still settles after navigation. Capture identity is
  page-lifetime-only, not persisted or a forced-page-reload protocol.

The other material ruling is lossless explicit exclusions, not a larger recent
roster cap or capacity-based Apply refusal. No new package, dependency, version,
importer (#216), snapshot keybind, crop/companion snapshot, named autosave, backup
history or persisted active selection is part of this slice.

### Spec-to-evidence map

This maps the [approved spec](preview-layouts-design.md) and
[publication amendment](preview-layouts-publication-amendment.md) to existing
assertions, not to Windows acceptance. Named-test anchors are relative to `tests/`;
standalone file paths are repository-relative. `[scenario]` denotes the actual
parametrized node. The read-only inventory was
verified at `891c9c743a580e548d837942399b5233f88209b3`; current names and the
reviewed Task 5 fix assertions were checked at the documentation baseline.
No stale source line numbers are used as acceptance anchors.

| Spec section / requirement | Existing assertion anchors | Evidence layer and limit |
| --- | --- | --- |
| Approved behavior — explicit scope and unchanged globals | `test_preview_savedlayouts.py::test_record_roundtrip_is_detached_and_excludes_global_fields`; `test_preview_savedlayouts.py::test_apply_changes_only_recorded_geometry_and_visibility_and_keeps_legacy_locks` | Pure frozen/detached records exclude lock/HWND data; merge compares the remaining settings dictionary. This is not live crop/companion/Wanderer independence or source-bounds evidence. |
| Approved behavior / User interaction — explicit CRUD, stable IDs/hashes | `test_preview_layoutcontroller.py::test_save_and_update_capture_all_sessions_live_and_offline_without_moving`; `test_preview_layoutcontroller.py::test_rename_noop_and_remove_leave_working_arrangement_alone`; `test_preview_layoutcontroller.py::test_stale_or_missing_record_has_no_write_or_native_effects`; `test_preview_savedlayouts.py::test_revision_ignores_character_insertion_order_but_tracks_snapshot_changes` | Real controller/settings/store, controlled native ports; snapshot-only capture does not replace working geometry, stale mutations refuse, canonical hashes track record changes. No installed UI/native run. |
| Data and compatibility — schema, validation, migration | `test_preview_savedlayouts.py::test_load_keeps_first_valid_id_and_casefolded_name_not_partial_members`; `test_preview_savedlayouts.py::test_extents_and_far_edge_arithmetic_must_be_native_safe`; `test_settings_savedlayouts.py::test_legacy_working_state_does_not_acquire_a_fabricated_snapshot`; `test_settings_savedlayouts.py::test_snapshot_normalization_survives_save_reload_and_unrelated_update` | Pure whole-record validation plus real settings normalization/save/reload. No fabricated migration; no promise of retention through older binaries. |
| Data and compatibility — lossless exclusions | `test_settings_savedlayouts.py::test_apply_exclusion_merge_over_capacity_is_lossless_in_either_order`; `test_settings_savedlayouts.py::test_failed_persistence_restores_all_exclusions_and_snapshot_state`; `test_settings_savedlayouts.py::test_explicit_exclusions_survive_reload_without_expanding_history`; `test_settings_savedlayouts.py::test_direct_preview_choice_transactions_retain_all_other_exclusions` | Real transactions/reload retain exclusions beyond recent history in either order; rollback preserves prior data/disk bytes. The direct-choice test is a transaction test, not bridge integration. |
| Data / User interaction — known, excluded-only and saved-only owners | `test_preview_savedlayouts.py::test_known_owners_unions_every_explicit_source_without_casefold_or_cap`; `test_preview_labelmarkers_page.py::test_marker_page_ownership[exclusions]`; `test_preview_savedlayouts_page.py::test_saved_layout_page_ordering[controls-empty]` | Pure exact owner union includes saved-only owners; production JS/DOM doubles keep excluded-only/prototype-like names editable Off. The empty-list page case permits saving known offline owners. No direct saved-only-row assertion, rendering or end-to-end settings-to-WebView coverage is claimed. |
| Capture, apply and ownership — live/default/offline/null/absent | `test_preview_layout_batch.py::test_capture_actual_default_and_live_excluded_offline_detached`; `test_preview_layout_batch.py::test_apply_transaction_is_lossless_for_absent_and_null_members`; `test_preview_layout_batch.py::test_null_unchanged_visibility_checks_recorded_creation_only`; `test_preview_layout_batch.py::test_offline_capture_and_apply_never_start_or_touch_native` | Real settings/writer/host with native doubles; actual-double rectangles differ from cache, untouched defaults are not auto-persisted, null keeps geometry and recorded membership still counts for creation failure. Off/companion-only paths do not start EVE. |
| Capture / Approved behavior — immediate Apply versus later reopen | `test_preview_layout_batch.py::test_restore_off_reenabled_member_uses_explicit_rect_now_but_not_on_later_arrival`; `test_preview_host.py::test_the_setting_is_read_per_placement_not_captured` | Host/native-double placement distinguishes immediate restore-Off Apply from later replacement; existing placement reads the preference anew. Both installed reopen modes and restart remain unrun. |
| Capture and ownership — admission, Reset, pending/later writes | `test_preview_layout_admission.py::test_shared_leases_finish_independently_and_ids_do_not_reuse`; `test_preview_layout_admission.py::test_consumed_resize_wake_waits_for_reset_storage_and_retains_leases`; `test_preview_cropstore.py::test_primary_action_uses_existing_worker_and_precedes_close`; `test_preview_layout_batch.py::test_batch_cannot_overtake_an_earlier_debounce`; `test_preview_store.py::test_successful_transaction_leaves_later_recorded_delta_pending` | Pure gate plus Event-controlled real writer/worker ordering with native doubles: every represented lease survives, Reset uses the retained worker, earlier debounce precedes batch and later delta remains pending. Not real Windows input scheduling. |
| Capture and ownership — native checks, untouched members and locks | `test_preview_window.py::test_checked_native_rectangle_never_fabricates_cached_geometry`; `test_preview_window.py::test_checked_move_does_not_adopt_failed_geometry`; `test_preview_window.py::test_checked_resize_updates_label_thumbnail_and_invalidates_active_alert`; `test_preview_layout_batch.py::test_noop_persisted_apply_still_moves_divergent_live_without_changing_globals`; `test_preview_layout_batch.py::test_batch_never_paints_an_unrecorded_member` | Owned-HWND/native doubles check false returns, cache/label/thumbnail/alert maintenance, moving locked Alice while absent Bob and settings stay unchanged. They do not observe real EVE bounds, foreground, rendered labels or live alerts. |
| Capture and ownership — replacement sessions / monitor rescue | `test_preview_layout_batch.py::test_source_replacement_during_native_capture_refuses`; `test_preview_layout_batch.py::test_replacement_session_never_receives_explicit_geometry`; `test_preview_layout_batch.py::test_replacement_during_create_never_binds_stale_batch_source`; `test_preview_layout_batch.py::test_monitor_rescue_never_changes_preferred_geometry` | Native doubles fence capture/batch/DWM source identity and preserve working/retained preferred coordinates while clamping live placement. Rescue does not directly assert named-record byte equality or real mixed-DPI behavior. |
| Outcomes and recovery — rollback, committed failure, cache recovery | `test_preview_layout_batch.py::test_failed_batch_keeps_the_prior_drag`; `test_preview_layout_batch.py::test_native_failure_is_incomplete_and_retains_commit`; `test_preview_layout_batch.py::test_visible_apply_after_partial_teardown_stays_incomplete_until_cleanup`; `test_preview_layoutcontroller.py::test_rename_projection_failure_recovers_new_hash_without_write_or_restart`; `test_preview_layoutcontroller.py::test_failed_cache_recovers_all_mutations_from_commit_not_sampled_preview` | Real persistence with injected failure/native ports; preserve pending drag, committed native-incomplete state/ownership and recover cache from immutable commit, not a sampled stale dictionary. These are exercised fault seams, not live fault injection. |
| Ownership / Outcomes — Off, final close, retained drain | `test_preview_layout_admission.py::test_final_barrier_waits_for_reset_and_admitted_resize_completion`; `test_preview_layout_batch.py::test_executing_native_future_cannot_release_early`; `test_preview_layoutcontroller.py::test_pending_stages_keep_slot_and_lease_until_settlement_and_shutdown_can_retry` | Event-controlled host/controller/worker lifetime: close cannot pretend entered work finished; timed-out owners remain tracked. Actual Quit/process/native teardown is NOT RUN. |
| Amendment — shared presentation and independent startup | `test_preview_presentation.py::test_main_adapters_never_present_on_pump_and_coalesce_while_page_blocked`; `test_preview_presentation.py::test_final_close_fences_both_pages_and_retains_entered_worker`; `test_startup.py::test_preview_presentation_starts_before_preview_without_fleet_telemetry_or_recordings` | Actual production main adapters/Api/writer plus controlled native pump and fake pages: reached page calls are off-pump, blocked delivery permits native/writer progress, seen admissions survive coalescing, startup/final fences retain one worker. Not real WebView2 or native OS. |
| Amendment — identified capture | `test_preview_presentation.py::test_identified_capture_through_main_while_old_delivery_is_blocked`; `test_preview_savedlayouts_page.py::test_capture_session_page_ordering[reversed]`; `test_preview_savedlayouts_page.py::test_capture_session_page_ordering[local]`; `test_preview_savedlayouts_page.py::test_capture_session_page_ordering[boundary]` | Production adapters/native doubles and production JS/DOM doubles cover old-session delivery, reversed requests, local fallback, section/staging boundaries. Physical key capture and native focus remain unrun. |
| Amendment — settled geometry producer | `test_preview_geometry_publication.py::test_every_fresh_sample_advances_even_without_a_value_change`; `test_preview_geometry_publication.py::test_store_notifies_only_after_writer_and_settings_release`; `test_preview_geometry_publication.py::test_apply_samples_unchanged_offline_geometry_before_release`; `test_preview_geometry_publication.py::test_retained_drag_and_commit_notify_distinct_authorities`; `test_preview_geometry_publication.py::test_off_apply_refreshes_retained_geometry_without_eve_start` | Real Api/settings/store/controller and main-adapter/native doubles: separate Size/Copy authorities, post-lock notifications, equal fresh observations, settlement before release and Off/companion-only refresh. Not cross-source atomicity or installed behavior. |
| User interaction / Amendment — page ordering and geometry consumer | `test_preview_savedlayouts_page.py::test_saved_layout_page_ordering[controls-unhydrated]`; `test_preview_savedlayouts_page.py::test_saved_layout_page_ordering[controls-select]`; `test_preview_savedlayouts_page.py::test_saved_layout_page_ordering[controls-pending]`; `test_preview_savedlayouts_page.py::test_saved_layout_page_ordering[geometry-ack]`; `test_preview_savedlayouts_page.py::test_saved_layout_page_ordering[geometry-getter]`; `test_preview_savedlayouts_page.py::test_saved_layout_page_ordering[row-feedback]` | Production app/previews/panel and real Api-generated receipts with DOM/bridge doubles: no pre-hydration mutation or selection reads, pending ownership, Apply versus delayed ACK/later writers, stale getters and independent row errors. Not CSS, WebView2 or actual focus. |
| User interaction — reviewed staging / dialog corrections | `test_preview_savedlayouts_page.py::test_saved_layout_page_ordering[staging-roundtrip]`; `test_preview_savedlayouts_page.py::test_saved_layout_page_ordering[copy-dialog-navigation]`; `test_preview_savedlayouts_page.py::test_saved_layout_page_ordering[copy-dialog-subpage]`; `test_preview_savedlayouts_page.py::test_saved_layout_page_ordering[copy-dialog-staging]`; `test_preview_savedlayouts_page.py::test_saved_layout_page_ordering[copy-dialog-configure]`; `test_preview_savedlayouts_page.py::test_saved_layout_page_ordering[copy-dialog-attempt]`; `test_preview_savedlayouts_page.py::test_saved_layout_page_ordering[copy-dialog-capture]`; `test_preview_savedlayouts_page.py::test_saved_layout_page_ordering[copy-admitted-subpage]`; `test_preview_savedlayouts_page.py::test_saved_layout_page_ordering[controls-capture]`; `test_preview_savedlayouts_page.py::test_saved_layout_page_ordering[geometry-dialog-capture]`; `test_preview_savedlayouts_page.py::test_saved_layout_page_ordering[dialog-focus-history]`; `test_preview_savedlayouts_page.py::test_saved_layout_page_ordering[dialog-owned-cancel]` | Current fix assertions cover plain no-push roundtrip; every stale chooser boundary; already-admitted Copy settlement; actual `activeElement` identity in the DOM double with armed capture; sticky revocation and owned queued Cancel. These replace the inventory's stale pending-gap assessment, not Windows focus acceptance. |
| Evidence and required verification — bridge/conventions/browser/native | `test_bridge_contract.py::test_preview_layout_facades_are_exact_single_line_delegates`; `test_bridge_contract.py::test_preview_layout_semantic_handler_and_private_controller_boundary`; `tests/test_page_conventions.py`; `scripts/js_smoke.js`; Task 5 browser records above | Lexical guards and executable top-level smoke complement focused runtime tests. Previously recorded isolated Chrome runs exercised actual DOM/CSS at both floors, not WebView2/live EVE. Fresh whole-branch gates and the Windows checklist remain pending below. |

The page fixture's `controls-empty` case has no named layouts but does have
known offline owners; it is not an empty-roster or saved-only-row assertion.
`test_preview_savedlayouts_page.py::test_saved_layout_page_ordering[controls-unavailable]`
checks unavailable capture controls; empty capture refusal is asserted by
`test_preview_layoutcontroller.py::test_save_empty_and_duplicate_id_refuse_without_replacing_records`.
Do not turn a test name, whole-dictionary equality, a native double or a screenshot
into stronger acceptance than its assertions support.

### Verification and pending integration boundary

Earlier task results, failed attempts, corrected reruns, prerequisite checks and
Windows-only skips remain recorded above. The Task 5 fix report's full run and
Ruff/JS/DOM/Cargo results were inspected by its scoped re-review; they are **not**
a fresh post-final-review branch gate. This documentation pass ran the following
with `UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-layouts-venv uv run --no-sync`:

- `python -m pytest tests/test_documentation.py tests/test_page_conventions.py
  -q -rs --basetemp=/tmp/task6-preview-docs-conventions
  --junitxml=/tmp/task6-preview-docs-conventions.xml` — **155 passed**, no skips.
- `python -m pytest tests/test_packaging_completeness.py -k 'readme or smoke or docs'
  -q -rs --basetemp=/tmp/task6-preview-docs-packaging
  --junitxml=/tmp/task6-preview-docs-packaging.xml` — **8 passed, 88 deselected**,
  no skips. Only the affected documentation assertions, not a packaging build.
- `python /tmp/task6-preview-docs-check.py` — local Markdown links/fragments and
  named-test definitions/parameters checked against the supplied base; no errors.
  External links were skipped without requests. This is AST/link validation,
  not execution of the coverage matrix. `git diff --check` also passed.

Docs-only local polish inspected the diff and tightened null-geometry, saved-only
coverage and receipt-sampling claims; no source changes or independent review.
Exact outputs, final reruns and the normal docs commit are recorded in
`.superpowers/sdd/preview-layouts-plan/task-6-docs-report.md`.

**Still pending — coordinator:** fresh final whole-branch changed-code review,
branch-wide polish with safe edits inspected, then the plan's fresh full pytest
(with Node and this checkout's built release codec), Ruff lint/format, all-page
Node smoke, independent Cargo regression and final diff check. Inspect every
failure/skip and rerun after any correction. No full suite, Ruff, all-page Node
or Cargo gate was rerun by this documentation task, and no CodeRabbit or additional
reviewer was invoked here.

**Still NOT RUN — authorized Windows acceptance:** the
[Saved layouts smoke matrix](smoke-checklist.md#saved-layouts-213--windows-acceptance-not-run)
covers real EVE bounds/foreground, multiple/hidden/offline/null/absent members,
both reopen modes, source replacement, locks/labels/alerts/Wanderer, independent
crops/companions, mixed-monitor rescue, pending ordinary edits, Off/on/restart/Quit
and actual WebView2 capture/dialog focus. None is established by portable tests
or isolated Chrome. No real app, EVE, profile, clipboard or browser effect was
performed in this task.

**Integration remains separate:** no push, PR, merge, amend or release; obtain
explicit integration authorization after the coordinator's gates and the agreed
acceptance decision. Preserve this linked worktree for feedback. Do not close
#213 before that decision; do not infer permission from completed implementation,
task reviews or this documentation commit.
