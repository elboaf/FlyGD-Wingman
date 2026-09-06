# Production cropped previews — one crop per character

**Status:** Design approved in conversation; written spec awaiting review.
**Date:** 2026-09-06
**Implementation baseline:** `57ce91d` (includes PRs #162, #170 and #171).
**Scope:** Phase 1 cropped previews only; no implementation in this change.

## Authority and outcome

Deliver one independently positioned live crop per named EVE character,
configured in Settings › Previews, persisted across restarts, and rebound when
that character returns. The normal primary preview remains unchanged.

This spec supplements the [approved crop design](../../preview-evolution-crops-design.md),
not the entire preview-evolution roadmap. Its architecture, persistence,
lifecycle, failure behavior and test contracts continue to apply except for
the explicit resource-budget and asynchronous-commit refinements below.
[PRODUCT.md](../../../PRODUCT.md) and [DESIGN.md](../../../DESIGN.md) remain the
product and UI authorities. The [prototype results](../../preview-crop-prototype-results.md)
record evidence, not a production-release approval.

## Approved scope

- Zero or one saved crop per named character, with independent enablement.
- A Wingman-owned enlarged DWM picker, never an overlay on the real client.
- Click to activate the owning client through the existing asynchronous path;
  drag to move and resize the crop, preserving source aspect by default.
- Remember source selection and destination placement across app restarts.
- Close on logout, anonymous character select or client exit; retain the
  definition and recreate when the named character returns.
- Select, reselect, enable, disable and remove from Settings › Previews.
- Inherit resolved character locking and hide-on-lost-focus behavior.
- `preview.enabled` remains the runtime master. Off closes crops and picker
  without rewriting individual definitions or enabled states. Crop controls
  never start a separate host. Configuration remains visible while off.
- Primary-preview exclusion does not disable that character's crop.

No crop labels, alert rendering, independent hotkeys, multiple named crops,
profiles, import/export, frozen frames, custom opacity or click-through mode.
Later alert, discovery, character-select, label and visibility initiatives
remain separate projects. Existing discovery is reused, not redesigned.

No crop operation may move, resize, reposition or maximize a real EVE client,
send gameplay input, or add a dependency to uploading.

## Resource budget: eight active plus one temporary

The provisional active-crop cap is **eight**, subject to the existing release
gates. A single additional temporary slot is approved for selection and safe
replacement, also subject to new Windows measurements. This is permission to
implement and validate, not evidence that the additional slot is safe.

- Count owned native resources, not just visible registry entries: a hidden
  candidate consumes the temporary slot.
- The picker and candidate share that slot and must never overlap. On confirm,
  capture the validated proposal and close/unregister the picker before
  allocating the candidate. There is only one selection/replacement operation
  using the temporary slot at a time.
- At capacity, eight committed crops may coexist with either one picker or one
  hidden replacement, never both. Primary-preview relationships are additional
  and must be present in performance measurements.
- Successful replacement releases the old crop in the same pump turn as the
  candidate becomes authoritative and visible. Failure releases the candidate
  and preserves the old crop and definition.
- New creation or enabling must obey the active cap; the temporary slot is not
  permission to enable a ninth committed crop. Concurrent requests and client
  arrivals cannot steal a reserved slot or bypass the cap.
- Saved definitions may exceed the active cap. Retain the parent design's
  deterministic case-insensitive ordering and visible cap-suppressed status;
  suppression never deletes a definition.

If the temporary-slot validation fails, the fallback is a strict resource
ceiling: at capacity, require disabling another crop before opening the picker
for reselection. Do not destroy a working crop merely to make editing possible.
A lower measured active cap lowers the same budget accordingly.

## Architecture and current integration points

Use the parent's proposed pure crop model, separate crop-window controller and
separate picker controller. Do not add an `is_crop` mode to `PreviewWindow` or
create another native pump thread.

`PreviewHost` owns all crop/picker HWND and DWM operations, live bindings,
resource reservations, reconciliation, visibility, activation and teardown.
A saved owner is a character name; a live binding includes current HWND and PID.

The current host consumes `RosterSnapshot` through `apply_roster()` and
`_apply_pending_roster()`, with `_reconcile_roster()` on its pump thread.
`request_sweep()` requests shared discovery; `_sweep()` is only a legacy test
adapter. Production and repaired probe wiring must use the current shared
`ClientDiscovery` lifecycle and snapshot delivery, not override `_sweep()` and
assume the runtime calls it.

The page sends semantic character-based requests, never HWNDs. Workers return
semantic results through the existing API/push path. Exact endpoint, message
and class-style choices belong in the implementation plan after checking the
current source; they are not new public interfaces established by this spec.

## Persistence and asynchronous operations

Use the parent's version-1 single-object-per-character schema semantics:
normalized client-area source coordinates are authoritative, original pixels
and dimensions are diagnostic, and destination geometry is physical
virtual-desktop pixels. Validate finite values, source bounds and minimum size.
One malformed definition must not prevent startup. Do not introduce a list
schema or implement multiple-crop migration ahead of the feature.

All mutations use the existing transactional settings boundary. Crop geometry
has separate pending deltas and generation/tombstone protection; never merge
crop geometry into the primary-layout store.

Disk writes must not block the preview pump. Native preparation happens there;
a settings worker commits; its completion returns through the pump mailbox.
Operations carry identity/generation tokens, and settings mutation ordering
must prevent an older operation overwriting a later disable, removal or edit.
Never hold the settings lock while waiting for the pump, or make the pump wait
for a worker that needs a pump callback.

Required outcomes:

- Creation/enabling while available validates native setup before persistence.
  Write failure destroys the new crop and leaves no new saved definition.
- Reselection keeps the old crop visible while preparing and persisting the
  candidate. Candidate or persistence failure leaves the old definition and
  live crop unchanged. Preserve the latest destination geometry through the
  asynchronous handoff, including movement during the operation.
- Disable/removal persist before closing the committed crop. Write failure
  leaves it enabled and visible. Stale geometry callbacks cannot recreate it.
- Client loss or master-off before commit cancels pending native work. If a
  successful write has already committed when availability changes, retain the
  committed definition but do not display a stale candidate; reconcile against
  current availability and master state.
- Shutdown fences new work and late completions, settles in-flight settings
  transactions, and flushes only valid current geometry before native teardown.
  No late completion may reopen a window or resurrect removed state.

The implementation plan must spell out the operation states, lock ordering and
commit/cancellation boundary and test their interleavings. This refines the
parent's synchronous-looking create/persist/swap description without weakening
its rollback guarantees for native setup or persistence failure.

## Settings and failure experience

Use compact per-character controls in the existing Previews table:
`Select region…` when unconfigured; enable/disable, `Reselect…` and Remove when
configured. Provide understandable picker selection, reset, confirm and cancel
states and a discoverable transactional crop-close/disable affordance.

Saved owners participate in row composition and roster-pruning protection.
Offline, cap-suppressed and failed crops remain visible and removable. Explain
whether the crop is waiting for its character, suppressed by the master/cap,
requires reselection, or failed to render/save. Do not misreport a refused
operation as applied or erase a user's preference because runtime is unavailable.
Use the existing per-field result contract and page-handler allowlist.

Retain the parent's bounded DWM recovery policy: one recovery attempt per
failure episode, then degraded status until a meaningful lifecycle event or
explicit retry. Log enough identity, rectangles and HRESULT context to diagnose
failure without warning on every discovery update. Record minimized-source
behavior in help; live minimized rendering is not a new promise.

## Delivery sequence

1. Repair the checkout-only probe: current discovery/pump wiring, monitor-safe
   stage placement, explicit incomplete-stage handling, usable probe-local
   diagnostics, and resource ownership when selection meets staged crops.
   Keep it excluded from the packaged runtime and free of settings I/O.
2. Build one complete production slice: select → create → persist → restart
   restore, including normalized validation and compact Settings controls.
3. Complete lifecycle and failure handling: rebinding, reselection/rollback,
   generation-safe geometry, cap/reservations, capture loss, lock/visibility,
   monitor rescue, recovery and shutdown.
4. Exercise production Windows release gates and decide the measured active
   cap and temporary-slot policy. No partial runtime ships before this gate.

## Verification and release acceptance

Add Linux-testable coverage for the parent's pure-model, host, geometry,
settings and bridge contracts, plus:

- Real snapshot-to-pump reconciliation routing, not only direct crop-helper
  tests; CLI discovery startup and teardown through injected seams.
- Every supported probe stage remains accessible on representative monitors;
  timeout/incomplete stages stop rather than claiming readiness.
- Probe diagnostics work under the documented invocation without reading or
  writing application settings.
- Native resource counts include hidden candidates and pickers; no overlapping
  temporary users or leaked replaced crop, including concurrent requests.
- Delayed successful/failed settings completion, client loss, master toggles,
  movement during replacement, remove/disable races and shutdown fencing.

The existing [smoke checklist](../../smoke-checklist.md) and prototype thresholds
remain release gates: quantitative source-edge accuracy at 100/125/150/200%
DPI and negative monitor coordinates; activation/drag latency; sustained
CPU/GPU/memory measurements; numeric HWND/DWM accounting; source geometry
safety; logout/rebinding/minimize/occlusion/cancel/shutdown; capture loss;
production lock/visibility; picker resize; and primary alerts under load.

Extend that matrix to eight active crops plus the temporary picker and then
replacement, with normal primary previews present. Verify resource return to
baseline after confirm, cancel and failure. Repaired-probe and production runs
must record their actual commit and matching baseline; do not retroactively
mark the older probe results as passing.

Run pytest, Ruff lint/format and applicable packaging/bridge checks. Exercise
Settings visually at the supported viewport floor and on Windows/WebView2.
Linux tests do not prove that DWM rendered the expected pixels. Release only
when applicable gates pass, or after an explicit evidence-backed scope revision.
