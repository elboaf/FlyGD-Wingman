# Broad CI waste reduction — Stage A design

## Status

Approved architecture and specification. Implementation requires a separate
reviewed plan.

Stage A changes test architecture only. It preserves every current test identity,
production behavior, public interface, workflow, dependency, cadence, marker,
workflow test selector, shard, timeout, and release gate. It authorizes no
production edit.

The approved sequence is:

- **Stage A — this design:** remove same-identity deterministic waste in one
  Preview readiness fixture, one rolling timing oracle, and eight screenshot
  walk tests.
- **Stage B — later and separately reviewed:** persistent page workers and one
  real saved-layout receipt bundle. This design fixes only that boundary; it
  does not select worker families, protocols, receipt contents, or exact Stage B
  identities.
- **Stage C — later and separately reviewed:** mutation-qualified deletion or
  consolidation of mapped low-value tests. The current discovery estimate is
  about 346 candidates, not an authorized deletion list or count target.

`PRODUCT.md` and `DESIGN.md` do not govern this tranche because it changes no
product behavior or rendered screen. The CI redesign, completed CI tranches,
current test helpers, and exact production APIs are the authorities.

## Decision

Implement three bounded corrections:

1. repair the test-local Preview readiness observer so it follows the sole
   callback that `Api` actually installed instead of waiting five seconds on a
   callback that `Api` replaced;
2. bound only the 2,101-prefix rolling test's independent expected timing window
   from the explicit 95-second protocol rule and its fixed one-second cadence;
3. focus eight full 61-screen screenshot walks while retaining one complete
   inventory/floor traversal, exact Preview success/failure order, every actual
   Fittings screen in order, and all 27 already-focused walks.

All 16,609 ordered test identities and all platform outcomes/skips remain exact.
Stage A acceptance is structural and contractual. Hosted durations are reported
as observations only. No speedup, lower bound, critical-path reduction, runner
throughput improvement, or new suite budget is claimed.

## Authority and frozen baseline

### Source authority

The implementation baseline is merged `main` commit
`463bccb07077325e64b6ad7f7ce4e9c100d2fcd6` (`Stop Fleet source bootstrap at
accepted readiness (#290)`). Relevant authorities inspected for this design are:

- `AGENTS.md`;
- `docs/ci-test-strategy-design.md` and
  `docs/ci-test-strategy-phase-1-results.md` for the historical persistent-worker
  and rejected-xdist decisions;
- `docs/ci-test-budget-redesign.md` and
  `docs/ci-test-budget-fleet-tranche-results.md` for the current consolidation
  policy and contract rules;
- the Stage 1–3 screenshot designs/results and the later setup, Windows-resource,
  and source-readiness designs/results;
- `tests/test_preview_runtime_review.py`,
  `tests/test_preview_presentation.py`, and
  `tests/test_preview_geometry_publication.py`;
- `wingman/preview/runtime.py`, `wingman/ui/api.py`, and
  `wingman/ui/fleetpresentation.py`;
- `tests/test_fleetsharing_timing.py` and
  `wingman/fleetsharing/timing.py`;
- `tests/test_shoot_screens.py` and `scripts/shoot_screens.py`.

The existing completed screenshot consolidations authorize measured later
review, not automatic deletion. The latest source-readiness results likewise
preserve claim discipline: structural work may be stated exactly; one hosted
run does not establish an elapsed-time effect.

### Latest hosted observation

The exact current artifacts are retained under
`/mnt/c/dev/flygd-wingman/tmp/next-hotspot-36208309831`. They are PR #290 run
`36208309831`, attempt `1`, for reviewed executable head
`3523dd0873493c8ecac0599b7c2daaf4d44d5902`, synthetic merge
`26428a687ad24f99cb21f8ff9f18628023c71799`, and base
`f6e8ecd5b09889e79aa169ce103b2eb9681cec9f`.

| Role | Exact job | Result | Job / Test observation |
|---|---:|---|---:|
| Checks | `108309461453` | success | `9s` / n/a |
| Ubuntu | `108309461358` | success | `307s` / `287s` |
| Windows | `108309461427` | success | `741s` / `680s` |

Artifact identity is exact:

| Platform | Artifact | ZIP SHA-256 | XML SHA-256 | Timing SHA-256 |
|---|---:|---|---|---|
| Ubuntu | `10894627359` | `3670232e32405fd1342e45eef655c7640f8650d5e52dacc29383715196faa15e` | `44474a56fc90e93d267df3f11318d12acf0a4515bc71e0c9db2f02bfcd0d8d1b` | `bd208ba1e6a502b553e0f00e7e8914fb925073a21b3329a26d96af447d46d4f7` |
| Windows | `10894793997` | `f7afad089e74456e76e1b3133a0a55c8d5f296c5a557af16b1009e80c6f6300f` | `1b993ea2dcf7245fceec7fb7213d4212d6a77f94925cc4c7274eaf3d0a62acdb` | `cde109559e59aa89cc9ddba2dff0c8c796aad77735defd1c7fd62614b9d88c12` |

Both platforms contain 16,609 unique identities in the same order, with ordered
final-newline SHA-256
`f468ba1954d3ff0ab693dd721ff8a7a4d12266e16d8568035de4245a6c616100`.
Ubuntu is exactly 16,595 passed plus 14 skipped. Windows is exactly 16,542 passed
plus 67 skipped. The normalized ordered skip-array hashes are Ubuntu
`14f1511f840fb2fdc1680123dde29a7143405829af97141d62c5099aa4f265af`
and Windows
`41a767f45f49215310104dc611a4e9b60e4cb251e90f850b80a6f3b1cd9bcfb6`.
There are no failures, errors, Node skips, codec skips, or unexpected native
availability skips.

The Windows timing JSON reports a `646.538s` testcase sum. The XML suite time is
`675.274s`; the job API's Test-step observation is `680s`. These are different
measures and must not be substituted for one another.

### Stage A hotspot observation

The affected Windows testcase observations total exactly `42.502s`:

| Area | Current affected identities | Windows testcase sum |
|---|---:|---:|
| Disconnected Preview readiness waits | 4 | `20.275s` |
| Rolling 2,101-prefix timing oracle | 1 | `13.320s` |
| Eight complete screenshot walks | 8 | `8.907s` |
| **Observed affected upper sum** | **13** | **`42.502s`** |

`42.502s` is only the sum of these current testcase observations. It is not a
promised saving, a lower bound, or a projection from testcase sum to Test-step,
job, or critical-path wall time.

## Stage A invariants

Every implementation decision is subordinate to these invariants:

1. complete collection remains exactly 16,609 unique ordered identities with
   the frozen hash above;
2. no test is added, deleted, renamed, reordered, reparameterized, remarked, or
   moved to another cadence;
3. all current assertions named below remain executable, either against their
   own focused walk or against one shared immutable failure receipt;
4. production source/helper behavior, public interfaces, workflows,
   dependencies, configuration, packaging, cadence, markers, workflow test
   selectors, budgets, shards, and timeouts do not change;
5. the Preview wait bound remains exactly five seconds and its final predicate
   remains unchanged;
6. the rolling timing test still constructs, prepares, checks, and commits all
   2,101 production transitions;
7. `diagnostic_oracle()` remains unchanged for its full-vector and all other
   callers;
8. production `shoot.walk()` and the 61-entry `SCREENS` inventory remain
   unchanged;
9. Node and the built release settings codec remain mandatory full-suite
   prerequisites;
10. elapsed timings are observational; acceptance is identity, structure,
    mutation sensitivity, order independence, and contract preservation.

## 1. Preview readiness observer

### Existing defect

`runtime_pump` in `tests/test_preview_runtime_review.py` constructs a
`PreviewRuntime`, installs its own `publish` callback, and exposes
`r.wait_state(predicate)`. `main_api()` then constructs the real `Api` with that
same runtime. `Api.__init__` calls:

```python
self._preview_runtime.set_state_callback(self._preview_runtime_changed)
```

`PreviewRuntime` has one `_callback`, not a subscriber list. The Api callback
therefore replaces the fixture callback that owns `Condition.notify_all()`.
Runtime transitions still complete, and `Condition.wait_for()` evaluates the
unchanged predicate true at its final timeout check, so the tests pass after
paying the whole five-second bound.

Exactly these four hosted identities exhibit that shape:

| Identity | Current Windows observation | Readiness call |
|---|---:|---|
| `tests/test_preview_presentation.py::test_main_adapters_never_present_on_pump_and_coalesce_while_page_blocked` | `5.150s` | `eve_on(r)` after `main_api()` |
| `tests/test_preview_presentation.py::test_identified_capture_through_main_while_old_delivery_is_blocked` | `5.009s` | `eve_on(r)` after `main_api()` |
| `tests/test_preview_geometry_publication.py::test_retained_drag_and_commit_notify_distinct_authorities` | `5.057s` | `eve_on(r)` after `main_api()` |
| `tests/test_preview_geometry_publication.py::test_off_apply_refreshes_retained_geometry_without_eve_start[True]` | `5.059s` | companion activation after `main_api()` |

The `[False]` companion row does not wait for a runtime transition. No other
identity in the two files has this disconnected callback shape. The hosted four
sum is `20.275s`, observationally.

### Test-local interface and two wait modes

Extend only the fixture interface in `tests/test_preview_runtime_review.py`:

```text
wait_state(predicate, *, trigger=None)
_wait_for_runtime_state(runtime, predicate, states, trigger) -> None
```

The two modes have different and explicit contracts.

**Legacy snapshot mode** is `wait_state(predicate)` with no trigger. Its code
path remains the existing fixture condition/current-snapshot wait. It is allowed
only where the fixture's `publish` callback still owns delivery, either directly
or as the explicit tail of a known composed callback. `publish` appends its
detached state and notifies while holding the same fixture condition used by the
waiter, so a callback that was already captured cannot be mistaken for completed
delivery: the waiter cannot acquire that condition until `publish` returns.
`layout_api` is the established composition example—it captures `publish` and
installs a callback that calls Api first and `publish(state)` second. No-trigger
mode retains the existing current-snapshot predicate and five-second bound. It
is not permitted after an unchained owner such as `main_api` replaces `publish`.
This ownership rule is a documented fixture contract rather than an unsafe
identity guess: a legitimate composite callback is not identical to `publish`.

**Trigger-driven mode** is `wait_state(predicate, trigger=callable)`. It owns the
transition and must arm before invoking it. It never accepts an already-visible
target as success. Its behavior is exact:

1. create a fresh local `Condition` and completed-delivery list;
2. acquire `runtime._condition` before the trigger can run;
3. require `predicate(runtime._snapshot())` to be false; a true predicate means
   the transition was triggered too early or the test supplied a stale target,
   so fail without invoking the trigger;
4. capture the exact current `runtime._callback` object as `delegate`;
5. reject a marked observer already in the callback slot before invoking the
   trigger; concurrent trigger waits are unsupported and may not accumulate;
6. install one marked observer directly while still holding
   `runtime._condition`, without clearing `_published`, calling `_wake()`, or
   using `set_state_callback()`;
7. release `runtime._condition`, then invoke the trigger exactly once;
8. for every state delivered to the observer, call the exact captured delegate
   once with the exact state object and return its exact result;
9. if the delegate raises, capture that same exception object for diagnostics,
   record completion/notify in `finally`, and use a bare re-raise so
   `PreviewRuntime._publish()` receives the original object and retains its
   existing catch/log behavior;
10. only after the delegate returns or raises, append that exact delivered state
    as completed and notify the local condition;
11. admit success only when a completed delivered state satisfies `predicate`
    **and equals the current `runtime.snapshot()`**; snapshot truth without a
    matching completed delivery is never sufficient;
12. keep the literal five-second safety bound and include detached fixture
    states, current snapshot, completed states, and captured callback errors in
    timeout diagnostics;
13. if the trigger itself raises, propagate its exact exception after the same
    owned-only cleanup;
14. in `finally`, reacquire `runtime._condition` and restore `delegate` by direct
    assignment only when `runtime._callback is observer`;
15. if Api, close, the delegate, or another owner replaced the callback during
    the wait, do not overwrite that newer callback;
16. restoration never calls the production setter, resets `_published`, wakes
    the worker, republishes state, or invokes either callback.

The equality requirement binds readiness to completion of the callback for the
currently visible state. An earlier matching delivery cannot admit a newer
matching snapshot whose callback is still running. Delegate-first completion is
load-bearing: Api's Companion/EVE reconciliation effects and callback error
observability must finish at the callback boundary before the wait can return.

Change `eve_on` to call trigger-driven mode so the observer is armed before
`runtime.set_eve(True, revision)`. Change the exact `[True]` companions branch in
`test_off_apply_refreshes_retained_geometry_without_eve_start` to arm before
`runtime.set_companions(True, 1)`. Those are the only call-site changes required
for the four disconnected waits. Existing no-trigger waits remain legacy only
while the fixture callback owns delivery.

The four old identities therefore retain the five-second safety bound but have
**zero expected disconnected timeout waits** after Stage A: three enter through
the trigger-driven `eve_on`, and the companions `[True]` row enters through its
explicit trigger. This is a structural expectation, not an elapsed-time claim.

The fixture API is serialized. A marked observer already present is a test
misuse, not permission to build a callback chain. Fixture teardown remains the
existing `runtime.shutdown(5)` over every opened rig; the helper adds no worker,
timer, or persistent subscriber.

### Preserved contracts and exact file scope

The change does not alter:

- `PreviewRuntime.set_state_callback()` or its sole-callback production model;
- Api's `_preview_runtime_changed()` bound-method identity, inputs, return, or
  effects;
- Companion `runtime_changed()` delivery;
- EVE runtime authorization/reconciliation;
- runtime state publication equality suppression;
- callback exception identity/logging in `_publish()`;
- any five-second safety bound, state predicate, native epoch, admission,
  cleanup, or final shutdown assertion.

`tests/test_preview_presentation.py` remains an unchanged consumer of the
trigger-driven `eve_on`. `tests/test_preview_geometry_publication.py` receives
only the exact companions `[True]` call-site conversion described above.
No permanent edit is needed in `wingman/preview/runtime.py`, `wingman/ui/api.py`,
`wingman/ui/fleetpresentation.py`, or any other Preview test.

### Qualification witnesses

Use temporary, uncommitted helper mutations or an in-memory runtime double.
Each probe must restore exact bytes/state before the next:

| Boundary | Temporary defect | Required witness |
|---|---|---|
| Old unsafe entry | start a target transition, let production capture the old callback, block that callback, then enter the old snapshot helper | runtime snapshot is active and the old helper returns while delegated effects are still absent; this proves why post-trigger arming is unsafe |
| Arm before trigger | use trigger-driven mode with the same barrier callback | observer is installed before the trigger; the old captured-callback state is unreachable |
| Blocked delegated callback | let the trigger make the snapshot active while the actual delegate remains barrier-held | waiter remains blocked until the delegate returns and matching completion is recorded |
| Missing delegation | omit `delegate(state)` | actual callback effect list remains empty and qualification fails even though snapshot is active |
| Premature completion | record/notify before calling a barrier-held delegate | waiter returns while delegate is held; blocked-callback witness fails |
| Exception identity | have the delegate raise one sentinel exception under a production-style catch | the exact same object reaches that catch; completion notifies and owned cleanup still occurs |
| Replacement during delegation | have the delegate install a legitimate replacement callback | candidate leaves the replacement installed; unconditional restoration fails |
| Sequential waits | execute two trigger waits against the same underlying callback | exact callback identity is restored after each and callback depth remains one |
| Concurrent waits | hold the first marked observer and attempt a second with a false target | second fails before its trigger runs; removing the marker check admits a second layer and fails qualification |
| Trigger already satisfied | begin trigger-driven mode with its predicate true | helper fails before wrapper installation or trigger invocation; it never fast-returns success |
| Trigger/callback cleanup | make trigger or delegate raise | `finally` restores only an observer it still owns and leaves no marked wrapper |
| Legacy ownership boundary | compare direct/composed `publish` delivery with an unchained replacement | direct/composed delivery completes under the fixture condition; the unchained old pattern reproduces the unsafe return and must use trigger-driven mode |

The exact four hosted identities must each invoke trigger-driven mode once in
focused qualification. Expected old disconnected timeout waits after the change
are exactly zero. A timeout that eventually finds the predicate true is not
acceptance evidence.

## 2. Bounded rolling timing oracle

### Existing cost and contract

`test_rolling_diagnostic_allows_legal_one_ms_per_second_drift_for_2101_prefixes`
constructs this deterministic trace:

```python
for second in range(2101):
    exchange = (float(second), float(second), 100000 + 1001 * second)
```

Every iteration prepares a real production diagnostic candidate, proves it is
detached, compares its retained vector and exact `lo`/`hi` interval with the
independent `diagnostic_oracle`, commits it, and requires at most 96 retained
records. Final assertions require exact `last_server_time_ms == 2202100` and a
clear inconsistency latch.

Production already prunes to the 95-second diagnostic window and therefore
retains at most 96 records on this one-second cadence. The test oracle instead
rescans every complete historical prefix. Its retention-membership checks are:

```text
2101 × 2102 ÷ 2 = 2,208,151
```

The current Windows testcase observation is `13.320s`. This motivates the
bounded test correction but is not a promised saving.

### Candidate expected window

Change only the rolling test body. Keep the constructed `exchanges` list and all
2,101 production candidate/commit transitions. Before calling the unchanged
oracle, derive the expected input independently:

```python
# The protocol retains request starts no older than 95 seconds. This trace has
# fixed one-second request-start cadence.
first_retained = max(0, second - 95)
expected = exchanges[first_retained:]
assert_candidate_matches_oracle(prepared, expected)
```

The independent bound comes from two explicit test premises:

1. the protocol rule is inclusive age `<= 95 seconds`;
2. this constructed trace has zero request duration and exactly one second
   between request starts.

It does not read `prepared.state.exchanges`, `_DIAGNOSTIC_WINDOW_MS`,
`_DIAGNOSTIC_CAPACITY`, a production cutoff, or any other production output to
choose expected inputs. The unchanged oracle then independently recomputes the
retained vector and exact intersection over that bounded expected prefix.

The exact oracle-membership work becomes:

```text
sum(min(prefix_length, 96), prefix_length=1..2101) = 197,136
```

Preserve all of these assertions on every transition:

- `prepared is not None`;
- exact ordered `(started_at, received_at, server_time_ms)` retained vector;
- exact `prepared.state.lo` and `prepared.state.hi`;
- `ctx._state is before` prior to commit;
- `_commit_diagnostic(prepared)` succeeds;
- accepted state retains at most 96 exchanges.

Preserve final exact server time and `not ctx._inconsistent`.

### Unchanged timing coverage

Do not change `diagnostic_oracle()`, `assert_candidate_matches_oracle()`,
`context()`, `candidate()`, production timing code, or any other timing test.
The complete `test_diagnostic_vectors`, exact binary-ratio boundaries,
request-start-versus-receipt test, discarded-candidate behavior, stale/foreign
commit identity, 191-record defensive capacity, slow-response behavior, and
order/contradiction cases remain as they are.

The rolling test is still a long recurrence and final-state contract. It is not
reduced to 96 transitions, sampled prefixes, a production self-comparison, or a
single final assertion.

### Mutation witnesses

All mutations target production temporarily and are restored exactly:

| Defect | Required permanent witness |
|---|---|
| Change inclusive pruning `<=` to `<` | exact 95-second boundary row and rolling vector reject premature pruning |
| Use old receipt instead of old request start | `test_retention_uses_old_request_start_not_old_receipt` fails |
| Remove pruning | rolling expected vector diverges at the first expired prefix, before defensive capacity masks it |
| Use a 94-second window | exact boundary and rolling vector reject premature removal |
| Use a 96-second window | exact boundary and rolling vector reject the extra retained record |
| Change the 95/96 edge or capacity interpretation | exact binary-ratio rows plus rolling `<= 96` and expected vector fail |
| Stop advancing `last_server_time_ms` | final exact `2202100` assertion fails |
| Latch inconsistency during legal recurrence | a candidate/commit transition or final `not ctx._inconsistent` fails |
| Confuse candidate and commit state | per-prefix detached identity or commit assertion fails |

A failure only at defensive overflow is insufficient for a pruning mutant when
an earlier exact vector mismatch should own the defect.

## 3. Focused screenshot walks

### Current eight complete walks

`shoot.SCREENS` contains 61 screens. Eight identities in
`tests/test_shoot_screens.py` currently traverse all 61 despite owning narrower
contracts:

| Exact identity | Windows observation | Current assertion owned |
|---|---:|---|
| `test_walk_records_setup_failure_as_failed_shot` | `0.874s` | Preview group and narrow setup failures are attempted and recorded |
| `test_walk_applies_and_clears_device_metrics_for_narrow_screen` | `2.257s` | complete inventory succeeds; every floor override is set before its clear |
| `test_walk_clears_device_metrics_even_when_narrow_screenshot_fails` | `0.783s` | failed Preview narrow capture records an error and clears/deactivates override |
| `test_walk_applies_device_metrics_before_narrow_setup_script` | `1.525s` | successful Preview narrow order is set → setup → screenshot → clear |
| `test_walk_narrow_setup_runs_inside_device_metrics_override_on_failure` | `0.578s` | failed Preview narrow setup/capture remains inside override and clears |
| `test_walk_failure_path_records_set_eval_attempt_clear_in_order` | `0.428s` | exact failure trace is set → setup → attempt → clear |
| `test_walk_failure_path_records_attempt_before_clear_not_only_clear` | `0.847s` | screenshot attempt exists after set and before clear |
| `test_walk_injects_fittings_fixture_before_stage_actions` | `1.615s` | every actual Fittings visit injects before stage actions and later stages reset |

Their current hosted sum is `8.907s`, observationally.

There are also exactly 27 already-focused one-screen walks. They remain
unchanged:

```text
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[None-settings-companions-populated]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[None-settings-fleet-sharing-history-narrow]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[prepare-settings-companions-populated]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[prepare-settings-fleet-sharing-history-narrow]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[entry-settings-companions-populated]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[entry-settings-fleet-sharing-history-narrow]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[stage-settings-companions-populated]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[stage-settings-fleet-sharing-history-narrow]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[verify-settings-companions-populated]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[verify-settings-fleet-sharing-history-narrow]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[capture-settings-companions-populated]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[capture-settings-fleet-sharing-history-narrow]
tests/test_new_screenshots.py::test_new_capture_cleanup_runs_after_any_failure[profiles-setup-import-prepare]
tests/test_new_screenshots.py::test_new_capture_cleanup_runs_after_any_failure[profiles-setup-import-stage]
tests/test_new_screenshots.py::test_new_capture_cleanup_runs_after_any_failure[profiles-setup-import-verify]
tests/test_new_screenshots.py::test_new_capture_cleanup_runs_after_any_failure[profiles-setup-import-capture]
tests/test_new_screenshots.py::test_new_capture_cleanup_runs_after_any_failure[settings-previews-crop-narrow-prepare]
tests/test_new_screenshots.py::test_new_capture_cleanup_runs_after_any_failure[settings-previews-crop-narrow-stage]
tests/test_new_screenshots.py::test_new_capture_cleanup_runs_after_any_failure[settings-previews-crop-narrow-verify]
tests/test_new_screenshots.py::test_new_capture_cleanup_runs_after_any_failure[settings-previews-crop-narrow-capture]
tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture[settings-wanderer-controls-narrow]
tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture[profiles-copy-scope]
tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture[fittings-copy-preflight-bottom-narrow]
tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails[fittings-copy-progress]
tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails[settings-previews-groups]
tests/test_shoot_screens.py::test_alerts_base_capture_walk_waits_then_frames_or_records_failure[False]
tests/test_shoot_screens.py::test_alerts_base_capture_walk_waits_then_frames_or_records_failure[True]
```

Current structural visits are `8 × 61 + 27 = 515`.

### Derived selector

Capture the production inventory as a tuple of existing `Screen` objects at
module import and add one test-local selector:

```text
_walk_screens(*keys) -> tuple of original Screen objects
```

It derives a key index from the captured production inventory, asserts inventory
keys are unique, looks up every requested key exactly, preserves caller order,
and returns those original objects. It does not copy screen fields or create a
second hand-maintained inventory. Missing, duplicate, or reordered selected keys
fail immediately.

Each focused test uses `monkeypatch` or a bounded `pytest.MonkeyPatch.context()`
to replace `shoot.SCREENS` only for one walk. Restoration occurs before the test
or shared fixture receipt is exposed. Production `screens_for_gate()` and
`walk()` remain unchanged.

### Exact full traversal

`test_walk_applies_and_clears_device_metrics_for_narrow_screen` remains the sole
complete walk. It must assert the visited shot keys equal this exact derived
production order, in addition to all existing floor assertions:

```text
uploader
settings-uploading
settings-uploading-recording
settings-uploading-integrations
settings-uploading-webhook
settings-companions
settings-companions-populated
settings-companions-detail-narrow
settings-companions-add
settings-companions-source-narrow
settings-characters
settings-characters-waiting
settings-characters-partial-cleanup
settings-characters-narrow
settings-bookmarks
settings-bookmarks-windows
settings-bookmarks-sigbar
settings-previews
settings-previews-middle
settings-previews-table
settings-previews-sticky-conflict
settings-previews-detail
settings-previews-copy
settings-previews-groups
settings-previews-narrow
settings-previews-crop-narrow
settings-wanderer
settings-wanderer-narrow
settings-wanderer-controls-narrow
settings-fleet
settings-fleet-characters-narrow
settings-fleet-sharing
settings-fleet-sharing-details
settings-fleet-sharing-history-narrow
settings-alerts
settings-alerts-advanced
settings-alerts-custom-narrow
settings-general
profiles
profiles-copy-scope
profiles-account-identity
profiles-backups
profiles-formations
profiles-formations-import
profiles-setup-share
profiles-setup-import
skills
fittings
fittings-unfiled
fittings-superseded
fittings-alliance
fittings-detail
fittings-metadata-narrow
fittings-narrow
fittings-copy-preflight
fittings-copy-preflight-bottom-narrow
fittings-copy-limit
fittings-copy-progress
fittings-copy-result
fittings-copy-result-bottom-narrow
dialog
```

This one identity retains complete screen reachability, ordinary/floor branch
crossing, all 14 current floor screens, override count parity, set-before-clear
ordering, all-shot success, and exact inventory order.

### Exact focused selectors and expected visits

| Existing identity | Selector / receipt | Exact expected visited list | Walk executions |
|---|---|---|---:|
| `test_walk_records_setup_failure_as_failed_shot` | derived explicit selector | `settings-previews-groups`, `settings-previews-narrow` | 1 |
| `test_walk_applies_and_clears_device_metrics_for_narrow_screen` | unmodified full inventory | exact 61-list above | 1 |
| `test_walk_clears_device_metrics_even_when_narrow_screenshot_fails` | shared failure receipt | `settings-previews-narrow` | shared |
| `test_walk_applies_device_metrics_before_narrow_setup_script` | derived explicit selector | `settings-previews-narrow` | 1 |
| `test_walk_narrow_setup_runs_inside_device_metrics_override_on_failure` | shared failure receipt | `settings-previews-narrow` | shared |
| `test_walk_failure_path_records_set_eval_attempt_clear_in_order` | shared failure receipt | `settings-previews-narrow` | shared |
| `test_walk_failure_path_records_attempt_before_clear_not_only_clear` | shared failure receipt | `settings-previews-narrow` | shared |
| `test_walk_injects_fittings_fixture_before_stage_actions` | all production screens whose `route == "fittings"` | exact 13-list below | 1 |

The Fittings expected order is:

```text
fittings
fittings-unfiled
fittings-superseded
fittings-alliance
fittings-detail
fittings-metadata-narrow
fittings-narrow
fittings-copy-preflight
fittings-copy-preflight-bottom-narrow
fittings-copy-limit
fittings-copy-progress
fittings-copy-result
fittings-copy-result-bottom-narrow
```

The Fittings test asserts both exact visits and 13 fixture injections. For each
stage after the first, the operations between that injection and the next still
contain the reset action. Injection remains before that stage's reset,
preparation, setup, verification, and capture.

### One immutable Preview failure receipt

The four failure-order identities exercise the same screen, same failing CDP,
same production branch, and overlapping operation assertions. Replace four
identical walks with one module-scoped, test-local receipt fixture. Its interface
is conceptually:

```text
PreviewFailureReceipt(
    shots: tuple of detached read-only shot records,
    operations: tuple of strings,
    override_active: bool,
)

module fixture preview_narrow_failure_walk(tmp_path_factory)
    -> PreviewFailureReceipt
```

The fixture:

1. uses `pytest.MonkeyPatch.context()` and the derived selector;
2. selects only `settings-previews-narrow`;
3. replaces sleep with the existing no-wait double;
4. runs the existing `_FailOnceCDP(fail_narrow_screenshot=True)` through the real
   production `shoot.walk()` once;
5. requires exact visited keys `("settings-previews-narrow",)`;
6. detaches shots, operations, and final override state into immutable values;
7. exits the monkeypatch context before returning the receipt;
8. retains no CDP, path, monkeypatch, mutable operation list, or production
   inventory replacement;
9. works when any one consumer is selected directly;
10. produces the same receipt regardless of consumer order.

The four existing IDs keep their current assertion ownership:

- failed shot exists and records an error;
- `clear` occurs and the override is inactive afterward;
- setup remains after set and before cleanup on failure;
- exact operation tuple is
  `("set:840x625", "eval:setup", "screenshot_attempt", "clear")`;
- screenshot attempt exists after set and before clear.

Sharing one immutable execution is not Stage B's persistent page-worker or real
saved-layout receipt work. It is a bounded pure-Python CDP-double receipt for
four assertions over one identical `walk()` branch.

### Visit arithmetic

The eight identities perform these candidate visits:

```text
full inventory       61
Preview setup errors  2
Preview success order 1
shared failure order  1
all Fittings          13
                      --
Stage A eight total   78
```

All 27 existing focused walks remain one visit each:

```text
78 + 27 = 105 visits
```

The eight identities remain eight identities, but the four failure consumers
share one module-scoped walk. Under the lifetime-safe structural order defined
below, the 35-identity set therefore executes 32 walks. No identity, parameter,
marker, or assertion contract is deleted.

### Receipt lifetime and structural qualification

The immutable receipt is module-scoped, not session-scoped. Its singleton claim
is valid only while the relevant `tests/test_shoot_screens.py` IDs remain one
contiguous module-lifetime block. The 35 identities divide exactly as follows:

```text
tests/test_shoot_screens.py target block  15 identities, 12 walks,  85 visits
tests/test_new_screenshots.py block         8 identities,  8 walks,   8 visits
tests/test_current_screenshots.py block    12 identities, 12 walks,  12 visits
                                           --             --        ---
                                           35             32        105
```

The 15-ID first block is the eight changed identities plus the seven already
focused identities in `tests/test_shoot_screens.py`. Its five changed-shape walks
visit 78 screens, and its seven focused walks visit seven more. The module
fixture is constructed exactly once in that contiguous block.

Run three instrumented structural orders. In each, keep all 15
`tests/test_shoot_screens.py` target IDs contiguous and vary order **only inside
that block**: collected order, reverse order, and deterministic seed-`20260926`
shuffle. Keep the eight `test_new_screenshots.py` IDs contiguous and the twelve
`test_current_screenshots.py` IDs contiguous in their collected orders. For each
of these three lifetime-safe commands require exactly:

- 35 unique expected identities and all passing outcomes;
- one `preview_narrow_failure_walk` fixture construction;
- 32 real `shoot.walk()` executions;
- 105 visited screens with the exact per-walk lists above.

Also run one deliberately mixed/interleaved cross-module order over the same 35
identities. That run owns only identity-set and outcome assertions. Pytest may
tear down `test_shoot_screens.py` when execution leaves its module and construct
the module fixture again if execution later re-enters it. Therefore no singleton
construction, walk-count, or visit-count invariant is asserted for arbitrary
cross-module interleavings. Direct selection in separate pytest invocations may
likewise construct one receipt per invocation. Session scope is not authorized:
the bounded module receipt already gives isolation and cleanup without extending
a monkeypatch-derived artifact across module environments.

### Preserved walk contracts and mutation witnesses

The focused set must still kill these temporary production mutations at the
intended assertion:

| Contract | Temporary defect | Witness |
|---|---|---|
| Complete inventory | omit or reorder one `screens_for_gate(True)` result | sole 61-screen traversal's exact visited list |
| Floor traversal | omit an override/clear or reverse one pair | full traversal's 14-floor counts and pair ordering |
| Both Preview setup failures | stop attempting either group or narrow setup | exact two-shot setup-failure identity |
| Metrics before setup | omit or move the narrow override after setup | success-order identity and shared failure receipt cannot locate set → setup |
| Verification before capture | move verifier after screenshot | existing focused `test_walk_refuses_capture_when_postcondition_fails` records a capture and fails |
| Attempt before clear | omit/move screenshot attempt | exact shared failure tuple and attempt-order identity fail |
| Clear after failure | remove/move final clear | shared receipt remains active or lacks final clear |
| Cleanup after failure | omit `new_screen_cleanup_script()` | unchanged new/current focused cleanup matrices fail |
| Fittings injection order | move fixture injection after reset/stage action | 13-screen Fittings identity fails its inter-injection order |
| Fittings completeness | omit one route-owned screen | exact 13-list/injection count fails |

A mutation that fails only because another unselected screen happened to run is
not accepted; this is the reason every expected visited list is exact.

Run the three lifetime-safe structural orders and the separate mixed/interleaved
outcome order exactly as defined above. No retry-to-green, process restart, or
order-specific skip is accepted. Never report one-construction/32-walk/105-visit
counts from a cross-module interleaving that may cross the module fixture's
teardown boundary.

## Disposable design qualification

No repository implementation was made while preparing or hardening this design.
A disposable archive whose executable source is `463bccb0` was created under
`/tmp/wingman-stage-a-overlay` and received only disposable candidate edits. The
source worktree remained documentation-only.

The hardened qualification established:

- the seven relevant modules collect 494 unique identities before and after;
  the ordered lists are byte-for-text equal with zero additions/removals;
- all 494 relevant tests passed together in the disposable candidate;
- `test_preview_runtime_review.py` passed 20 tests and the Preview
  presentation/geometry selection passed 32 tests;
- all 388 tests in the complete set of modules that consume `runtime_pump`—runtime
  review, runtime boundaries, layout batch, layout admission, polish fixes,
  presentation, geometry publication, and wiring—passed with the two-mode
  contract; this includes every importer of the changed `eve_on` helper;
- focused instrumentation recorded exactly the four named post-Api identities
  entering trigger-driven mode once each, so expected old disconnected timeout
  waits are structurally zero while the five-second bound remains;
- an independent observer probe reproduced the old unsafe return after a target
  callback was already captured/running, then proved the trigger-driven waiter
  remained blocked with an active snapshot until its delegated callback
  returned;
- the observer probe also passed missing-delegation effects, exact exception
  identity through a production-style catch, legitimate callback replacement,
  owned-only restoration, two sequential waits, and concurrent-wrapper
  rejection; missing-delegation, premature-completion, unconditional-restore,
  and wrapper-accumulation mutations all failed that probe;
- the rolling case executed exactly 2,101 candidates and 2,101 commits while
  counting exactly 197,136 oracle membership checks; the current formula is
  exactly 2,208,151;
- the complete 41-test timing file passed; pruning-edge,
  receipt-versus-request, no-pruning, 96-second-window, and last-server mutations
  all failed retained timing identities;
- the eight changed screenshot IDs passed with the candidate shape;
- each lifetime-safe structural order—normal, reverse, and seed-`20260926`
  shuffle within the contiguous 15-ID `test_shoot_screens.py` block—passed all
  35 identities and recorded exactly one receipt construction, 32 walk
  executions, and 105 visits;
- one deliberately interleaved cross-module order passed all 35 identities; no
  construction/walk/visit count was asserted for that order;
- metrics-before-setup omission, verification-after-capture,
  capture-attempt omission, cleanup omission, and Fittings injection-after-action
  mutations all failed their intended retained identities;
- focused Ruff check and format-check passed for the four disposable candidate
  test files;
- every temporary production mutation was restored byte-for-byte in a `finally`
  path.

The local durations from this disposable Linux/WSL exercise are diagnostic only.
They support neither a local nor hosted speedup claim and are not acceptance
thresholds.

## TDD and implementation sequence

Implementation follows test-first structural gates without adding permanent test
identities.

### Preview

1. Freeze the exact four hosted identities and current callback identities.
2. Reproduce the old unsafe case where the target callback is already
   captured/running and snapshot truth returns before callback completion.
3. Add trigger-driven arming and require the blocked-callback witness to remain
   blocked even while the runtime snapshot is active.
4. Separate documented direct/composed fixture-owned snapshot mode from
   trigger-driven mode; add the trigger precondition and marked-wrapper
   assertions without guessing callback identity through legitimate composites.
5. Convert `eve_on` and only the exact companions `[True]` call to arm before
   their triggers.
6. Instrument the exact four identities: four trigger-driven calls and zero old
   disconnected timeout waits are required structurally.
7. Run the complete runtime-review/presentation/geometry selection and every
   observer guard mutation with exact restoration.

### Timing

1. Instrument only oracle input lengths; the current rolling case must report
   2,208,151 checks while still passing.
2. Add a temporary structural assertion requiring 197,136; observe RED on the
   current full-prefix shape.
3. derive the bounded expected prefix from literal 95-second protocol semantics
   and fixed one-second cadence.
4. require exactly 2,101 candidate and commit calls, exact final state, and
   197,136 oracle checks.
5. run the full timing file and every mutation witness.

### Screenshots

1. Instrument production `walk()` calls without replacing them; current selected
   identities must report 515 visits.
2. Add the derived selector and exact expected-list assertions.
3. Introduce the one immutable module-scoped Preview failure receipt.
4. Keep the 15 `test_shoot_screens.py` target IDs contiguous and run their normal,
   reverse, and deterministic shuffle orders; each full structural command must
   report one receipt construction, 32 walks, and 105 visits.
5. Run a separate mixed/interleaved 35-ID command for identity/outcome evidence
   only; do not assert lifecycle-dependent counts across module re-entry.
6. Apply each walk mutation separately and restore production source exactly.

Temporary counters, plugins, mutation scripts, receipt debug output, and generated
JUnit/timing evidence remain outside the tracked tree and are removed or retained
only in ignored local evidence space.

## Verification and acceptance

### Focused local verification

The implementation results must record:

1. exact four Preview hotspot IDs, then complete runtime review, runtime
   boundaries, layout batch, layout admission, polish fixes, presentation,
   geometry publication, and wiring files—the full set that consumes
   `runtime_pump` and includes every changed-`eve_on` importer;
2. exact rolling timing ID, then complete `test_fleetsharing_timing.py`;
3. exact eight screenshot IDs;
4. exact 35 screenshot walk IDs, including all 27 unchanged focused identities;
5. three lifetime-safe commands that vary order only within the contiguous 15-ID
   `test_shoot_screens.py` block and prove one receipt construction, 32 walks,
   and 105 visits;
6. one mixed/interleaved cross-module 35-ID command that asserts only exact
   identities and passing outcomes, never lifecycle-dependent counts;
7. complete `test_shoot_screens.py`, `test_new_screenshots.py`, and
   `test_current_screenshots.py`;
8. relevant Preview runtime, Api/presentation, Fleet timing, screenshot worker,
   protocol, isolation, and lifecycle files;
9. exact structural counters and all temporary mutation witnesses.

### Complete local verification

With Node on `PATH` and the release settings codec built and installed in
`packaging/bin`, run and record:

- `uv sync --locked --extra dev`;
- codec release build and `codec.codec_available()` assertion;
- `uv run --no-sync python -m pytest tests/ -q -rs --durations=50
  --junitxml=/tmp/stage-a-full.xml`;
- exact `16,595 passed + 14 skipped = 16,609` local outcomes;
- exact ordered complete identity hash
  `f468ba1954d3ff0ab693dd721ff8a7a4d12266e16d8568035de4245a6c616100`;
- exact ordered normalized 14-skip equality;
- `node scripts/js_smoke.js`;
- applicable executable screenshot DOM/worker tests;
- `cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml`;
- `uv run --extra dev ruff check .`;
- `uv run --extra dev ruff format --check .`;
- `uv run --no-sync python -m pytest tests/test_documentation.py -q`;
- `git diff --check` and exact changed-path/protected-path audits.

No Node, settings-codec, or unexpected native-availability skip is acceptable.

### Hosted verification

Compare one successful candidate run directly with run `36208309831` and its
pinned artifacts. Record:

- branch head, synthetic merge, base, workflow run/attempt, all required job IDs,
  and exact checkout-log provenance;
- artifact IDs/digests and ZIP-member/extracted-file equality;
- exact 16,609 ordered Windows and Ubuntu identities and frozen hash;
- exact `+0/-0` identity diff globally and for every targeted file;
- Ubuntu 16,595 passed/14 skipped and Windows 16,542 passed/67 skipped;
- exact normalized platform skip-array equality and hashes;
- no failure, error, Node skip, codec skip, or unexpected native skip;
- exact four Preview IDs, one rolling ID, eight complete-walk IDs, and 27 focused
  walk IDs;
- targeted testcase sums, complete testcase sums, Test-step and job observations;
- proof that production, workflows, dependencies, configuration, cadence,
  markers, workflow test selectors, shards, timeout values, and packaging did
  not change.

One hosted run may establish contract preservation and disclose observations. It
may not establish speedup, slowdown, a lower bound, runner efficiency, p95, or a
critical-path effect. No repeat run is required solely to manufacture a favorable
elapsed result.

## Data lifecycle

- The Preview observer exists only around one trigger-driven `wait_state` call.
  It temporarily holds the exact callback object, completed immutable runtime
  states, and exact exception objects for diagnostics; it persists none of them
  and restores only its own slot. Runtime and native teardown remain fixture
  owned.
- The rolling timing test retains its existing in-memory 2,101 constructed
  exchanges. The expected slice is bounded for oracle work only; production
  state and all commits remain real. Nothing is persisted.
- Focused screenshot walks continue writing only to each pytest temporary
  directory. The shared failure receipt contains detached immutable shot/trace
  values and no live CDP, monkeypatch, file handle, or production inventory
  replacement. Its temporary directory is pytest-owned.
- No generated XML, JSON, mutation script, timing artifact, or overlay enters the
  commit.

## Failure behavior and observability

- Preview readiness remains fail-closed after five seconds with the unchanged
  final predicate and stronger callback/current-state diagnostics. Callback
  exceptions retain production logging and exact identity.
- Timing mismatches fail on the first wrong retained vector, interval, detached
  state, commit, capacity, final server time, or inconsistency assertion.
- Screenshot selection fails immediately on missing/duplicate keys. Every walk
  still records per-screen setup, verification, capture, and cleanup errors
  through production `walk()`.
- Structural counters are qualification evidence only. No permanent logging,
  metric, JUnit property, workflow summary, timeout, or budget is added.

## Security and compatibility

Stage A changes no authentication, network, filesystem trust boundary, native
binding, package, production serialization, signing, credential, or secret
handling. The Preview observer never logs callback payloads or accesses user
state. Screenshot data remains the existing synthetic test fixtures.

Compatibility is defined by exact identity/order/outcome preservation. Existing
focused selectors, direct pytest node selection, file-level execution, JUnit
names, platform skips, and required check names remain unchanged. The shared
module fixture must work when any one of its four consumers is selected directly
and while the 15 `test_shoot_screens.py` target IDs run contiguously in
normal/reverse/shuffled order. Arbitrary cross-module interleaving retains
outcomes and identities but owns no singleton/count guarantee across module
teardown/re-entry.

## Alternatives rejected

### Change production Preview callback semantics

Rejected. A subscriber list or callback multiplexer would broaden production
lifecycle and ownership for a test-fixture defect. Stage A observes and delegates
the current actual callback locally.

### Shorten the Preview timeout, poll, pre-signal, or arm after triggering

Rejected. A shorter bound hides the disconnected observer and weakens deadlock
protection. Polling adds scheduling noise. Pre-signalling or snapshot truth can
pass before Api callback effects. Arming after the trigger cannot intercept a
callback already captured by `_publish()`. Trigger-driven mode arms atomically
first, rejects an already-true target, and keeps the five-second bound and final
predicate exact.

### Use `set_state_callback()` to install/restore the observer

Rejected. It resets `_published`, wakes an owner, and can replay callback effects.
Direct test-local replacement under the runtime condition preserves delivery and
identity semantics.

### Compare timing against production's retained state

Rejected. Reading candidate length/cutoff to choose the expected window makes the
test self-fulfilling. The expected bound comes only from explicit 95-second rules
and fixed one-second test cadence.

### Reduce the rolling trace to 96 transitions

Rejected. It would lose long recurrence, every candidate/commit transition, and
exact final server-state coverage.

### Add a production screenshot selector argument

Rejected. `walk()` is shipped tooling and already has a test-local inventory seam.
Monkeypatching derived original `Screen` objects scopes the optimization without
changing production API or behavior.

### Run seven independent focused replacements

Rejected. Four failure IDs assert overlapping facts about one exact walk trace.
Independent one-screen reruns would yield 108 visits, not the approved 105, and
would retain deterministic duplicate work. One immutable receipt preserves all
four assertions and direct selection.

### Delete duplicate screenshot identities now

Rejected. Identity deletion belongs to Stage C and requires mapped
mutation-qualified consolidation. Stage A preserves every identity.

### Fold Stage B or Stage C into this tranche

Rejected. Persistent page ownership and broad test deletion have different
isolation, failure, and review risks. This design fixes only their boundaries and
precommits no implementation details.

## Risks and mitigations

### Observer restoration overwrites a newer callback

Mitigation: restore only when the callback slot is still the exact observer.
Qualify a delegate that installs a replacement.

### Observer notification races ahead of Api effects

Mitigation: delegate first and notify only in `finally` after return/raise.
Qualify with a barrier-held callback.

### Callback replay changes behavior

Mitigation: do not reset `_published`, wake, or call the production setter during
installation/restoration. A trigger-driven predicate that is already true fails
before observer installation or trigger invocation; it is never accepted as a
readiness fast path.

### Expected timing window accidentally copies production

Mitigation: use the literal protocol age and constructed cadence; forbid reads of
candidate state or production constants when selecting expected exchanges.

### Bounded oracle misses an old-record pruning defect

Mitigation: compare the production retained vector with the independently sliced
expected vector on every prefix. No-pruning and 95/96 edge mutations must fail at
the first mismatch.

### Shared screenshot receipt becomes order-dependent

Mitigation: module-scoped immutable detached receipt, bounded monkeypatch context,
no yielded live state, direct-selection checks, and three structural runs that
keep the 15 file-local IDs contiguous. Mixed cross-module order owns only
identity/outcome evidence because module teardown/re-entry may reconstruct the
receipt.

### Focused screens hide full-inventory behavior

Mitigation: retain one complete 61-screen traversal and exact derived order, all
14 floor screens, both Preview setup failures, all 13 Fittings screens, and all
27 existing focused walks.

### Timing observations are overinterpreted

Mitigation: publish structural transitions/checks/visits and identity evidence as
acceptance. Label all local and hosted elapsed values as single-run observations.

## Stopping rules

Stop implementation and return to design review if any of these occurs:

1. the Preview wait requires a production callback/subscriber change;
2. readiness requires shortening five seconds, polling, sleeping, pre-signalling,
   or weakening a final predicate;
3. trigger-driven mode cannot arm before its transition, or can return from
   snapshot truth without a matching completed delivery through the captured
   callback;
4. the helper cannot delegate the exact current callback once and preserve its
   effects, return/exception identity, and production logging;
5. a callback replacement can be overwritten by cleanup, sequential waits
   accumulate wrappers, or a concurrent wrapper reaches its trigger;
6. any target Preview identity needs a source edit outside
   `tests/test_preview_runtime_review.py` and the exact companions call in
   `tests/test_preview_geometry_publication.py`;
7. the rolling test cannot execute exactly 2,101 candidates and 2,101 commits;
8. independent oracle work is not exactly 197,136 checks or depends on production
   candidate output;
9. `diagnostic_oracle()` or another timing test must change;
10. any pruning, request-start, 95/96, commit, final-server, or inconsistency
    mutant survives its intended witness;
11. screenshot visits are not exactly 515 before and 105 after in the defined
    lifetime-safe structural commands;
12. any cross-module interleaving is reported as proving singleton construction,
    32 walks, or 105 visits across a module teardown/re-entry boundary;
13. the eight full-walk IDs, 27 focused IDs, their parameters, markers, or
    assertion contracts change;
14. the sole complete traversal is not exactly all 61 screens and all 14 floor
    screens in production order;
15. either Preview setup-failure screen, successful order, exact failure order,
    or any of 13 Fittings screens is omitted;
16. the shared receipt retains live/mutable state, leaks a monkeypatch, or changes
    while the 15 file-local target IDs remain contiguous;
17. metrics-before-setup, verification-before-capture, attempt-before-clear,
    cleanup-after-failure, or Fittings injection-order mutations survive;
18. complete collection differs from exact ordered 16,609 or platform identities
    diverge;
19. normalized skip tuples change or Node/codec availability skips appear;
20. any production, workflow, dependency, configuration, cadence, marker,
    workflow test selector, budget, shard, timeout, packaging, or unrelated test
    change appears necessary;
21. temporary mutation/instrumentation cannot restore exact bytes, binary diff,
    and status;
22. evidence supports only an elapsed-time claim and cannot reproduce the exact
    callback, transition/check, and visit contracts.

## Exact implementation scope

The complete future Stage A tranche may commit only:

- this design;
- a future reviewed Stage A implementation plan under `docs/superpowers/plans/`;
- a future Stage A results document under `docs/`;
- `tests/test_preview_runtime_review.py`;
- `tests/test_preview_geometry_publication.py` (only the exact companions
  trigger call);
- `tests/test_fleetsharing_timing.py`;
- `tests/test_shoot_screens.py`.

`tests/test_preview_presentation.py` is an unchanged verification consumer.
`tests/test_new_screenshots.py` and `tests/test_current_screenshots.py` are
unchanged focused-walk verification consumers. No other permanent presentation
or geometry test edit is necessary.

Explicitly forbidden without a new design review:

- any file under `wingman/`;
- `scripts/shoot_screens.py` or any Node/CJS fixture;
- any test file beyond the four authorized Stage A files;
- `.github/`, dependencies, `pyproject.toml`, `uv.lock`, packaging, pytest
  configuration, markers, workflow test selectors, budgets, shard manifests, or
  timeout values;
- test deletion, addition, rename, reorder, signature-driven identity change,
  parameter/ID change, or cadence change;
- persistent workers, saved-layout receipt bundling, or broad consolidation;
- generated evidence, permanent benchmark/mutation tooling, debug output, or
  placeholders.

## Required implementation self-review

Before publication, the results document must explicitly confirm:

- **Scope:** only the approved spec/plan/results and four authorized test files
  changed; the geometry file contains only the exact companions trigger call and
  all protected paths are unchanged.
- **Identity:** exact 16,609 order/hash, exact targeted file orders, `+0/-0`, and
  unchanged parameters/markers.
- **Preview observer:** atomic arm-before-trigger, false-target precondition,
  actual callback capture, delegate-first matching completion, exact return and
  exception identity, no replay/wake, marked no-accumulation, concurrent
  rejection before trigger, owned-only restoration, and unchanged five-second
  safety bound/current-state predicate.
- **Preview structure:** the old captured/running-callback unsafe return is
  reproduced; exactly the four named disconnected waits enter trigger-driven
  mode; expected old timeout waits are zero; the hosted `20.275s` observation is
  reported without a saving claim.
- **Timing:** all 2,101 candidates/commits, independent literal 95-second bound,
  197,136 oracle checks, exact vectors/intervals, `<= 96`, final `2202100`, and
  clear inconsistency latch.
- **Screenshots:** exact eight IDs, exact selectors/lists, one 61-screen/14-floor
  traversal, two Preview setup failures, one success order, one module-scoped
  immutable failure receipt, all 13 Fittings screens, and all 27 focused walks;
  each lifetime-safe contiguous-file order proves one construction/32 walks/105
  visits, while mixed cross-module order proves identities/outcomes only.
- **Mutations:** every observer, timing, and walk mutant fails at its intended
  assertion; no timeout/later failure is misreported; every edit is restored.
- **Order:** Preview waits are trigger-armed; the 15 contiguous file-local
  screenshot IDs are green under required normal/reverse/deterministic-shuffle
  orders; the mixed cross-module order is green without a count claim or retry.
- **Prerequisites/gates:** Node, release codec, full pytest, exact skips, JS smoke,
  Cargo, Ruff check/format, documentation tests, and diff/scope audits are fresh.
- **Claims:** `646.538s`, `680s`, `42.502s`, and all candidate timings are labeled
  observations; no speedup, lower bound, p95, job, or critical-path claim appears.
- **Leftovers:** no overlay, generated artifact, mutation, counter, debug output,
  mutable shared receipt, unfinished placeholder marker, or Stage B/C
  implementation remains.

## Follow-up boundary

Successful Stage A implementation proves only that these same identities can
avoid disconnected waits, unbounded test-oracle history, and unrelated screenshot
walks while preserving their contracts. It does not authorize Stage B persistent
page workers or a saved-layout receipt bundle. It does not authorize any Stage C
test deletion/consolidation, including any of the roughly 346 discovery
candidates. Each later stage requires its own evidence-based design, plan,
mutation qualification, scope, and hosted decision.
