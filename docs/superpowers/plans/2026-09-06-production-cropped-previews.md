# Production Cropped Previews Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Draft for review; no implementation performed.

**Goal:** Ship one persistent, independently positioned crop per character without weakening normal previews, settings transactions or client-window safety.

**Architecture:** Separate crop and picker controllers run on the existing preview pump. A crop-specific coordinator consumes full shared-discovery sessions and committed definitions; a retained crop store serializes settings writes on one lazy worker and returns tagged completions through the pump mailbox. The page sends semantic requests and observes authoritative state, never native handles.

**Tech Stack:** Python 3.11+, ctypes/Win32/DWM, Pillow, existing transactional JSON settings, plain ES5/HTML/CSS in pinned pywebview/WebView2, pytest and Ruff. No new dependency or subpackage.

**Spec:** [Production crop spec](../specs/2026-09-06-production-cropped-previews-design.md), including its accepted independent-review findings and transaction-admission clarification. Read its linked parent design and prototype results for inherited requirements and measured thresholds.

## Global Constraints

- Zero or one saved crop per named character, with independent enablement.
- The provisional active-crop cap is **eight**, subject to the existing release gates.
- The picker and candidate share one temporary slot and must never overlap.
- `preview.enabled` remains the runtime master; individual definitions survive master-off.
- Primary-preview exclusion does not disable that character's crop.
- No real EVE client move, resize, reposition, maximize, input injection or gameplay automation.
- All crop/picker HWND and DWM work stays on the existing preview pump.
- Cancellation before transaction admission writes nothing. An admitted save may finish after client loss or master-off; a stale native candidate must not become visible.
- Settings writes and waiting for settings workers must not block the preview pump.
- Runtime discovery-session identity is not persisted.
- No crop labels, alerts, independent hotkeys, multiple crops, profiles, import/export, frozen frames, custom opacity or click-through mode.
- Existing `PRODUCT.md`/`DESIGN.md` conventions apply, including Settings placement, wrapped checkboxes, no browser-native dialogs, no pre-hydration commits, and the 840x625 CSS viewport floor (also exercise the documented 839px rounding case).
- Work in a linked worktree. Use failing regression tests before each behavior change; use normal commit hooks. Do not release an intermediate production slice.

## Evidence and review-risk decisions

Baseline is `57ce91d`; the reviewed spec is on `design/production-crop-spec` after `8a55384`. Recheck these seams if implementation rebases:

| Existing evidence | Consequence for this plan |
| --- | --- |
| `wingman/preview/host.py:571–603,835–892,936–975,1009–1070` | `_sweep()` is not a runtime hook. Use `ClientDiscovery` subscription and the existing snapshot mailbox. |
| `wingman/telemetry/model.py:10–34`, `tests/test_client_discovery.py:125–138`, `wingman/preview/host.py:91–103` | Preserve `RosterClient.session` before conversion to primary `Client`; same HWND/PID can represent a renewed session. |
| `wingman/settings.py:915–964` | `update()` owns a nonreentrant lock, temporarily mutates the live document, normalizes nested sections and rolls back exceptions. An unlocked read is not proof of a successful crop commit. |
| `wingman/atomicio.py:16–48` | File writing/fsync/replacement has no cancellation seam. Transaction admission and successful publication are distinct. |
| `wingman/preview/store.py:29–205` | Reuse per-key merge and write-ordering patterns, not the primary layout pending dictionary. |
| `wingman/__main__.py:356–547`, `wingman/ui/api.py:4542–4640` | Construct a retained store with the host; master-off and application shutdown are different lifetimes. |
| `wingman/preview/host.py:499–532,2506–2577` | Timed-out pumps retain ownership. Existing teardown synchronously flushes primary layouts; crop shutdown must not add another blocking flush. |
| `wingman/web/previews.js:290–318,726–744,1457–1467` | Add crop owners to rows and controls inside Configure. Existing lock eligibility incorrectly assumes exclusion means no relevant window. |
| `tests/manual/preview_crop_windows.py:406–856` | A picker owns a DWM destination plus a non-DWM overlay HWND. Count both HWNDs, but only one temporary thumbnail relationship. |
| `wingman/settings.py:425–585` | Add defaults AND validation together or another settings write silently drops crops. |

### Decisions to implement, not rediscover

1. **Resource units:** `MAX_LIVE_CROPS = 8` bounds committed crop relationships. One picker or candidate may temporarily add one relationship. Picker overlay/child-control HWNDs are separately counted and leak-tested, not a license for another DWM relationship. Close the picker's entire native resource bundle before candidate creation.
2. **Persisted model:** keep the parent design's version-1 object under `preview.crops[name]`, using normalized `x/y/w/h`, diagnostic original dimensions/pixels, and physical destination geometry. No separate file, settings version bump or future multi-crop implementation.
3. **Selection geometry:** retain a 16x16-source-pixel minimum from the probe. Use floor for left/top and ceil for right/bottom, clamped to current client bounds. Picker resize clears selection with an explanation and redraws the full mirror; source-client resize likewise clears selection and refreshes dimensions, requiring a fresh drag rather than guessing the user's intent.
4. **Picker UI:** a resizable Wingman tool window with a mirror, selection overlay, status text and native Reset/Use region/Cancel controls. Default mirror maximum remains 1200x800, fitted inside the selected monitor with room for chrome. Use keyboard-accessible native controls; actual focus, dark rendering and DPI behavior are release gates.
5. **Crop close:** retain click/left-drag activation/movement and right-drag aspect resize. A stationary right-click opens a native menu containing `Disable crop`; `WM_CLOSE` requests the same operation. Neither path directly destroys an enabled committed crop before its disable saves. Settings provides the equivalent keyboard-accessible control.
6. **Concurrency:** one FIFO settings writer; admission checks occur under the settings transaction lock plus a short metadata lock. The metadata lock is never held during file I/O. Definition changes, geometry deltas and shutdown barriers share this writer.
7. **Truth:** only the store's successfully committed snapshot drives crop reconciliation and crop UI. Publish a successful persisted outcome even if its native token has become stale. Runtime authorization is checked separately.
8. **Bridge:** new mutation endpoints return the existing `applied/persisted/error` fields plus `pending` and `operation_id`. Pending means neither applied nor refused yet. A dedicated semantic `onPreviewCrops` state event carries terminal outcomes; a getter recovers state when pushes were missed. Existing endpoints keep their return shapes.
9. **Master failure:** preserve `set_preview_enabled`'s boolean interface, but return `False` and do not start/stop or reconcile a new mode after its transactional save fails. Its current log-and-continue behavior would contradict committed crop authorization. This is a targeted integration correction, not a general Settings rewrite.

Rejected alternatives: a second pump/discovery service; a broad `PreviewWindow.is_crop` mode; synchronous pump writes; reading tentative settings as authoritative; destroying the old crop before replacement; compensating writes to fake cancellation after admission; widening the global settings/atomic-file API.

## File structure and interfaces

All paths below are relative to the repository root. New files are proposed deliverables, not missing existing files.

| File | Responsibility |
| --- | --- |
| Create `wingman/preview/crops.py` | Immutable source/definition/token/result records; validation, conversion and cap ordering. No native calls or threads. |
| Create `wingman/preview/cropstore.py` | Committed snapshots, mutation admission, one lazy worker, geometry sequences, cancellation/tombstones and drain barriers. No HWND operations. |
| Create `wingman/preview/cropwindow.py` | One crop HWND/thumbnail, gestures, transactional close requests, bounded update recovery and idempotent cleanup. |
| Create `wingman/preview/croppicker.py` | Temporary native selection UI, current mapping, focus/capture/DPI and callback-once cleanup. |
| Create `wingman/preview/cropcontroller.py` | Pump-owned resource registry, current sessions, user-operation ordering, reservations, selection/candidate/swap and runtime status. |
| Modify `wingman/preview/host.py`, `wingman/preview/win32.py` | Thin coordinator wiring, message identifiers, native bindings and two-phase shutdown. Preserve primary identity and rendering. |
| Modify `wingman/settings.py`, `wingman/preview/store.py`, `wingman/__main__.py`, `wingman/ui/api.py` | Persisted schema, protected owners, construction, semantic bridge and runtime lifecycle. |
| Modify `wingman/web/previews.js`, `wingman/web/app.js`, `wingman/web/style.css`, `wingman/web/dev.js` | Configure-detail controls, state event, lock eligibility and realistic dev states. No new route or JS bundle. |

### Shared records (Task 2 defines these)

```python
from dataclasses import dataclass
from wingman.preview.geometry import Rect
from wingman.telemetry.model import ClientSessionId

@dataclass(frozen=True)
class CropSource:
    x: float
    y: float
    w: float
    h: float
    original_client_w: int
    original_client_h: int
    original_px: Rect

@dataclass(frozen=True)
class CropDefinition:
    source: CropSource
    window: Rect
    enabled: bool = True
    version: int = 1

@dataclass(frozen=True)
class CropToken:
    operation_id: int
    name: str
    epoch: int
    generation: int
    session: ClientSessionId | None

@dataclass(frozen=True)
class CropWriteResult:
    token: CropToken
    applied: bool
    persisted: bool
    error: str | None
    revision: int
```

`epoch` identifies a preview runtime lifetime; definition `generation` distinguishes edits, not scans. `begin()` reserves a prospective edit generation, separately from the committed definition generation used by geometry. It does not change committed state or invalidate an admitted write. `session=None` is for configuration-only operations such as disabling/removing an offline crop. No record containing HWND/PID/session is serialized to the page or settings.

| New interface | Contract and producer task |
| --- | --- |
| `source_from_pixels(rect: Rect, size: tuple[int, int]) -> CropSource` | Task 2; rejects invalid/currently too-small selection with `ValueError`. |
| `source_to_pixels(source: CropSource, size: tuple[int, int]) -> Rect \| None` | Task 2; current-size clamp/minimum; no semantic region guessing. |
| `map_selection(selection: Rect, destination: Rect, size: tuple[int, int]) -> Rect \| None` | Task 2; destination is picker-client coordinates including mirror inset. |
| `deserialize(raw: object) -> dict[str, CropDefinition]`; `serialize(definitions: dict[str, CropDefinition]) -> dict` | Task 2; forgiving invalid-entry handling and canonical schema. |
| `eligible_names(definitions, sessions, limit=MAX_LIVE_CROPS) -> tuple[str, ...]` | Task 2; enabled and available, sorted by `(name.casefold(), name)`, capped. |
| `CropStore(update_settings, initial, *, executor_factory, debounce_s=1.0, flush_primary=None)` | Task 3; injected context manager and initial validated definitions; factory lazily supplies one worker. Optional primary-flush callback runs outside crop transactions during drain. |
| `store.open_epoch(epoch) -> None`; `store.observe_roster(epoch, snapshot) -> None` | Task 3; thread-safe runtime authorization metadata. Accept only newer roster generations for the current epoch; retain full session identities without native work. |
| `store.begin(name, *, epoch, session) -> CropToken` | Task 3; allocate operation/edit identity under metadata lock; no write. The host returns its operation ID in the receipt. |
| `store.put(token, definition)`, `store.set_enabled(token, enabled)`, `store.remove(token) -> Future[CropWriteResult]` | Task 3; queued writes. Toggle/remove patch the latest committed definition at execution, not a stale caller copy. |
| `store.cancel(token) -> bool`; `store.fence_epoch(epoch) -> None` | Task 3; cancel only unadmitted work; fencing does not erase admitted outcomes or configuration-only requests. |
| `store.record_geometry(name, generation, sequence, rect) -> None` | Task 3; memory-only; flush can modify only an existing, enabled definition at that generation. |
| `store.snapshot() -> dict`; `store.drain() -> Future[bool]`; `store.close() -> Future[bool]` | Task 3; copied committed definitions/revision/operation outcomes; drain flushes current deltas, close also fences new requests. |
| `CropWindow.create(libs, client, source_rect, rect, *, hidden, locked, on_activate, on_rect_changed, on_disable, on_failure)` | Task 4; `client` is a full `RosterClient`. Returns controller or `None`; hidden candidates remain hidden from their first update. |
| `window.move(rect)`, `set_hidden(bool)`, `set_locked(bool)`, `set_source_rect(rect)`, `close()` | Task 4; pump-only, idempotent where appropriate; geometry callback sends current destination. |
| `CropPicker.create(libs, client, monitor, *, on_confirm, on_cancel)`; `picker.cancel(reason)` | Task 5; confirm callback receives `(client, pixel_rect, client_size)` only after all picker resources close. |
| `CropController(libs, store, *, create_crop, create_picker, read_client_size, monitors, activate, is_locked, publish)` | Task 6; injected native seams, pump-only, no independent worker. |
| `controller.reconcile(snapshot)`, `request(action, name, value, token)`, `complete(result)` | Task 6; full roster session retained; token is the host-issued `CropToken`; action is `select`, `enabled` or `remove`; completions handled in write order. |
| `controller.set_hidden(bool)`, `restyle()`, `begin_stop(epoch) -> Future[bool]`, `close_native()` | Tasks 6–7; fence/freeze then drain; native close after drain completion. |
| `PreviewHost.request_crop(action, name, value=None) -> dict`; `crop_state() -> dict`; `is_stopping: bool` | Task 7; safe cross-thread submission/state, including configuration-only operations while pump is stopped and explicit draining-state reporting. |
| `Api.select_preview_crop(name)`, `set_preview_crop_enabled(name, enabled)`, `remove_preview_crop(name)`, `get_preview_crop_state()` | Task 8; validate external arguments; never touch HWNDs or start the host to satisfy a crop request. |

`snapshot()` contains `revision`, `definitions` (serialized), and `operations` (pending plus bounded recent terminal outcomes, each keyed by operation ID). Use `RECENT_RESULT_LIMIT = 32` for terminal outcomes only; never evict pending work. The UI reads current authoritative definitions even if an old operation aged out. Runtime `crop_state()` additionally contains `statuses` by character, `live_count`, `cap`, `runtime_enabled`, and `busy`; no native identity leaks through either representation.

## Operation ordering and failure contract

This table is the implementation contract for Tasks 3, 6 and 7:

| Stage | Owner/action | Cancellation or failure |
| --- | --- | --- |
| Requested | Coordinator validates name/master/source and reserves native capacity where required. | Refuse with a final field result if impossible; do not create an operation that cannot be serviced. |
| Selecting/prepared | Pump owns picker or hidden candidate. Old crop remains authoritative. | Cancel picker/candidate and unadmitted write; release reservation. |
| Queued | Worker waits for its turn/settings lock. | Fence/cancel marks the token invalid; inside `settings.update()` raise an internal cancellation exception before mutation so normal context exit cannot accidentally save. |
| Admitted | With settings lock held, check token under the short metadata lock, mark admitted, release metadata lock, mutate/save. | Native authorization may be revoked, but this write is no longer canceled. No callback or pump wait while holding either lock. |
| Published/failed | Worker exits transaction, updates committed snapshot only on success, records outcome, then enqueues completion. | Failure preserves previous committed definition. A successful stale operation remains a real persisted outcome. |
| Applied to runtime | Pump matches runtime epoch, discovery session and current committed definition revision. | Swap candidate only if still authorized; otherwise close it and reconcile latest committed state. |
| Later disable/remove | Ordered after an admitted earlier write; patches its resulting definition. | Success wins. Failure preserves the earlier successfully committed definition, not a pre-operation snapshot. |

Keep per-character request order through native completion: hold later requests in the coordinator while that character's admitted write completes, then prepare/submit the next request. The worker never blocks waiting for this; it finishes and is free to process other characters. Cancel/supersede a picker before admission when a disable/remove for that character arrives. While the pump is stopped, use the same store FIFO for configuration-only mutations and publish their outcomes without creating a native controller.

Geometry has a separate monotonically increasing sequence. At replacement admission, use the latest resolved destination. Movement during the save remains a newer dirty delta; apply it at swap and persist it as a subsequent geometry-only update against the replacement generation. Do not discard old-generation pending geometry until replacement succeeds; failed replacement leaves it eligible. Disable/removal success installs the new generation/tombstone before any following geometry write can run; failure preserves the prior generation and valid pending geometry.

Runtime shutdown is two-phase: fence epoch and freeze geometry on the pump, enqueue crop drain plus the existing primary-layout flush on the settings worker, then post a shutdown-ready completion. Only then destroy native resources and the host HWND. Move only the shutdown primary flush off-pump; unrelated primary-layout paths are not this feature's refactor. Ordinary master-off drains but retains the store; application exit closes it, including if the pump was never started. A timeout is incomplete shutdown, not cancellation: retain references, log/report it, refuse a replacement runtime, and finish cleanup when the worker returns. Do not promise guaranteed bounded process exit under stuck disk I/O.

## Execution sequence

Each task ends with its focused tests, `ruff check` and `ruff format --check` on changed Python files, inspection of the diff, and a normal commit. Run `polish-core --fix` before the final automated gate and inspect any edits. Suggested commit subjects below are per-task boundaries, not permission to publish an incomplete feature.

### Task 1: Restore a trustworthy checkout-only probe

**Files:** Modify `tests/manual/preview_crop_harness.py`, `tests/manual/preview_crop_model.py`, `tests/manual/README.md`; extend `tests/test_preview_crop_harness.py`, `tests/test_preview_crop_model.py`. No production behavior change.

**Interfaces:** Consume existing `ClientDiscovery.subscribe/start/stop/request_scan/snapshot`, `PreviewHost.set_discovery_request/apply_roster/_reconcile_roster`. Add `PrototypePreviewHost.wait_roster(timeout) -> bool`, backed by an Event set after its first actual roster reconciliation (even an empty roster). Keep CLI commands and opt-in acknowledgment compatible.

- [ ] Add a failing routing test using the existing harness loader/fake clients, not a direct call to `_reconcile_probe`:

```python
def test_shared_roster_path_reaches_crop_reconciliation(monkeypatch):
    from wingman.telemetry.model import RosterSnapshot
    host = harness.PrototypePreviewHost()
    calls = []
    monkeypatch.setattr(host_mod.PreviewHost, '_reconcile_roster',
                        lambda self, libs, snapshot: calls.append('primary'))
    monkeypatch.setattr(host, '_reconcile_probe', lambda libs: calls.append('crop'))
    host.apply_roster(RosterSnapshot(1))
    host._apply_pending_roster(None)
    assert calls == ['primary', 'crop']
```

- [ ] Run `uv run --no-sync python -m pytest tests/test_preview_crop_harness.py -q`; confirm the routing test fails because only the primary callback runs.
- [ ] Replace the prototype's `_sweep` override with `_reconcile_roster(libs, snapshot)` calling the base first, then probe reconciliation. In `_probe_host`, own one `ClientDiscovery`, subscribe `host.apply_roster`, set `host.set_discovery_request(discovery.request_scan)`, start the host and discovery, and wait for `wait_roster()` as well as pump readiness. Snapshot delivery alone is not enough; the pump must have applied it before the load command reads its clients. On every exit unsubscribe, stop discovery and stop the host; report failed starts/timeouts without leaking either owner.
- [ ] Fix the independent probe failures: wrap rows into monitor-bounded columns, fitting the probe destination size to the eight-slot grid when needed; test all eight positions including negative-origin/small monitors, without hiding distinct crops behind identical rescued positions or resizing any EVE client. Reject and stop incomplete stages (`live < requested`) with nonzero CLI status. Configure probe-local console logging honoring `WINGMAN_LOG_LEVEL` before host creation, and correct README log-destination claims; do not call settings-reading production logging setup. Explicitly reject mixed picker/load use in `set_probe_count` when `character` was supplied, removing the resource-overwrite path rather than expanding this disposable CLI.
- [ ] Run probe model/harness/windows and packaging tests. Add a subprocess assertion that documented INFO/DEBUG diagnostics are enabled, and a timeout CLI test that never prints `stage N is up`. Commit: `fix: restore crop probe discovery and measurement integrity`.

### Task 2: Add the normalized crop domain and settings schema

**Files:** Create `wingman/preview/crops.py`, `tests/test_preview_crops.py`; modify `wingman/settings.py`, `tests/test_settings_preview.py`, `wingman/preview/store.py`, `tests/test_preview_store.py`.

**Interfaces:** Produce the shared records and pure functions above. Constants: `MAX_LIVE_CROPS = 8`, `MIN_SOURCE_SIZE = (16, 16)`. All new defaults are `preview.crops = {}`.

- [ ] Add self-contained red tests, including:

```python
def test_normalized_source_scales_with_client_dimensions():
    from wingman.preview.crops import source_from_pixels, source_to_pixels
    from wingman.preview.geometry import Rect
    source = source_from_pixels(Rect(320, 180, 640, 360), (1280, 720))
    assert source_to_pixels(source, (1920, 1080)) == Rect(480, 270, 960, 540)
```

- [ ] Run `uv run --no-sync python -m pytest tests/test_preview_crops.py tests/test_settings_preview.py -q` and confirm missing-domain failure before creating the module.
- [ ] Implement frozen records, source conversion and serialization. Reject booleans as dimensions/numbers, nonfinite fractions, empty/anonymous names and nonpositive extents; clamp finite fractions and trim overflow to the unit square, rejecting empty remainders. Reject unsupported record versions and malformed entries individually. Diagnostic metadata never overrides normalized authority. Require integer positive original dimensions, original rectangle extents and destination sizes; original source origins may be zero and must be nonnegative. Preserve negative destination origins. Settings save/load/normalization must be a fixed point and retain unrelated preview keys.
- [ ] Derive pixel edges with the probe's floor/ceil rule; test exact edges, fractional round-trip tolerance, insets, reversed drag, source shrink below minimum and NaN/infinity. Add `preview.crops` defaults and validator calls in the same commit. Extend `LayoutStore._protected` with all saved crop owners, including disabled definitions; preserve existing protected sets.
- [ ] Verify deterministic cap suppression and that a settings write to another field cannot remove crops. Run domain, settings and store tests. Commit: `feat: define persistent normalized preview crops`.

### Task 3: Implement the asynchronous committed crop store

**Files:** Create `wingman/preview/cropstore.py`, `tests/test_preview_cropstore.py`. Consume Task 2 records and `settings.update`, without modifying `settings.py` or `atomicio.py`'s transaction API.

**Interfaces:** Produce all `CropStore` methods in the interface table. `executor_factory` returns a single-worker executor supporting `submit` and `shutdown`; construction is lazy, so untouched crops add no worker. The store holds the initial committed snapshot, not a captured nested live-settings dictionary.

- [ ] Write red tests using the real transactional settings boundary and injected executors/events. Start with admission cancellation and a real successful write:

```python
def test_success_is_exposed_only_after_transaction_returns(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from wingman import settings
    from wingman.preview.crops import CropDefinition, source_from_pixels
    from wingman.preview.cropstore import CropStore
    from wingman.preview.geometry import Rect
    live = settings.load()
    store = CropStore(lambda: settings.update(live), {},
                      executor_factory=lambda: ThreadPoolExecutor(max_workers=1))
    definition = CropDefinition(
        source_from_pixels(Rect(0, 0, 320, 180), (1280, 720)),
        Rect(40, 50, 320, 180))
    token = store.begin('Alice', epoch=1, session=None)
    try:
        result = store.put(token, definition).result(timeout=2)
        assert result.applied and result.persisted
        assert 'Alice' in store.snapshot()['definitions']
    finally:
        assert store.close().result(timeout=2)
```

- [ ] Run `uv run --no-sync python -m pytest tests/test_preview_cropstore.py -q`; confirm missing-store failure.
- [ ] Implement worker admission in this order: enter injected settings transaction, take metadata lock, reject canceled/unadmitted stale token with an internal exception, mark admitted, release metadata lock, apply per-character mutation, exit transaction, update committed snapshot/result under metadata lock, then invoke completion listeners outside all locks. Do not publish the tentative `live['preview']['crops']` while saving.
- [ ] Implement `open_epoch`/`observe_roster` so admission can check the actual current discovery session, not only the token's copied value. Host roster ingress publishes this metadata before queuing native reconciliation; stale snapshots/epochs cannot regress it. Fence unadmitted source-bound operations on session loss/renewal, but preserve admitted outcomes and configuration-only requests.
- [ ] Implement one FIFO for definition and geometry writes, per-name generations/tombstones, separate geometry sequence numbers and debounce deadlines. Use a condition/event to wake the lazy worker for deadlines rather than starting a thread for every drag event. `drain()` is an ordered flush barrier and invokes the optional `flush_primary` callback after crop transactions have exited; `close()` additionally prevents new submissions and shuts down the worker without joining itself. Failure records contain useful errors and do not kill the worker.
- [ ] Use `threading.Event` barriers, not sleep-based ordering, to prove: cancellation while waiting for settings lock writes nothing; fence during admitted write permits success; old successful put followed by successful remove stays removed; remove failure retains that put; failed replacement preserves old geometry; movement during saving reaches the replacement; geometry cannot create/re-enable; tentative settings never escape the committed snapshot; closing twice and never-started close are safe. Run store/settings tests. Commit: `feat: serialize crop persistence off the preview pump`.

### Task 4: Build the independent crop window

**Files:** Create `wingman/preview/cropwindow.py`, `tests/test_preview_cropwindow.py`; modify `wingman/preview/win32.py` and `tests/test_preview_win32.py` only for used native bindings/constants.

**Interfaces:** Produce `CropWindow` above. Reuse `Thumbnail`, `Rect`, `CLICK_PX`, `drag_target`, `resize_result`, `coalesce_moves`; do not inherit `PreviewWindow` or import `tests/manual` at runtime.

- [ ] Add red fake-Win32 tests with the recording-lib pattern from `tests/test_preview_crop_windows.py`, initially reusing its `FakeLibs` in tests only. Include:

```python
def test_candidate_is_created_without_showing(monkeypatch):
    from wingman.preview import cropwindow
    from wingman.preview.geometry import Rect
    from wingman.telemetry.model import ClientSessionId, RosterClient
    from tests.test_preview_crop_windows import FakeLibs
    libs = FakeLibs()
    monkeypatch.setattr(cropwindow, '_ensure_class', lambda libs: None)
    client = RosterClient(16, 101, 'EVE - Alice', 'Alice',
                         ClientSessionId(16, 101, 'Alice', 1))
    window = cropwindow.CropWindow.create(
        libs, client, Rect(0, 0, 320, 180), Rect(20, 20, 320, 180),
        hidden=True, locked=False, on_activate=lambda client: None,
        on_rect_changed=lambda rect: None, on_disable=lambda: None,
        on_failure=lambda reason: None)
    assert window is not None
    try:
        assert libs.user32.shows == []
        assert all(not props.fVisible for props in libs.dwmapi.updates)
    finally:
        window.close()
```

- [ ] Run `uv run --no-sync python -m pytest tests/test_preview_cropwindow.py -q`; confirm the missing-controller failure before implementation. Add initial registration/update failure cleanup regressions.
- [ ] Start from the probe's crop controller, removing probe loaders/registries and adding explicit callbacks. Use `RosterClient.character` for names and retain its session; do not assume the primary adapter's `stable_key` field exists. Production class name: `WingmanPreviewCrop`; styles remain popup/topmost/toolwindow/noactivate without layered opacity. Add `hidden=True` creation, `on_rect_changed`, source-update validation, `on_disable` and `on_failure`. On any partial failure unregister DWM before destroying its destination HWND.
- [ ] Implement capture loss with reset-before-release ordering, including lock or hide mid-gesture:

```python
def _cancel_gesture(self, *, release=True):
    had_capture = self._mode is not None
    self._mode = None
    self._start = None
    self._start_rect = None
    if had_capture and release:
        self._libs.user32.ReleaseCapture()
```

  Route `WM_CAPTURECHANGED` to `_cancel_gesture(release=False)` and `WM_CANCELMODE` to normal cancellation, without activation or recursively releasing already-lost capture. Right press begins pending-right, threshold crossing resizes, stationary release opens the Disable crop menu. `WM_CLOSE` calls `on_disable`; only host-authorized `close()` destroys the window.
- [ ] Later DWM update failure attempts one unregister/register/update for that episode. On recovery failure close the live native resource and notify `on_failure`; successful recovery ends the episode. Initial failure persists nothing and does not enter a retry loop. Include character, source HWND, rectangles and HRESULT in crop-level diagnostics.
- [ ] Test unchanged-source destination resizing, hidden creation, lock/capture cancellation, click-versus-drag, menu/close persistence routing, callback-once failure and numeric unregister/destroy counts. Extend client-targeted geometry safety guards. Commit: `feat: add independently controlled crop windows`.

### Task 5: Build the production crop picker

**Files:** Create `wingman/preview/croppicker.py`, `tests/test_preview_croppicker.py`; extend `wingman/preview/win32.py` and `tests/test_preview_win32.py` for actually used control, focus, DPI and message APIs.

**Interfaces:** Produce `CropPicker` above; reuse Task 2 mapping. Mirror destination coordinates are always relative to the picker client area, excluding toolbar/chrome and letterboxing.

- [ ] Add red mapping and native-lifecycle tests. The inset case must not accidentally select toolbar pixels:

```python
def test_toolbar_offset_is_removed_before_mapping():
    from wingman.preview.crops import map_selection
    from wingman.preview.geometry import Rect
    assert map_selection(Rect(20, 60, 320, 180), Rect(20, 60, 640, 360),
                         (1280, 720)) == Rect(0, 0, 640, 360)
```

- [ ] Run `uv run --no-sync python -m pytest tests/test_preview_croppicker.py -q`; confirm the native-controller tests fail before adding the controller.
- [ ] Port the probe's full-client DWM/selection-overlay technique into its own module, not a production import of the probe. Use a resizable tool window without maximize/minimize controls. Add native Reset/Use region/Cancel controls and status text. Keep Use region disabled until a valid current selection exists; small/empty selection stays open and explains the 16x16 source minimum. Preserve exact source-size facts in confirmation metadata.
- [ ] Handle move, resize and DPI changes by recomputing the mirror inset, owned overlay placement and current source dimensions. Resize/source-size change clears selection with `Client size changed. Select the region again.` or the picker-resize equivalent. Missing/renewed source session cancels through the coordinator. Negative coordinates and work-area fitting use actual monitors, not the virtual bounding box.
- [ ] On confirm copy the proposal, mark callback complete, release capture, close overlay/controls/thumbnail/picker, then call `on_confirm`. Cancel follows the same once-only cleanup. Focus must work before the first mouse click; implement keyboard navigation via the native dialog-message path integrated in Task 6. Review current Microsoft API signatures before adding ctypes bindings; bind lazily and test widths.
- [ ] Test all partial failures, confirm/cancel ordering, Enter/Escape/Reset, capture loss, source/picker resize, four-edge rounding and overlay cleanup. Record native dark-theme/accessibility and mixed-DPI checks for Task 10; do not claim fake tests prove them. Commit: `feat: add a production crop region picker`.

### Task 6: Coordinate crops on the current roster and native pump

**Files:** Create `wingman/preview/cropcontroller.py`, `tests/test_preview_cropcontroller.py`; modify `wingman/preview/host.py`, `wingman/preview/win32.py`, `tests/test_preview_host.py`.

**Interfaces:** Produce coordinator methods from the table. Add `WM_APP_CROP_COMMAND = WM_APP + 10`, `WM_APP_CROP_COMPLETE = WM_APP + 11`, and `WM_APP_CROP_STOP_READY = WM_APP + 12` after checking those offsets are still free. Messages carry signals; Python queues hold immutable commands/results.

- [ ] Write failing host-route and session-preservation tests before wiring. This seed proves that the crop path receives the unadapted newest snapshot; add controller-level cancellation/rebinding assertions separately:

```python
def test_crop_reconcile_receives_latest_full_session(monkeypatch):
    from types import SimpleNamespace
    from wingman.preview.host import PreviewHost
    from wingman.telemetry.model import ClientSessionId, RosterClient, RosterSnapshot
    observed = []
    host = PreviewHost(on_layout_changed=lambda *args: None)
    host._crop_controller = SimpleNamespace(reconcile=observed.append)
    monkeypatch.setattr(host, '_reconcile_roster', lambda libs, snapshot: None)
    anonymous = RosterClient(16, 101, 'EVE', None, None)
    session = ClientSessionId(16, 101, 'Alice', 3)
    returned = RosterClient(16, 101, 'EVE - Alice', 'Alice', session)
    host.apply_roster(RosterSnapshot(2, (anonymous,)))
    host.apply_roster(RosterSnapshot(3, (returned,)))
    host._apply_pending_roster(None)
    assert len(observed) == 1
    assert observed[0].clients[0].session == session
```

  Also exercise real primary reconciliation with recording windows, rather than relying solely on this routing seam.
- [ ] Run `uv run --no-sync python -m pytest tests/test_preview_cropcontroller.py tests/test_preview_host.py -q` and confirm new requirements fail on unwired behavior.
- [ ] Instantiate the coordinator on the pump. From `_apply_pending_roster`, pass it the original snapshot, not the adapted primary client dictionary; preserve retry/high-water-mark behavior if either reconciliation raises. At `apply_roster` ingress, update store authorization metadata without native calls. Preserve primary reconciliation independently; crops remain eligible when a primary is excluded. Resolve activation from the current full session on each request, then adapt through `_preview_client` only when invoking the existing `_activate_client` path.
- [ ] Maintain separate dictionaries for committed live crops, current sessions and degraded `(session, definition-generation)` episodes, plus one temporary-slot owner. Reconcile from `store.snapshot()` and current availability; normalized sources resolve against current dimensions. Rescue wholly off-screen destinations with `clamp_to_monitors`, preserving partial overhangs. Source-size changes update the live source/aspect or close as invalid-source if below minimum, without guessing a different region.
- [ ] Implement the selection/candidate/admission/completion order above. Reserve capacity before opening a new picker or candidate; reject at-cap new creation, but permit at-cap reselection using the temporary slot. Recheck at confirmation and admission. Client arrivals respect reservations; once a pending reservation ends, recompute deterministic sorted eligibility. Retain all suppressed definitions/statuses.
- [ ] Propagate resolved hidden/lock state, including newly born windows and mid-drag changes; hiding never reveals a candidate. Route picker dialog messages before ordinary dispatch, only while a picker exists. Close a renewed session's old crop and picker even if character/HWND/PID are unchanged; unchanged-session snapshots neither retry degraded work nor recreate windows.
- [ ] Test 8+picker then 8+candidate then 8, never simultaneous picker/candidate; creation at cap refused; candidate/persistence failure preserves old crop; same-session no-op; renewed-session retry; source exit/rebind; primary-excluded crop activation; no retry per scan; stale completion cleanup. Commit: `feat: reconcile crop lifecycle on the shared preview pump`.

### Task 7: Wire retained state and two-phase runtime shutdown

**Files:** Modify `wingman/__main__.py`, `wingman/preview/host.py`, `wingman/ui/api.py`, `tests/test_preview_wiring.py`, `tests/test_preview_host.py`, `tests/test_preview_cropstore.py`, `tests/test_telemetry_coordinator.py`.

**Interfaces:** Produce host request/state methods and `begin_stop` wiring. Add an optional injected crop store/coordinator factory to `PreviewHost` so existing primary-only tests retain their present behavior without fabricated native dependencies.

- [ ] Write red wiring tests with existing `FakeHost`/`make_api` patterns: never-enabled startup creates no crop worker; ordinary stop/start reuses the committed store; application exit closes it even if the pump never ran; admitted save completing after epoch change cannot create a window. Pin the master transaction correction with:

```python
def test_failed_master_save_does_not_stop_host(tmp_path, monkeypatch):
    host = FakeHost()
    api = make_api(tmp_path, preview_host=host)
    api._state.settings['preview']['enabled'] = True
    def fail_save(data, path=None):
        raise OSError('read-only settings')
    monkeypatch.setattr('wingman.settings._save_locked', fail_save)
    assert api.set_preview_enabled(False) is False
    assert host.stopped == 0
    assert api._state.settings['preview']['enabled'] is True
```
- [ ] Run `uv run --no-sync python -m pytest tests/test_preview_wiring.py tests/test_preview_host.py tests/test_preview_cropstore.py -q` and confirm lifecycle assertions fail before implementing.
- [ ] In `build_preview_host`, construct the crop store beside `LayoutStore` using `settings_mod.update(state.settings)`, validated initial definitions, and `flush_primary=store.flush` (the existing layout store's bound method). Open a new store runtime epoch before starting each new pump, resetting only runtime authorization, not committed definitions. Inject bound callbacks for state changes via `api_box`, preserving safe startup before Api exists. Do not start another telemetry coordinator or attach a second discovery subscriber in production; extend only the existing host consumer.
- [ ] Split shutdown request from final native teardown. First fence native authorizations/unadmitted source writes, freeze latest valid geometry, hide primary/crop windows, cancel picker/capture, and stop accepting new native commands. Submit already-accepted configuration-only requests held by the coordinator to the store FIFO before its drain barrier, preserving their order after any admitted write; canceled source requests receive terminal outcomes rather than disappearing. While stopping, queued roster/restyle/activation messages cannot create or reshow windows; continue servicing drain completions and cleanup. Queue crop drain and the existing primary-layout flush off-pump. On tagged ready completion, cancel picker, close crop relationships/windows, then run the existing hook/hotkey/primary/host cleanup without a duplicate synchronous flush. Keep pumping while storage is busy; handle flush failure with logged outcome and cleanup rather than a stranded pump.
- [ ] Preserve the existing timed-out-worker ownership rule. Master-off drains without permanently closing the store; final application shutdown closes it. Reject new selection while draining and do not create a replacement host while the old thread is alive. Expose `is_stopping`; reject a master-on request before changing settings while it is true, instead of persisting on and silently losing the requested restart. Update fake hosts and the state/status tests with that explicit contract. Serialize configuration-only operations while no pump runs. Fence command ingress too, not only completion handling.
- [ ] Correct master-save failure using its existing boolean shape:

```python
try:
    with settings_mod.update(self._state.settings) as cfg:
        cfg.setdefault('preview', {})['enabled'] = enabled
except OSError:
    logger.exception('Could not persist the preview setting')
    return False
```

  Only a successful transaction authorizes a new host mode. Test the page's existing boolean handling and update assertions that expected log-and-continue behavior. Fleet/alerts remain independently governed; preview shutdown must not accidentally stop an independently wanted service on master-off.
- [ ] Test blocked disk with a responsive pump, explicit timeout reporting, concurrent stop/start, duplicate ready messages, old-epoch completions, ordinary off/on restoration and final close after never-started/offline edits. Commit: `feat: wire crop persistence and ordered preview shutdown`.

### Task 8: Add semantic crop bridge requests and authoritative state

**Files:** Modify `wingman/ui/api.py`, `wingman/web/app.js`; create `tests/test_api_crops.py`; extend `tests/test_bridge_contract.py`, `tests/test_preview_wiring.py`, `tests/test_api.py`.

**Interfaces:** Produce four Api methods from the table and `onPreviewCrops`. Add crop state to `get_preview_hotkey_state` for one-read section hydration; expose the dedicated getter for explicit refresh/recovery. Define statuses: `unconfigured`, `disabled`, `master-off`, `offline`, `selecting`, `saving`, `live`, `cap-suppressed`, `invalid-source`, `degraded`, `stopping`.

- [ ] Add failing refusal tests using `make_api`, including:

```python
def test_crop_request_rejects_anonymous_owner(tmp_path):
    from tests.test_api import make_api
    api = make_api(tmp_path)
    result = api.select_preview_crop('hwnd:0x123')
    assert result['applied'] is False
    assert result['persisted'] is False
    assert result['pending'] is False
    assert result['error']
```

- [ ] Run `uv run --no-sync python -m pytest tests/test_api_crops.py tests/test_bridge_contract.py -q` and confirm missing-endpoint/handler failures.
- [ ] Validate names, boolean types, existing definitions and allowed actions at the bridge boundary. Select/reselect needs an available named session and an accepting master-on host. Saved enable/disable/remove can operate while unavailable/off without starting the host; an enable request still rejects when the live/reserved cap is full, even for an offline owner. Return immediate final refusal when unsupported; otherwise use this explicit receipt:

```python
{'applied': False, 'persisted': False, 'error': None,
 'pending': True, 'operation_id': operation_id}
```

  Terminal outcomes set `pending=False` and retain `operation_id`; cancellation is unapplied/unpersisted with a specific reason. Never report a queued operation as saved. Both getters and event payloads contain a monotonically revised snapshot plus pending/recent outcomes; a completion before its receipt is therefore recoverable.
- [ ] Publish `onPreviewCrops` through `Api._push` after readiness/state changes, not directly from workers to JS. Register the handler allowlist in the same commit. Runtime state production must not hold settings/metadata locks during `_push`; it must not read HWNDs from an API thread. Keep every Api collaborator underscore-prefixed.
- [ ] Test refusal/no-op/failure/success, late receipt versus early completion, missed-push recovery, master-off configuration, strict bool/name validation, removal results after owner disappears, and all payloads free of session/HWND/PID. Commit: `feat: expose asynchronous crop settings commands`.

### Task 9: Add compact Configure controls and crop-only lock access

**Files:** Modify `wingman/web/previews.js`, `wingman/web/style.css`, `wingman/web/dev.js`; create `tests/test_preview_crops_page.py`; extend `tests/test_page_conventions.py`, `tests/test_dev_harness.py`, `tests/test_preview_wiring.py`; update `docs/smoke-checklist.md`.

**Interfaces:** Consume Task 8 state/result contract. Add `cropState` with revision filtering inside the existing preview IIFE; handler registration must precede DOM setup that could throw. No new destination, grid column, polling timer or production fake data.

- [ ] Add failing lexical guards before UI edits, including:

```python
def test_crop_ui_has_semantic_requests_and_registered_handler():
    from pathlib import Path
    src = Path('wingman/web/previews.js').read_text(encoding='utf-8')
    for method in ('select_preview_crop', 'set_preview_crop_enabled',
                   'remove_preview_crop'):
        assert method in src
    assert "WM.handle('onPreviewCrops'" in src
```

- [ ] Run `uv run --no-sync python -m pytest tests/test_preview_crops_page.py tests/test_page_conventions.py tests/test_dev_harness.py -q`; verify the new guard fails before rendering work.
- [ ] Append a Crop field to `makeCharacterDetail` beside existing Saved geometry and Cycle group fields. Unconfigured: `Select region…`. Configured: wrapped enabled checkbox, `Reselect…`, Remove and status. Remove confirms using `WM.confirm`, naming the lost selection/position and distinguishing it from Disable. Use existing tokens and field/disclosure patterns, neutral selection/reselection buttons and `.btn.danger` for confirmed removal; no new save button. When the source/master is unavailable, leave configuration controls live but explain why source selection cannot run.
- [ ] Add all `cropState.definitions` owners to `rows()` using its null-prototype dedup map. Implement lock eligibility as `isExcluded(name) && !hasEnabledCrop(name)`; `hasEnabledCrop` reads the saved enabled definition, not runtime visibility. Update the old lexical exclusion test without weakening primary geometry exclusion. Repaint lock eligibility on crop enable/disable/remove results without resetting unrelated keybind/group edits.
- [ ] Disarm keybind capture with `endCapture()` before opening picker or confirmation. Pending receipts do not revert controls as refusals; disable only conflicting actions while showing Saving/Selecting. Accept terminal state by revision/operation ID, ignore old results, and preserve Configure disclosure/focus using existing `detailInteraction`/focus helpers. Section leave invalidates page focus intents but does not cancel an already-admitted save. Section reentry fetches authoritative state, with no write before hydration.
- [ ] Extend only `dev.js` with all new methods/events and fixtures for offline, crop-only locked, cap-full, pending, failed-save and degraded states. Exercise the actual page in the browser at 840/839 CSS widths, long names and keyboard navigation; separately schedule real Windows/WebView2 smoke. Assert all handlers register and ordinary Preview/Group/Geometry controls still work. Commit: `feat: manage character crops in Preview settings`.

### Task 10: Prove integration, package boundaries and release readiness

**Files:** Extend `tests/test_preview_cropcontroller.py`, `tests/test_preview_cropstore.py`, `tests/test_preview_host.py`, `tests/test_preview_wiring.py`, `tests/test_api_crops.py`, `tests/test_packaging_completeness.py`, `tests/test_engine_invariants.py`; update `docs/smoke-checklist.md`, `tests/manual/README.md`, `README.md`; create `docs/preview-crops-production-results.md` for actual new evidence.

**Interfaces:** All earlier contracts; do not replace tests with broad source-string assertions where injected runtime tests can prove behavior.

- [ ] Before final hardening, add deterministic integration regressions for every row in the operation table. Inject delayed writes/failures with Events and recording native factories. Include successful replacement followed by failed removal, queued versus admitted cancellation, move during replacement, session renewal with coalesced roster, master changes, hidden-at-birth, degraded recovery and late shutdown completion. Run focused tests and confirm any uncovered behavior fails before fixing it.
- [ ] Add import/packaging guards for the five production modules while preserving exclusion of all three probe modules. They are modules in the already-listed `wingman.preview` package: do not add an unnecessary subpackage or speculative hidden import. Verify actual build collection. Extend native safety guards to new modules, targeting EVE HWNDs versus owned HWNDs rather than banning legitimate crop `SetWindowPos` calls.
- [ ] Run `polish-core --fix`, inspect its diff, then run fresh full gates:

```bash
uv sync --locked --extra dev
uv run --no-sync python -m pytest tests/
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
git diff --check
```

  Run pytest on Windows as well as Linux; follow current CI packaging/version/WebView2 checks rather than stale historical version-grep instructions. No version bump is part of this feature plan.
- [ ] Perform Windows/EVE acceptance against matching primary-only baselines at stages 1/2/4/8. Keep all intended test crops visible; record exact commit, clients, hardware, monitor rectangles/scales and source resolutions. Record source-edge error (≤2 source pixels), click latency (≤500ms, p95 ≤baseline+50ms), drag gaps (p95 ≤32ms, max ≤100ms, primary p95 increase ≤50%), 60-second combined CPU delta (≤2 percentage points), DWM GPU median delta (≤5 points), and working-set delta (≤8 MiB + 4 MiB×active crops). Apply the same stage allowance during the temporary-slot exercise; do not invent a larger allowance after measuring.
- [ ] Repeat stage eight with picker open, then candidate replacement, cancellation, initial DWM failure and save failure. Count thumbnail registrations/unregistrations separately from top-level/owned/child HWND creation/destruction; verify peak relationships equal baseline primary relationships plus at most nine. Explain the picker's extra overlay/control HWNDs and require all to return to baseline. Validate crop close, source exit/logout/return, source minimize/restore, occlusion, alert pulses, capture theft, lock/visibility, monitor rescue, source/picker resize, negative coordinates and 100/125/150/200% scaling. Never change a real EVE client's geometry to automate the test.
- [ ] Record results honestly in the new production-results document; leave historical probe values unchanged. If eight fails, lower the cap to a fully tested passing stage and rerun the temporary-slot case. If only the extra slot fails, implement/test the approved strict-cap fallback requiring a free slot before reselection. If one crop fails, block release. Missing hardware or unrun gates are release blockers, not passes; report them rather than extending scope or declaring completion.
- [ ] Update help with measured minimized-source behavior, restoration/master/exclusion semantics and actual released cap. Review final diff against spec, use `change-explainer` for completion, and commit only verified claims: `test: verify production crop lifecycle and release gates`.

## Coverage map and adaptation points

| Spec requirement | Tasks |
| --- | --- |
| Probe repair and trustworthy evidence | 1, 10 |
| Single-object normalized schema, forgiving load, protected offline owners | 2, 3, 9 |
| Separate native controllers, picker controls/mapping and capture loss | 4, 5 |
| Eight active plus one shared temporary slot, rollback and cap fallback | 3, 5, 6, 10 |
| Full session identity, coalesced snapshots and bounded recovery | 4, 6, 10 |
| Admission boundary, committed snapshots, geometry sequences/tombstones | 3, 6, 7, 10 |
| Master/offline behavior, nonblocking shutdown, upload/fleet independence | 7, 8, 10 |
| Semantic bridge, pending outcomes, Configure UI, crop-only unlock | 8, 9 |
| Automated/platform/packaging/manual release gates | All tasks, final gate 10 |

Stop and revisit the affected plan section if the host/telemetry lifecycle or settings transaction contract changes during a rebase; do not patch against obsolete line numbers. If native picker controls cannot meet focus/accessibility/DPI requirements, revise that controller with a reviewed alternative, not a web overlay on EVE. If an implementation needs a broader settings/atomic-writer change, a second pump, a new dependency, or multiple persisted crops, stop for design approval. The explicit admission boundary removes the need for any of those today.

The reviewed scope is only production one-crop-per-character previews. Do not implement the parent roadmap's alert localization, discovery hooks, character-select cycling, portable profiles, label customization, global visibility modes or static-frame experiments.
