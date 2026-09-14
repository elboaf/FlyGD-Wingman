# Saved Preview layouts — approved publication amendment

The maintainer approved option 1 during implementation: retain the blanket
no-page-work-on-Preview-pump guarantee by reusing the existing presentation worker,
not by narrowing the guarantee to the new operations.

This supplements [the design](preview-layouts-design.md) and
[implementation plan](preview-layouts-plan.md). Snapshot scope, persisted schema,
explicit-save behavior, geometry/visibility admission and source immobility are
unchanged. Tasks 1–3 are not reimplemented.

## Task 4 continuation — shared presentation

Reuse the **same** `FleetPresentationWorker` instance already owned by `Api`.
Its callback becomes a small presentation dispatcher: service bounded Preview
notifications and run the existing Fleet iteration, preserving its deadline.
No new executor, presentation thread owner, persistence owner or runtime owner.
Keep existing module/class names unless a concrete necessity emerges.

Start that instance before Preview starts, independently of Fleet enablement,
telemetry availability and recording-directory configuration. Separate starting
presentation from subscribing to Fleet telemetry. Fleet Off must not stop Preview
presentation. Final stop retains the existing timed-out worker reference.

Native/discovery callbacks perform only data admission and wakeups:

- Every discovered name still reaches `LayoutStore.record_character` immediately;
  coalescing presentation must not lose intermediate seen-name admissions.
- Primary hotkey/roster/layout notifications mark a dirty bit. Delivery samples
  current authority rather than replaying a stale hotkey-status argument.
- Crop notifications keep only the newest host-revisioned detached snapshot.
- Captured keybind events keep session identity (below), not an unbounded queue.
- The existing Wanderer detached metadata handoff stays unchanged.

Detach bounded mailbox work under a short lock; collect payloads and call the
page outside mailbox, controller, host, writer and worker lifecycle locks. A
notification arriving during delivery must retain its wake. Blocked WebView
presentation must not block native completion, subsequent pump commands or the
geometry writer. Preview draining is not behind a Fleet-specific early return;
an exception in one presentation domain must not permanently starve another.

Close Preview publication ingress before native window destruction. Queued
notifications cannot reach the main or sig-bar WebView afterward. Already-entered
presentation remains owned by the existing worker and may time out, never justify
creating a replacement. Do not route through the conditional watcher Scheduler,
PreviewRuntime lifecycle thread or CropStore persistence queue.

## Capture-session safety

Asynchronous captured-key delivery must not apply a key from capture A to newly
armed row B. Carry capture-session identity through page arm/disarm, the bridge,
Host capture consumption, the bounded mailbox and the page handler. Reject stale
arm/disarm requests and ignore results for a superseded session. Keep native
immediate disarm on consumption and the page's existing wait-before-inviting-a-key
behavior. Preserve its local keydown path when native capture is unavailable.

Pin the concrete transport in tests, including reversed bridge completion,
cancel/rearm while presentation is blocked, and screenshot/section ownership.
There is no persisted capture identity and no new public product feature.

## Task 5 foundation — settled working-geometry refresh

Land the refresh port, revisioned projection and page acceptance together in
Task 5, before its controls. Task 4 establishes the shared owner and safe ingress;
it does not claim geometry ordering is solved by a full hotkey refresh.

Freeze this wire projection:

```text
PreviewGeometry {
  geometry_revision: integer,
  sizes: {name: [w, h]},
  layout_sources: [{name, online, geometry: {x, y, w, h}}],
  sizable: [name],
  client_sizes: {name: [w, h]}
}
```

One dedicated Api sampling lock serializes fresh committed-Preview and detached
host-memory reads, projection construction and revision allocation. No disk,
native, controller-state or page calls occur in that lock. Every successful
sample advances `geometry_revision`, even when values are unchanged; cache one
detached projection and never assign a new revision to caller-supplied old data.
This is ordered observation, not a cross-source atomic settings/native transaction.

Preserve authorities: sizes use committed layouts/configured defaults for seen
and live names; Copy sources prefer retained host layouts even while Off, otherwise
committed layouts; sizable combines eligible live names and committed geometry;
client sizes are host samples only while EVE delivery is eligible.

Api seams are `_sample_preview_geometry() -> dict`,
`_request_preview_geometry_refresh() -> None`,
`_refresh_preview_geometry() -> dict`, and
`_publish_preview_geometry(payload) -> None`. Dirty ingress uses the existing
shared mailbox, not the sampling lock. Sampling releases its lock before requesting
delivery or pushing. The full getter takes these fields from one sample. A new
semantic `onPreviewGeometry` event carries only this projection.

Add `PreviewLayoutsPorts.refresh_geometry: Callable[[], dict]`. An admitted
operation commits, awaits native/deferred completion, samples/requests refresh
outside the controller lock, releases, then settles. Final receipts add
`geometry: PreviewGeometry | null`; a sampling failure preserves the last cache
and adds a warning without downgrading durable success. Apply samples even when
unchanged and while Off, after retained authority is installed. Do not overload
`publish_state` or deliver from a Future done callback on the pump.

Geometry-only dirty notifications cover successful LayoutStore `_write`,
`replace`, `clear`, and `transact` commits after all writer/settings locks release;
all retained host geometry installations/clears; discovery/eligibility/client-size
changes; and successful configured-default-size changes. Bind one store commit
callback during Api composition before runtime startup. A notification failure
must not turn a durable store result into a false persistence failure. Both host
and store notifications are necessary across debounce and retained installation.

The page has one geometry high-water mark and `acceptGeometry` for events, getters
and receipts. Both full-getter paths overlay the newest accepted geometry before
replacing state. Geometry-only delivery never increments keybind `pushes`. Remove
Size's optimistic requested-dimension patch: a queue-success acknowledgement does
not write geometry. Preserve drafts, capture, focus and screenshot/live isolation.

Mandatory history: sampled 500/rev10 → unsampled Size600 → Apply500/rev11 → delayed
Size acknowledgement. The acknowledgement changes nothing. Also prove a later
ordinary Size/Copy/Reset supersedes Apply and older getters cannot restore its
prior geometry.

## Verification gates

- Real main adapters and native fixtures assert all reached `evaluate_js` calls
  occur off-pump: normal discovery/rebind/geometry/crops/capture and new layout
  capture/Apply/visibility.
- Event-blocked presentation leaves native futures, another pump command and
  writer completion live; mailboxes stay bounded and deliver newest state later.
- Intermediate seen names survive coalescing.
- No recording directory, Fleet disabled and telemetry unavailable still use
  that one presentation instance successfully.
- Capture A cannot bind or disarm B after cancellation/rearm and delayed delivery.
- Final closure fences both WebViews and retains timed-out presentation ownership.
- Off/companion-only Apply refreshes working geometry without starting EVE.
- Focused production-page tests cover geometry/getter/Size/keybind ordering.

Portable tests and browser rendering are not Windows/WebView2/live-EVE acceptance.
