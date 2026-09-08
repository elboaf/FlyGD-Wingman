# Lane D — Fleet presentation handoff

Base: `2a1d846725f50d42e8a496e2fc64100dd56a47ca`.
Decision: coordinator D-01 (approved roster accumulator and daemon worker).

## Failure and reproduction

The real coordinator invokes subscribers synchronously. Fleet's receiver used
settings.update and three potential WebView targets on that dispatcher. The
new parametrized regression stalled each boundary (Fleet, main, sig-bar mirror,
and settings save), then asserted that a later subscriber ran before release.
All four failed on the unchanged implementation at that assertion. Initial test
setup errors (missing fleet_bar fixture section and empty fake metric rows) were
corrected before establishing those four intended failures. Worker lifecycle
and reducer tests were also added before their implementation.

## Implementation and ordering

- `_receive_fleet_snapshot` accepts state synchronously and wakes one owner.
  It does no persistence, JS, thread creation or join. Snapshot storage is one
  latest reference, and the worker wakeup is one bit, not a task queue.
- `RosterMemory` folds each transition's sorted current tier, logical pending
  cap-overflow tier, and prior logical seen tier through existing normalization.
  This preserves newest-transition priority and the existing 64-name seen cap.
  A separate insertion-ordered admission ledger retains all actually
  unacknowledged names for configurability. Neither it nor existing failed-name
  memory gets a new arbitrary cap. Storage scales with distinct remembered
  names, not the count of telemetry frames or transitions.
- Only an actual settings transaction acknowledges names. Failed writes retain
  the pending retry tier and retry on a later roster transition, not metric-only
  frames. Successful writes remove only retained names admitted no later than
  the captured version. Repeated names admitted during that save survive its
  acknowledgement. Priority promotions carry separate transition ages: a name
  promoted from cap overflow by a later empty roster must survive an older
  acknowledgement even without a new admission. Coalescing is not a claim that skipped physical writes
  succeeded: names absent from the actual durable candidate remain pending even
  if the logical priority reducer once included them.
- All runtime writes still use settings.update/update_section unchanged.
  Character visibility remains synchronous/durable at its endpoint; its
  subsequent semantic presentation, like lifecycle presentation, is queued.
- The single worker captures local activation, revision and all actual window
  identities before saving. It revalidates before every later JS stage and
  keeps captured targets. A later snapshot supersedes the old display, not the
  roster memory. A retired activation cannot redirect a continuation to a new
  bar, even when sharing keeps the coordinator generation unchanged. Invalidated
  delivery requeues the latest state: a target-only change (such as sig-bar
  creation) may not produce another telemetry snapshot to wake the worker.
- Worker construction is inert. Main starts before subscribing; failed startup
  leaves no subscription and an enable can retry. Disable does not churn
  workers. Stop retains a timed-out owner; start refuses a second live owner.
  The worker is daemon per D-01: a WebView call already entered cannot be
  cancelled and must not hold process exit hostage.

## Lock and lifecycle contract

Existing order remains `shutdown_lock -> Fleet native lifecycle -> presentation`.
Worker startup accounting may occur under Fleet native lifecycle; its short
worker lock protects only thread identity/running/stop state. The worker's
iteration lock serializes processing and the deterministic test drain. The
telemetry callback never acquires either worker lock; it only sets the wakeup
Event while holding the brief presentation lock.

Settings transactions, JS and joins never hold the presentation lock. JS and
joins also never hold Fleet native lifecycle. No settings-lock-to-presentation
nesting was added: roster acknowledgement runs after transaction exit.

Main closes acceptance and marks quitting, detaches, and bounded-stops before
native destruction. The same idempotent teardown runs after the GUI loop and
before telemetry teardown in shutdown_previews. Native create/show/hide/ready/
geometry/destroy ownership remains on existing paths, never on the worker.

## Tests and integration surface

New worker tests use Events and bounded joins, not sleeps. Coverage includes
four blocked-call boundaries through a real coordinator, next iteration,
coalesced display and persisted names, admission-safe acknowledgements,
actual failed-save/retry, deterministic logical reducer comparisons, repeated
names, cap eviction/overflow, local activation with unchanged coordinator
generation, replacement targets, thread factory/start failure, timed-out owner,
shutdown rejection and detach-before-join-before-native-destroy ordering.

Existing Fleet contract tests explicitly drain the new owner rather than
assuming receipt performs synchronous I/O. Their startup seam does not spawn
threads; the lane-owned regression file exercises the real thread implementation.

Shared source edits are limited to the new Fleet import and Fleet constructor
fields, Fleet methods and Fleet detachment portion of shutdown_previews in
ui/api.py; and Fleet subscription, pre-destroy stop, and post-GUI stop in main.
No settings transaction implementation, preview config reader, telemetry core,
public bridge payload/name, native window module or JS changed.

## Polish findings resolved

Independent review of the initial implementation found two correctness gaps:
older acknowledgements erased later cap-overflow priority promotions, and a
target-only invalidation could strand the sole wakeup while Fleet was off.
Both reproduced as deterministic failing regressions before correction. Priority
age is now distinct from admission age; invalidated deliveries reschedule the
current state without redirecting the captured job. Regressions also cover an
inherited failed tier, and target changes before delivery and during main push.
The main-state test decodes through the existing JSON.parse-aware test helper;
raw JSON decoding was an incorrect test assumption corrected during verification.

## Remaining gaps / proposed central smoke checklist

- Windows/WebView2: restore hidden Fleet at startup, first fit/ready/reveal,
  rapid off/on with sharing active, hidden character restore, and Quit during
  delayed page evaluation; verify previews/alerts retain cadence.
- An already-entered WebView call cannot be undone. Invalidation prevents later
  delivery stages, not cancellation of the entered native call.
- Existing public ready/fit/move callbacks still carry no page-instance identity;
  stale callbacks from a replaced page are explicitly deferred by D-01.
- A settings save already in progress may finish after shutdown invalidation.
  It remains a shared, atomic settings transaction; this lane does not promise
  cancellation or global committed-reader isolation.
- No codec code changed. Full suite's unavailable codec/native skips are not
  Windows/native verification.
