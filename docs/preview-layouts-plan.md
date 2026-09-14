# Saved Preview Layouts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Save, apply, update, rename and remove explicit primary-preview snapshots without losing offline choices or weakening native/persistence ordering.

**Architecture:** One small controller orchestrates named operations on the existing bridge-call thread. One shared admission object orders them against ordinary primary geometry/visibility work; the existing `LayoutStore` serializes persistence and the existing host pump captures/applies native geometry. Named operations do not add an executor or runtime owner.

**Tech Stack:** Python 3.11+, existing settings transactions and injected Win32 seams, plain HTML/CSS/ES5, pytest and Node page harnesses.

**Spec:** [preview-layouts-design.md](preview-layouts-design.md), including the accepted lossless-exclusion revision. Approved for planning after an independent SHIP verdict; implementation and runtime acceptance are still outstanding.

**Planning baseline:** source `76afd3dc34f20eb071c97f25cd6d891ae11c352a`, design `9f9734a4d414054e1f1c89dd585fd65dfe361576`. Existing symbols below refer to that source baseline; new interfaces are explicitly marked proposed.

## Global constraints

- Named layouts are **explicit snapshots**; ordinary edits persist only the working arrangement.
- Snapshot scope is primary-preview position, size and Preview visibility. Locks, crops, companions, keybinds, appearance and global policies stay global.
- Absent members remain unchanged; a null rectangle leaves current geometry unchanged.
- Apply uses saved geometry now where possible, without changing **Reopen previews where you last put them**. Later client openings follow that preference.
- Explicit exclusions retain all valid owners. Do not raise the 64-entry recent-history cap or alter unrelated per-character policy caps.
- No EVE source geometry, activation, native identity persistence, network, import, dependency or new package.
- `Api` orchestration belongs behind ports; all its non-method attributes remain underscore-prefixed. Literal push adapters and the handler allowlist remain test-visible.
- No disk/page work on the pump or discovery callbacks; no host/runtime/settings lock held while awaiting a future or joining an owner.
- Preserve both 840×625 and 839×621 CSS floors. DOM doubles, browser checks and Windows/WebView2/live-EVE acceptance are separate evidence.

## Evidence and highest-review-risk decisions

1. **Admission must cover completion, not entry.** Current `_preview_setting_change()` only reserves certain bridge methods (`ui/api.py:4590`). Primary Size/Reset use `_primary_intents`, while Copy uses `_pending_layouts` (`preview/host.py:1902–1967`). A lease released when a bridge method merely posts work is insufficient.
2. **Use the caller, not another worker.** pywebview provides a thread per bridge call. That thread may wait for pump futures and disk with no state lock held. `PreviewRuntime._run` remains a lifecycle owner, not an executor for layout transactions.
3. **Legacy Reset needs supporting work.** `_reset_layouts()` currently invokes its persistence callback on the pump (`preview/host.py:4237–4248`). Route that existing clear through `CropStore`'s already-retained command worker; do not submit another job to the one-worker executor occupied by `CropStore._run` (`preview/cropstore.py:385–432`).
4. **Capture actual windows; check actual movement.** `_saved` is not a complete live rectangle inventory. `PreviewWindow.move()` currently updates its cache before calling `SetWindowPos` and does not inspect failure (`preview/window.py:929–940`). Add narrow checked native seams for the new batch, rather than interpreting cached rectangles as proof.
5. **Keep discovery running.** Do not freeze `_apply_pending_roster()` wholesale: it also feeds crop reconciliation. Freeze conflicting user/configuration edits, continue external discovery/revocation, and fence delivery by captured full session identities. Disappeared/replaced sessions become deferred, not targets on newly reused HWNDs.
6. **Losslessness includes the page.** `settings.validated_preview()` caps `excluded` via `roster.deserialize()`, and `previews.js:rows()` does not union excluded-only owners. Fix both in the first independently testable task.
7. **Revision ordering is narrower than a UI rewrite.** Give saved-layout state and exclusion acknowledgements one ordered revision domain. Do not replace existing keybind, crop or marker ownership schemes with a generic form framework.

Rejected alternatives: named autosave changes the approved product; a second settings file/writer breaks atomic working geometry/visibility commits; a series of Copy endpoints permits torn application; queueing requests behind unknown busy work creates hidden actions; using `locked=True` as a gesture gate changes right-click crop behavior.

## File/ownership map

| File | Responsibility |
| --- | --- |
| New `wingman/preview/savedlayouts.py` | Pure immutable snapshot records, validation/serialization, record revisions, owner union and merge/capture functions. |
| New `wingman/preview/layoutadmission.py` | Shared/exclusive lease state and final closure; no native, disk or UI imports. |
| Existing `wingman/preview/store.py` | Acknowledged transaction, ordered with debounce/replace/clear and failure restoration. |
| Existing `wingman/preview/host.py`, `window.py`, `win32.py` | Completion-bound ordinary leases, gesture gate, checked capture/movement and native batch futures. |
| Existing `wingman/preview/cropstore.py` | Execute legacy primary Reset persistence on its existing worker queue; crop definitions/lifecycle stay unchanged. |
| New `wingman/preview/layoutcontroller.py` | Named operations, correlated committed state/receipts, bounded shutdown draining. |
| Existing `wingman/__main__.py`, `ui/api.py` | Construct/share resources, ports/facades, exclusion integration, shutdown/publication fences. |
| Existing `wingman/settings.py`, `preview/roster.py` | Empty schema default, lossless exclusions and every-write normalization. |
| Existing `wingman/web/previews.js`, `index.html`, `style.css`, `app.js`, `dev.js` | Saved-layout controls and one semantic state handler; preserve current module/capture ownership. |
| New focused tests listed per task | Model, transaction, admission/native, controller and executable page contracts. |

No new JavaScript module or Python subpackage is needed; `wingman.preview` is already explicitly packaged. Do not refactor unrelated bridge domains.

## Proposed shared contracts

Freeze these names across tasks unless a verified constraint requires a coordinated plan correction. These are new interfaces, not claims that they exist today.

### Model and wire state

```python
# preview/savedlayouts.py
@dataclass(frozen=True)
class SavedCharacter:
    name: str
    visible: bool
    rect: Rect | None

@dataclass(frozen=True)
class SavedLayout:
    id: str
    name: str
    characters: tuple[SavedCharacter, ...]
```

Functions: `validate_record(raw: object) -> SavedLayout` raises `ValueError`;
`deserialize(raw: object) -> tuple[SavedLayout, ...]` applies the forgiving
whole-record load policy; `serialize(records: tuple[SavedLayout, ...]) -> dict`
produces the spec's `{version: 1, items: [...]}` shape;
`record_revision(record: SavedLayout) -> str` hashes canonical sorted-key JSON;
`known_owners(section: dict, live_names: tuple[str, ...]) -> tuple[str, ...]`
returns exact validated names; `capture_characters(section: dict, retained: dict,
live_rectangles: dict) -> tuple[SavedCharacter, ...]` prefers actual live geometry;
`apply_snapshot(section: dict, snapshot: SavedLayout) -> None` merges into a
transaction's Preview section without changing globals.

Known owners are the union of live named clients, current geometry, recent
history, exclusions, explicit direct/group assignments, lock/minimize exceptions,
crops, markers and saved snapshot members. Validate names with `crops.valid_owner`;
do not casefold them. A snapshot with no valid members cannot be created. Record
IDs are generated with `uuid.uuid4().hex`; names are stripped, nonblank/printable,
and unique by casefold. Do not introduce an arbitrary count/name limit.

Wire `LayoutState` is a detached dictionary:
`{revision, layouts, owners, excluded, busy, availability, operation}`.
`availability` contains booleans `capture`, `edit` and `visibility`: an exclusive
capture/apply may begin, named metadata may be edited, and a shared exclusion
write may begin, respectively. These are advisory; every mutation rechecks.
`revision` is a process-local
monotonic integer. Each `layouts` summary contains `{id, name, revision,
character_count}`; its revision is the record hash, independent of unrelated
checkbox/busy changes. `owners` contains all validated known owners, including
saved-only owners and cached named discovery. `operation` is null
or the current/most-recent `{id, action, pending, applied, persisted, live, warning,
error}`; keep one operation, not an unbounded history. `live` is null for
snapshot-only mutations, otherwise `applied`, `deferred` or `incomplete`.

The retained `operation` describes named actions only; ordinary checkbox receipts
still carry their own operation IDs and do not build a second history. `busy`
reflects active admission as well as the named slot. Native gestures need no page
push; a read or attempted action rechecks real admission rather than trusting it.

Final receipts contain `{applied, persisted, error, operation_id, live, warning,
state}`. They are final results, not queue acknowledgements. Before completion,
the originating promise remains pending and `LayoutState.busy` explains it.
No success receipt is produced merely because a native command was posted.

### Admission and delivery

```python
# preview/layoutadmission.py
@dataclass(frozen=True)
class PrimaryLayoutLease:
    operation_id: int
    exclusive: bool
```

`PrimaryLayoutAdmission` methods:
`try_begin(*, exclusive: bool) -> PrimaryLayoutLease | None`,
`owns(lease: PrimaryLayoutLease) -> bool`,
`finish(lease: PrimaryLayoutLease) -> None`,
`close() -> None`, and `wait_idle(timeout: float | None = None) -> bool`.
Finishing is idempotent for that lease; IDs never reuse within the owner lifetime.
Shared leases permit ordinary operations; exclusive leases require no live
leases and block new shared/exclusive operations. Add `snapshot() -> AdmissionState`,
a frozen record `{closed: bool, shared_count: int, exclusive: bool}`, for pure
capability/status reads. Combine it with the named slot to derive availability;
Rename/Remove must not be disabled merely because an ordinary drag is active.
Close rejects new leases but never pretends outstanding leases completed.
No fairness queue or automatic retry.

`LayoutStore.transact(mutate_preview: Callable[[dict], None]) -> LayoutCommit`
raises on refusal/persistence failure. Define `LayoutCommit` in `savedlayouts.py`
as a frozen record of `revision: int`, detached immutable
`layouts: tuple[tuple[str, Entry], ...]`, `excluded: tuple[str, ...]` and
`saved: tuple[SavedLayout, ...]`. Its revision is a process-local successful
transaction sequence assigned under `_write_lock`, not persisted metadata.
The controller accepts data only from newer commit sequences before advancing
its separate view-state revision. This preserves concurrent ordinary exclusion
writes without letting a delayed older caller replace newer committed choices.

Define these fields alongside those records:

```python
@dataclass(frozen=True)
class PrimaryLayoutCapture:
    pump_epoch: int
    eve_epoch: int
    roster_generation: int
    sessions: tuple[ClientSessionId, ...]
    retained: tuple[tuple[str, Entry], ...]
    live_rectangles: tuple[tuple[str, Rect], ...]
    preview: dict

@dataclass(frozen=True)
class PrimaryLayoutLiveResult:
    live: str
    warning: str | None
```

Sessions include live excluded clients, not just existing primary windows. The
Preview dictionary is a detached committed copy owned only by this operation;
no mutable source object is shared with the pump/settings. Capture membership
and visibility come from this copy plus the captured sessions, not discovery
that arrives later while persistence is running.

Proposed host methods:
- `capture_primary_layout(lease) -> Future[PrimaryLayoutCapture]`
- `apply_primary_layout(lease, capture, commit, rectangles) -> Future[PrimaryLayoutLiveResult]`
- `refresh_primary_visibility(lease) -> Future[PrimaryLayoutLiveResult]`
- `release_primary_layout(lease) -> None`

`rectangles` is `Mapping[str, Rect | None]` containing **every recorded member**.
A null value leaves that member's geometry untouched while retaining its identity
for scoped visibility reconciliation and native failure accounting. Omitting null
members would make an unchanged visible/hidden choice indistinguishable from a
character outside the snapshot; do not infer membership from geometry or deltas.

`release_primary_layout` retires operation-local native state, finishes its
lease, then wakes the existing family/stop completion path. Wake after finishing,
not before: an early wake can observe the lease still active and strand shutdown.
Controller fallback finish is idempotent and covers host-unavailable operations.
No callback may still mutate after the lease is finished. Off/cancel must not
complete a future early while an executing pump callback remains authoritative;
only queued, unstarted work can be canceled immediately. A closed/offline host
settles without starting a pump. Completing futures occurs outside host locks.

## Execution preparation

- [ ] Reuse the linked worktree, or create an implementation worktree from the
  approved design/plan commits. Do not write source in the primary checkout.
- [ ] Check `git status`, `git log` and current upstream main; reconcile any source
  changes before execution. Do not amend merged commits or silently rebase a
  reviewed range.
- [ ] Create a dedicated environment and build this checkout's codec before the
  initial full baseline. Use case-sensitive `/tmp` for pytest data:

```sh
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-layouts-venv uv sync --locked --extra dev
node --version
cargo build --locked --release --manifest-path packaging/settings-codec/Cargo.toml --target-dir /tmp/wingman-preview-layouts-codec
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-layouts-venv uv run --no-sync python -c "import os,pathlib,shutil; from wingman.evesettings import codec; n='wingman-settings-codec'+('.exe' if os.name=='nt' else ''); t=pathlib.Path('packaging/bin')/n; t.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(pathlib.Path('/tmp/wingman-preview-layouts-codec/release')/n,t); assert codec.codec_available()"
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-layouts-venv uv run --no-sync python -m pytest tests/ -q -rs --basetemp=/tmp/wingman-preview-layouts-baseline
```

Subsequent Python commands use that same `UV_PROJECT_ENVIRONMENT` and
`uv run --no-sync`. Stop on an unexplained failing baseline. Record exact results
in `docs/preview-layouts-implementation-notes.md` when execution starts.

## Task 1: Lossless settings model and offline visibility

**Files:** create `preview/savedlayouts.py` under `wingman/`,
`tests/test_preview_savedlayouts.py`, `tests/test_settings_savedlayouts.py`;
modify `preview/roster.py`, `settings.py`, `web/previews.js` under `wingman/`;
extend `tests/test_preview_roster.py`, `tests/test_settings.py`,
`tests/test_preview_labelmarkers_page.py` and its existing Node fixture for the
excluded-only row regression.

**Consumes:** existing `Rect`, `layout.Entry`, `crops.valid_owner`, settings
transactions and the `TextPageTree`/Node harness conventions.
**Produces:** all pure model functions above and lossless current exclusions,
without exposing named-layout actions yet.

- [ ] Write failing model tests: independent empty defaults, schema/type validation,
  whole-record rejection on one malformed member, duplicate ID/name load order,
  exact/prototype-like owner names, null geometry, negative coordinates, bools and
  integer overflow. Enforce signed Win32-representable coordinates/extents and
  positive dimensions; reject unsafe right/bottom arithmetic before native use.
- [ ] Write the real transaction regression, not a test of a mocked normalizer:

```python
def test_explicit_exclusions_survive_reload_without_expanding_history(tmp_path):
    from wingman import settings
    path = tmp_path / "settings.json"
    doc = settings.load(path)
    names = [f"Pilot{i}" for i in range(65)]
    with settings.update(doc, path) as live:
        live["preview"].update(excluded=names, seen=names)
    with settings.update(doc, path) as live:
        live["channel_title"] = "Unrelated"
    saved = settings.load(path)["preview"]
    assert saved["excluded"] == names
    assert len(saved["seen"]) == 64
```

- [ ] Run `python -m pytest tests/test_preview_savedlayouts.py
  tests/test_settings_savedlayouts.py -q` through the prepared uv environment
  and confirm the missing model/capacity behavior fails. Add `cap: int | None = CAP` to
  `roster.deserialize`; its only new branch is `return out if cap is None else
  out[:cap]`. Pass `cap=None` only for `preview.excluded`. Preserve existing
  validation/deduplication and default behavior for every other caller.
- [ ] Implement the model/default/every-write normalization. `apply_snapshot`
  preserves existing legacy lock fields for geometry replacements, merges
  exclusions losslessly and touches no unrelated setting. Validate first, then
  mutate. Canonical record hashes must not depend on character map insertion order.
- [ ] In `previews.js:rows()`, union `state.excluded` through the existing
  null-prototype deduplication map. Prove an excluded-only 65th owner is editable
  even with no live/seen/bind/group/crop/marker entry; preserve the inverted Preview
  checkbox semantics. Do not wait until the final UI task to repair this route back.
- [ ] Run GREEN: new tests plus `test_preview_roster.py`, `test_settings_preview.py`,
  `test_settings.py`, `test_preview_labelmarkers_page.py`, `test_page_conventions.py`.
  Commit this independently useful compatibility/model change.

## Task 2: One completion-bound admission owner

**Files:** create `wingman/preview/layoutadmission.py` and
`tests/test_preview_layout_admission.py`; modify `preview/host.py`, `window.py`,
`win32.py`, `cropstore.py`, `__main__.py`, `ui/api.py` under `wingman/`; update
`tests/test_preview_polish_fixes.py`, `test_preview_runtime_review.py`,
`test_preview_runtime_boundaries.py`, `test_preview_window.py` and relevant fakes.

**Consumes:** existing primary intents, Copy mailbox, CropStore worker and runtime
fences. **Produces:** the shared admission contract and ordinary operations that
keep their leases until actual completion, with no named controls exposed.

- [ ] RED-test shared/exclusive conflicts, idempotent finish, final close and
  retained timed-out wait using Events. A minimal lease contract test is:

```python
def test_exclusive_waits_for_ordinary_completion():
    from wingman.preview.layoutadmission import PrimaryLayoutAdmission
    gate = PrimaryLayoutAdmission()
    ordinary = gate.try_begin(exclusive=False)
    assert ordinary is not None
    assert gate.try_begin(exclusive=True) is None
    gate.finish(ordinary)
    batch = gate.try_begin(exclusive=True)
    assert batch is not None
    assert gate.try_begin(exclusive=False) is None
    gate.close()
    assert not gate.wait_idle(timeout=0)
    gate.finish(batch)
    assert gate.wait_idle(timeout=0)
    assert gate.try_begin(exclusive=True) is None
```

- [ ] Run `python -m pytest tests/test_preview_layout_admission.py -q` RED before
  implementing the gate, then repeat GREEN with the native integration cases.
- [ ] Construct exactly one store/gate pair before the platform-specific host
  builder can return None. Inject it into `build_preview_host` and `Api`; keep
  it available for host-unavailable offline operations. Existing standalone host
  tests must explicitly inject the same pair when exercising new operations;
  never let a real host and its controller silently use separate gates/writers.
- [ ] Attach shared leases to ordinary work across **all** these boundaries:
  move/resize/resize-all gestures through release/cancel; default-size persistence;
  queued single/bulk Size and Reset through storage/native completion; Copy
  through persistence and `_pending_layouts` retirement; offline Size/Copy/Reset;
  exclusion writes through reconciliation/rebind; master-enable admission.
  Coalescing must retire every represented lease exactly once, not lose a lease
  when a queued payload is replaced. Every finish path wakes existing lifecycle
  reconciliation after lease retirement, including completion without an HWND.
  Retain current ordering between user intents.
- [ ] Add gesture-specific begin/end callbacks to `PreviewWindow`, independent of
  `is_authorized` and `locked`. Reject a conflicting drag start without changing
  click activation or right-click crop meaning. Release on button-up, capture
  loss, native close and stop freezing. Keep crop/companion gestures independent.
- [ ] Move Reset's clear out of the pump: add proposed
  `CropStore.submit_primary(action: Callable[[], T]) -> Future[T]`, backed by a
  typed item in its existing `_queue`. `_run` executes it outside the condition
  lock; callbacks only store/post completion. Submit admitted offline Reset work
  before the closing barrier, and handle worker-start/post failure without an
  orphaned pending count. Never submit a second task to the occupied executor.
- [ ] Keep Off/final revocation independent of waiting for layout-idle. Master On
  refuses while a conflicting lease exists; do not change the existing committed
  master-setting requirement. On an admitted Off edge, `_eve_valid()` fences at
  once while outstanding leases drain. `_begin_stop()` freezes gestures before
  waiting for their completion, and retained work blocks re-enable/replacement.
- [ ] Handle completion/retirement messages before `_host_proc` discards ordinary
  messages for stopping/old epochs. Failed posts must either refuse before
  admission or settle the admitted token without authorizing native work.
- [ ] Run GREEN against all existing preview-runtime and polish-fix suites plus
  window/cropstore tests. In particular retain the accepted-live-Reset→offline-Size,
  final-close-during-I/O and HWND-gap cases. Commit before adding exclusive batch use.

## Task 3: Acknowledged store transaction and checked native batch

**Files:** modify `wingman/preview/store.py`, `savedlayouts.py`, `host.py`,
`window.py`, `win32.py`; create `tests/test_preview_layout_batch.py`;
extend `tests/test_preview_store.py`, `test_preview_window.py`,
`test_settings_committed_preview.py` and native runtime fixtures.

**Consumes:** Tasks 1–2. **Produces:** `LayoutCommit`, capture/live-result types,
`LayoutStore.transact` and the proposed host future methods.

- [ ] RED-test the batch with the real settings document and injected saver:
  block an earlier debounce write, start a batch, prove it cannot overtake;
  queue an ordinary delta/name, fail batch persistence, and prove both are still
  retained without overwriting a newer recorded delta. No sleeps as race evidence.
  This is the minimal rollback/retention regression; add the blocked interleavings
  around it using the existing runtime fixtures:

```python
def test_failed_batch_keeps_the_prior_drag(tmp_path, monkeypatch):
    import pytest
    from tests.test_preview_store import FakeTimer
    from wingman import settings
    from wingman.preview.geometry import Rect
    from wingman.preview.layout import Entry
    from wingman.preview.store import LayoutStore
    path = tmp_path / "settings.json"
    doc = settings.load(path)
    store = LayoutStore(lambda: settings.update(doc, path), timer=FakeTimer)
    store.record("Pilot", Entry(Rect(9, 2, 320, 210)))
    def fail_save(*args, **kwargs):
        raise OSError("disk unavailable")
    with monkeypatch.context() as patch:
        patch.setattr(settings, "_save_locked", fail_save)
        with pytest.raises(OSError, match="disk unavailable"):
            store.transact(lambda preview: preview["excluded"].append("Pilot"))
    assert doc["preview"]["excluded"] == []
    store.flush()
    assert settings.load(path)["preview"]["layouts"]["Pilot"]["x"] == 9
```

- [ ] Run `python -m pytest tests/test_preview_layout_batch.py -q` RED against
  the missing transaction/checked-native seams before implementing them.
- [ ] Implement transaction ordering: `_write_lock` → short pending `_lock` →
  release pending lock → `settings.update()`. Merge detached ordinary deltas/names
  before calling `mutate_preview(section)`, so Apply supersedes only its members.
  On any transaction exception, restore drained deltas with newer-pending-wins
  precedence and restore names in chronological order; re-arm retained work.
  Snapshot-only operations may flush prior deltas but never replace working
  geometry with their capture. Before exiting `settings.update()`, explicitly
  canonicalize the changed Preview section with pure `validated_preview`, assign
  it back to the transaction document, and prepare the detached `LayoutCommit`.
  Normalization at context exit must be a fixed point; test it. Preparing before
  exit makes allocation/validation failure roll back before disk commits. Prepare
  the next transaction sequence with that value and advance the store counter
  only on success, still under `_write_lock`. Return the prepared value only after
  durable save and committed publication succeed.
- [ ] Add checked `PreviewWindow.native_rect() -> Rect | None` and
  `move_checked(rect: Rect) -> bool` seams using owned HWNDs only. Check native
  success before adopting applied geometry; keep labels, thumbnails and alert
  caches coherent after a successful resize. Share mechanics with `move()` only
  where its existing callers' behavior is preserved; do not rewrite input/rendering.
- [ ] Capture on the pump after lease/phase/gesture revalidation. Read actual
  rectangles, including untouched default placements, and include retained offline
  geometry and live excluded sessions. Failure to read an existing primary is a
  capture refusal, not a made-up coordinate or omitted member. Offline capture
  uses retained/committed data without a pump. Preserve the committed Preview
  snapshot as detached operation data, not a reference to a mutable settings section.
- [ ] Apply one batch from the committed data. Install preferred geometry in
  retained authority; validate full source identities and current epochs before
  each native effect. Reconcile recorded primary inclusion choices and rebind
  without re-sourcing hotkey tables. For currently known live sessions whose
  primaries are re-enabled by this Apply, use the explicit rectangle in this batch
  even if reopen positions is Off; genuinely later arrivals follow that preference.
  Verify desired inclusion against actual primary ownership after reconciliation:
  a still-current client whose requested preview failed creation is incomplete,
  not an expected offline member. Cover failed hide/removal as well as failed moves.
- [ ] Keep discovery/crop reconciliation active. Revocation can retire a source
  during the operation; skip/defer that session, never substitute a same-name
  replacement. Clamp live geometry for monitors without persisting rescue. Native
  failure produces `incomplete`; Off/source disappearance produces `deferred`.
  A mix reports the strongest real failure with context, not a blanket success.
- [ ] Explicitly test same persisted target with different live geometry: Apply
  must still move the current preview. Test 64 absent exclusions plus one hidden
  member in both merge orders, null geometry, all-hidden snapshots, offline mode,
  current locks, active alert labels, failed GetWindowRect/SetWindowPos, monitor
  rescue, replacement sessions, failed completion posts and shutdown after commit.
- [ ] Run new batch tests plus store/host/window/runtime/committed-reader suites
  GREEN. Commit the native/persistence primitive before exposing bridge commands.

## Task 4: Controller, bridge and lifetime wiring

**Files:** create `wingman/preview/layoutcontroller.py`,
`tests/test_preview_layoutcontroller.py`, `tests/test_preview_savedlayouts_page.py`
and `tests/fixtures/preview_savedlayouts.cjs`; modify `wingman/ui/api.py`,
`wingman/__main__.py`, `wingman/web/app.js`, `wingman/web/previews.js`;
extend `tests/test_preview_wiring.py`, `test_bridge_contract.py`, `test_api.py`.

**Consumes:** immutable model, shared gate/store, host futures and committed reader.
**Produces:** one controller plus five new one-line bridge facades:

| Bridge facade | Controller method |
| --- | --- |
| `create_preview_layout(name)` | `save_current(name)` |
| `apply_preview_layout(layout_id, revision)` | `apply(layout_id, revision)` |
| `update_preview_layout(layout_id, revision)` | `update_saved(layout_id, revision)` |
| `rename_preview_layout(layout_id, revision, name)` | `rename(layout_id, revision, name)` |
| `remove_preview_layout(layout_id, revision)` | `remove(layout_id, revision)` |

Constructor: `PreviewLayoutsController(initial: dict, *, store: LayoutStore,
admission: PrimaryLayoutAdmission, ports: PreviewLayoutsPorts, id_factory:
Callable[[], str])`. Production passes `lambda: uuid.uuid4().hex`; tests pass a
deterministic factory. `initial` is a committed Preview snapshot.

Define `PreviewLayoutsPorts` as a frozen dataclass with these named effects:

```python
read_preview: Callable[[], dict]
live_names: Callable[[], tuple[str, ...]]
capture: Callable[[PrimaryLayoutLease], Future[PrimaryLayoutCapture]]
apply: Callable[[PrimaryLayoutLease, PrimaryLayoutCapture, LayoutCommit,
                 Mapping[str, Rect | None]], Future[PrimaryLayoutLiveResult]]
refresh_visibility: Callable[[PrimaryLayoutLease], Future[PrimaryLayoutLiveResult]]
release: Callable[[PrimaryLayoutLease], None]
publish_state: Callable[[dict], None]
```

`live_names` reads the host's existing cached `characters()` result without native
work; return an empty tuple without a host. State reads sample these pure ports
outside locks and union their owner evidence with accepted saved/excluded state,
never replacing authoritative exclusion data with a stale sampled dictionary.
Host-unavailable adapters return already-settled offline capture/deferred futures,
not a missing owner or an invented native result. Also implement
`set_excluded(name, excluded)` behind the existing `set_preview_excluded`
signature, preserving its boolean conversion and existing exclusion-name
acceptance (not the stricter new snapshot-owner rule), and `state() -> dict`,
`close_admission() -> None`, `shutdown(timeout: float = 5.0) -> bool`.
No controller import from `ui`.

- [ ] RED-test CRUD/stale-record/no-op cases with real model/settings/store, then
  Event-controlled capture/persist/native blocks. Refused or duplicate names and
  stale revisions cause no write, no native effects and no misleading success.
  Save/Update capture fresh state; Rename/Remove do not move windows. This case
  exercises real persistence while making any unexpected native port call fail:

```python
def test_rename_refuses_stale_revision_without_native_effects(tmp_path):
    from wingman import settings
    from wingman.preview import savedlayouts as model
    from wingman.preview.layoutadmission import PrimaryLayoutAdmission
    from wingman.preview.layoutcontroller import PreviewLayoutsController, PreviewLayoutsPorts
    from wingman.preview.store import LayoutStore
    path = tmp_path / "settings.json"
    doc = settings.load(path)
    record = model.SavedLayout("1" * 32, "Original", (model.SavedCharacter("Pilot", True, None),))
    with settings.update(doc, path) as live:
        live["preview"]["saved_layouts"] = model.serialize((record,))
    reader = settings.committed_preview(doc)
    def unexpected_native(*args):
        raise AssertionError("Rename must not capture or move windows")
    ports = PreviewLayoutsPorts(
        read_preview=reader.snapshot, live_names=lambda: (), capture=unexpected_native,
        apply=unexpected_native, refresh_visibility=unexpected_native,
        release=lambda lease: None, publish_state=lambda state: None,
    )
    controller = PreviewLayoutsController(
        reader.snapshot(), store=LayoutStore(lambda: settings.update(doc, path)),
        admission=PrimaryLayoutAdmission(), ports=ports, id_factory=lambda: "2" * 32,
    )
    before = path.read_bytes()
    refused = controller.rename(record.id, "stale", "Renamed")
    assert not refused["applied"] and not refused["persisted"]
    assert path.read_bytes() == before
    receipt = controller.rename(record.id, model.record_revision(record), "Renamed")
    assert receipt["applied"] and receipt["persisted"]
    saved = settings.load(path)["preview"]["saved_layouts"]
    assert model.deserialize(saved)[0].name == "Renamed"
```

- [ ] Run `python -m pytest tests/test_preview_layoutcontroller.py -q` RED before
  implementing these methods; add blocked-stage and shutdown cases in the same suite.
- [ ] Reserve one named-operation slot under a short state lock, then release it.
  Save/Update/Apply take exclusive leases; Rename/Remove take shared leases.
  Direct exclusions take their own shared leases without occupying the named
  slot, preserving ordinary concurrent writes. Named mutations revalidate ID/hash
  inside the settings transaction. Do not serialize unrelated settings through
  this lock. A named request cannot queue behind another named request.
- [ ] Orchestrate on the existing bridge-call thread in this order:

```text
validate request -> reserve controller operation -> acquire lease
capture if required (wait without locks) -> acknowledged store transaction
publish committed cache revision -> native apply/visibility future if required
retire host state / finish lease / wake lifecycle -> idempotent fallback finish
settle final state/receipt
```

  Pending state is read-only observable. No timeout may clear an in-flight slot
  while its caller/native/storage work can still finish. The bridge caller waits
  for settlement; bounded shutdown waits may report incomplete draining and keep
  the owner tracked. Pre-write revocation may refuse; once a transaction is
  admitted it finishes, and post-commit revocation yields saved/deferred.
- [ ] Rebuild controller cached state only from committed data and operation
  transitions; reads take short locks only. Accept `LayoutCommit` data by its
  store sequence, ignoring delayed older commits; return the latest accepted
  state in such callers' receipts. Test two ordinary exclusions with reversed
  post-commit callbacks and prove both choices survive. Never hold the state lock
  over a port, future wait or page publication. Publish after releasing it.
  Snapshot-only CRUD must not mirror a stale working-geometry map into the host.
  Separate precommit exception handling from postcommit/native handling so a
  cache/publication/native error after a successful save never becomes a false
  `persisted: false` result. Individual exclusions use the same revision domain
  as bulk Apply and retain the existing primary-only sweep/rebind behavior;
  no runtime effect after a
  refused save. Leave Lock/Never-minimize orchestration outside this controller.
- [ ] Add literal `_push("onPreviewLayouts", payload, delivery_allowed=...)`
  behind a private Api port adapter and allowlist/register its single owner
  together. Include `layout_state` in `get_preview_hotkey_state()` so initial
  hydration/re-entry needs no extra request. Add an initial handler in previews.js
  that accepts state even before the new controls exist; keep this commit's
  all-page smoke green. Mirror top-level `excluded` from that committed state.
- [ ] In this same commit, make hydration/handler acceptance revision-guarded and
  change only `makeExcludedCheck` to consume authoritative receipt state with
  per-attempt ownership. Older hotkey payloads or replies must not restore older
  exclusions. Do not increment the existing hotkey `pushes` counter for the new
  handler; that could discard an unrelated successful keybind write. Start the
  production-page harness with reversed checkbox replies, a later bulk state push
  and a pending keybind write; do not defer this compatibility fix to Task 5.
- [ ] Close controller publication/admission nonblockingly in `_close_eve_runtime`
  and main's pre-destruction fence. Drain controller operations outside locks
  before `PreviewRuntime.shutdown`; timeout retains both references, never a
  second controller/host. Cover host-unavailable startup, repeated close and late
  replies after page destruction. Main must inject the exact shared store/gate.
- [ ] Run controller tests plus bridge/API/wiring, lifecycle and committed-reader
  tests GREEN; verify lexical one-line facades and private Api attributes. Commit.

## Task 5: Explicit Saved layouts controls and page ownership

**Files:** modify `wingman/web/index.html`, `previews.js`, `style.css`, `dev.js`;
extend `tests/test_preview_savedlayouts_page.py` and
`tests/fixtures/preview_savedlayouts.cjs`; modify
`tests/fixtures/screenshot_dom.cjs` for opt-in static text; extend `tests/test_settings_runtime.py`,
`test_page_conventions.py`, `test_dev_harness.py`, screenshot fixtures/shooter tests
where their actual Preview captures include the new block.

**Consumes:** Task 4's `layout_state`, handler, facades and final receipts.
**Produces:** the spec's complete user flow in the existing Placement disclosure.

- [ ] Extend Task 4's real-page Node harness using `TextPageTree` and existing
  `screenshot_dom.cjs` mechanics, loading production app/previews/panel scripts.
  Its existing `createDOM` builder ignores static text, so add only opt-in
  `node.text` consumption before appending child elements. Pin this with a real
  static-control-text regression and unchanged structure-only input behavior:

```javascript
function build(node) {
  const el = new Element(node.tag, node.attrs);
  if (Object.prototype.hasOwnProperty.call(node, 'text')) el.textContent = node.text;
  node.children.forEach(child => el.appendChild(build(child)));
  return el;
}
```

  Feed complete state and controllable promises; assert calls and retained DOM,
  not fabricated copies of the new implementation. Include this deferred-order case:

```text
hydrate revision 1 -> open Apply confirmation for record hash A
accept -> keep Apply pending -> deliver revision 3 with new exclusions
resolve an older checkbox reply/revision 2 -> assert revision 3 choices remain
navigate away -> settle Apply -> assert no dialog reopen or focus theft
```

- [ ] RED-test empty/unavailable state, every action, canceled confirmations,
  stale hash, duplicate name, save refusal, offline/deferred/incomplete outcomes,
  repeated clicks and unknown/prototype-like names. No command before hydration;
  no bridge request when only choosing a name or switching subpages.
- [ ] Add labelled selector and wrapping action rows for Apply…, Save current as…,
  Update saved…, Rename…, Remove…. Use IDs `preview-layouts`,
  `preview-layout-select`, `preview-layout-apply`, `preview-layout-save`,
  `preview-layout-update`, `preview-layout-rename`, `preview-layout-remove` and
  `preview-layout-status`; keep the status live region mounted. Derive counts
  from supplied records. Save/Update/Apply use `availability.capture`;
  Rename/Remove use `availability.edit`; Preview checkboxes use
  `availability.visibility` plus their own pending ownership. Save also needs a
  known owner; selection alone stays usable while a mutation is pending. Prompts
  own free text; Remove confirms with existing danger styling; Apply warns about
  replacing the affected working arrangement and leaving other characters alone.
  Show the reopen-Off consequence from acknowledged settings, not a guessed value.
- [ ] Keep saved-layout state separate from the hotkey table. Extend Task 4's
  shared revision guard to the new controls; do not introduce another baseline
  for exclusions. Cover a late checkbox reply after Apply, a stale getter after
  a named mutation, and newer ordinary edits after an earlier Apply completes.
- [ ] Union saved-layout owners as well as uncapped exclusions into `rows()`.
  Use the existing null-prototype deduplication and owned-focus render scheduling.
  Preserve selection/drafts across pushes, and clear a removed selected ID
  without pretending another layout was applied. Every dialog starts with
  `endCapture()`; late callbacks must not rearm it or cancel a later capture.
- [ ] Keep `WM.previewCropScreenshot` isolated: all new layout mutations and
  delayed dialog continuations refuse while staging; fixture entry/exit cannot
  contaminate live acknowledged state. Only `dev.js` and the existing fixture
  transport supply fabricated data. Exercise delayed real replies across staging.
- [ ] Run the new page suite RED/GREEN, existing Preview page suites, settings
  runtime/tab tests, bridge conventions, dev/shooter guards and JS smoke. Open
  in an isolated browser at both floors; check wrapping, keyboard dialogs, busy
  state, readable errors, scroll/focus and no extra hydration. Record browser
  evidence separately; do not claim Windows acceptance. Commit the complete UI.

## Task 6: Acceptance, documentation and integration gate

**Files:** update `docs/smoke-checklist.md`, `docs/preview-layouts-implementation-notes.md`,
`AGENTS.md`, `DESIGN.md`, and the relevant existing README Preview description.
Keep changes limited to shipped behavior/ownership and accurate evidence; do not
rewrite historical design records. Update the active spec/plan status only when
its acceptance really changes.

- [ ] Map every spec section to completed tests. In particular inspect exclusion
  retention, missing members/null geometry, failed save rollback, native failures,
  untouched windows, shared-lease completion, Reset worker ownership, new/reused
  sessions, restored locks and startup/final-shutdown paths.
- [ ] Obtain independent changed-code review and run `/polish --fix`; inspect
  any safe edits and independently resolve substantive findings. Run actual
  CodeRabbit if requested for this change; never relabel a local agent as CodeRabbit.
- [ ] Run fresh gates from the implementation worktree after review corrections:

```sh
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-layouts-venv uv run --no-sync python -m pytest tests/ -q -rs --basetemp=/tmp/wingman-preview-layouts-final --junitxml=/tmp/wingman-preview-layouts-final.xml
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-layouts-venv uv run --no-sync ruff check .
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-layouts-venv uv run --no-sync ruff format --check .
node scripts/js_smoke.js
cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml --target-dir /tmp/wingman-preview-layouts-codec
git diff --check
```

- [ ] Record all failures/skips and prerequisites. Add Windows smoke steps for
  multiple clients, offline/re-enabled primaries, both reopen modes, live source
  replacement, locks, labels/alerts, independent crops/companions, monitor rescue,
  Off/on/restart/Quit and unchanged real EVE bounds. Only perform live app/profile
  actions with authorization; retain unrun acceptance explicitly.
- [ ] Inspect the final range against the approved scope; explain the controller,
  admission and batch boundaries using `change-explainer`. Get integration
  authorization, then push to `fork` and target `elboaf/FlyGD-Wingman:main` with
  `-R`. Preserve the worktree for feedback; do not close #213 before its agreed
  integration/acceptance decision.

## Coverage and adaptation checkpoints

| Spec requirement | Delivery |
| --- | --- |
| Explicit snapshots, CRUD, stale record identity | Tasks 1, 4, 5 |
| Absent/null/offline members and lossless exclusions | Tasks 1, 3, 5 |
| No new persistence/runtime owner; current-arrangement continuity | Tasks 1–4 |
| Pending writes, gestures, Reset, Copy and ordinary exclusion ordering | Tasks 2–4 |
| Immediate Apply versus later reopen, source/session fences, monitor rescue | Task 3 |
| Truthful persistence/native outcomes and bounded retained shutdown | Tasks 3–4 |
| Hydration, dialogs, revisions, focus/capture, screenshot isolation | Tasks 4–5 |
| Browser and Windows acceptance, packaging and regression gates | Task 6 |

Stop and revisit the plan if the existing worker cannot admit/settle primary
Reset commands through shutdown, any gate path requires waiting on a pump while
holding a writer lock, or native correctness would require touching real EVE
geometry. These are architecture failures, not reasons to add a new worker,
weaken tests, drop a lease early or silently narrow supported offline behavior.
Correct interface names consistently in this plan and all dependent tasks if
execution exposes a verified mismatch. Do not widen the user-approved feature.

Explicit exclusions: no #216 importer, external fixtures, saved crop/companion
configuration, layout keybinds, named autosave, automatic backup history, active
layout persistence, broad bridge/UI refactoring or unrelated policy-cap changes.
