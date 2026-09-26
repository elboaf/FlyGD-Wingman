# Broad CI waste reduction — Stage A results

This ledger is cumulative. Task 1 freezes the merged PR #290 baseline, Task 2
records the Preview observer, Task 3 records the bounded timing oracle and focused
screenshot walks, and Task 4 records the complete local endpoint. Candidate hosted
fields remain unfilled. Elapsed values below are observations only; none is a
speedup, lower bound, p95, throughput, job, or critical-path claim.

## Authority and exact source identities

The source baseline is merged `main`
`463bccb07077325e64b6ad7f7ce4e9c100d2fcd6` (`Stop Fleet source bootstrap at
accepted readiness (#290)`). Task 1 began on branch
`ci-broad-waste-stage-a` at documentation-only head
`39757fda` with `origin/main` and the merge base both at the exact source
baseline. `git merge-base --is-ancestor` succeeded. Before this ledger, the only
paths in `origin/main...HEAD` were the authorized Stage A design and plan; the
production, test, workflow, packaging, and configuration trees had no diff.

A `pytest_collection_finish` plugin wrote every `item.nodeid` and its sorted
marker names. Each invocation below was independently collected from the current
source; every count, uniqueness check, order, and final-newline SHA-256 matched
the frozen ledger.

| Selection | Count | Ordered final-newline SHA-256 |
|---|---:|---|
| Complete `tests/` | `16,609` | `f468ba1954d3ff0ab693dd721ff8a7a4d12266e16d8568035de4245a6c616100` |
| Five in-scope test files | `313` | `a21d48abcdfaeb9b2b33ab5e1b089f5da4e692f01bebe94c104908728235eaef` |
| Relevant seven-file selection | `494` | `ad677b5f7f9b2667401ccfc39295de021c8a320498d59a3679b05497491b229e` |
| Eight `runtime_pump` consumer files | `388` | `36e61c70b9d081f2302bd2928f2b83e2c8d6e9032fe2c9fa8dd0c2eeee0d784f` |
| `test_preview_runtime_review.py` | `20` | `dfb34888c52b3db0c6b70b35ae033b7a45e9a77c75e6e29448d86a43ef50691e` |
| `test_preview_presentation.py` | `15` | `582d30ccfa1102d8128fe9e365abccfa9bd2181be752096e576c6a3fe4701df2` |
| `test_preview_geometry_publication.py` | `17` | `95840e2f840134c3ac38e7c055c69f4fdff72724e81500780c49ddc7959ae76f` |
| `test_fleetsharing_timing.py` | `41` | `f4fe35e78a92078c923fd894382c38924501fe6d1f3a4e56a8f8839c0382e37a` |
| `test_shoot_screens.py` | `220` | `156563ca03eb0f29c887f26e6aea18e393d54e7793a6a0a5fe557250cc406e81` |
| `test_new_screenshots.py` | `90` | `c885cb48a3fbc03547291ff302a079cff2d5ebe42c7faeb5c4ec0a5e40a2938d` |
| `test_current_screenshots.py` | `91` | `c0a709d70a349ef901ec28a86be422bcf17dddb2c6cc75beec3c39544010ef8b` |
| Preview four | `4` | `97886a5121cd3ecb1be6c2f3b9b6c4d423274dadd9f9fbb055006fd7c773b2eb` |
| Rolling timing one | `1` | `7315dfab22e06d84f2c7b818e2ceb488e4c5667f13b2e8e50f37e3abb39b915e` |
| Changed screenshot eight | `8` | `d42ecdf5d0c82bdd29e86f43c9553eefee50dfdd8fceee1e65430dad589c9774` |
| Contiguous `test_shoot_screens.py` fifteen | `15` | `628e82704990f6186c5d1b2d213308d99cf9f77a9ac42925c7404f213ca476c5` |
| Unchanged new-screenshot eight | `8` | `cd7c178e1482a5e04aa5bc3727d15e72f7fc3a91866d18c423dd54f4ab5eda99` |
| Unchanged current-screenshot twelve | `12` | `b1f7e96d4322dd13a9d2023635a02881fdc9edee7955eb4717f98ff879517cac` |
| Normal screenshot thirty-five | `35` | `75e7172a2c9685582b2e4adbc15decd71bc2ebb978f65b84acf9f738c2546786` |
| Reverse-in-fifteen screenshot thirty-five | `35` | `dfef25628da7c26bd98db8f4fc5862bd5dc2c7c73888b92197fd1279bf8c4ef1` |
| Seed-`20260926`-shuffle-in-fifteen screenshot thirty-five | `35` | `04a1f9125d3bbbb0dbef9eed72916b8a11db8d0b6cbc08782f084f50d6a5e59f` |

The complete source collection is byte-for-order equal to both retained platform
JUnit arrays. The three 35-ID order variants deliberately vary only the
contiguous 15-ID `test_shoot_screens.py` block; the new-eight and current-twelve
blocks retain collected order.

The read-only production/helper baseline hashes were recomputed locally:

| Protected path | SHA-256 |
|---|---|
| `wingman/preview/runtime.py` | `adde9c49b469fbffe7816c746da7078fbfcc88aada9412ad318193c3072101c0` |
| `wingman/ui/api.py` | `730298e68701348ce175d4db3fd75ac95c343b939d07052e0ea3d772a17615ce` |
| `wingman/ui/fleetpresentation.py` | `db714251d8744ecdb0862414126baf2aa887578af4f7c6919520e32e00246613` |
| `wingman/fleetsharing/timing.py` | `0b09ec89d47b803089015a6e21f80604219ec1b619909ca400e5e7e7d9520901` |
| `scripts/shoot_screens.py` | `05e03a76374d16719568eb92b461ef1b50a7e5ff35ef2cd3944b97aa3d4453b4` |
| `tests/test_new_screenshots.py` | `ffb2024c3931ab599c3e33cb9a1bbc4188224392fc1caadf58e989c58b29e157` |
| `tests/test_current_screenshots.py` | `1a6dabb9d2e6f8360268eab5045334d25c4ad09048ca99bfc166d80edf6bb021` |
| `tests/preview_runtime_helpers.py` | `18c39a550a941d8fdb06af6d0764e31e19fd01fe9616ecf3785ebdf158d33b3a` |
| `tests/test_preview_layout_batch.py` | `2ff792554c2aff31664854ab9aa68968be8aa4b1e4842ec4ae670893015e4285` |
| `.github/workflows/ci.yml` | `9524b760b9f74c09b39c7d096cf1e1494b16e6607e8a5c7422d97e9ee4811222` |
| `pyproject.toml` | `33620c99049ad82b1366b2c63cf9957ebb9ea928e08445b9ea8fefd28c789412` |
| `uv.lock` | `ebf5e1a5e892dd6488385d117c64a14dd0b0575ef9dbc4565b07a3012f9ad499` |
| `packaging/settings-codec/Cargo.toml` | `c6668b09f3fd3aaff0af1ca3a7dbaa77a40d7c349b06c2f42038134e094fa101` |

## PR #290 provenance and retained artifacts

The retained files under
`/mnt/c/dev/flygd-wingman/tmp/next-hotspot-36208309831` belong to PR #290,
workflow run `36208309831`, attempt `1`. The already accepted PR #290
logs-primary provenance records executable head
`3523dd0873493c8ecac0599b7c2daaf4d44d5902`, synthetic merge
`26428a687ad24f99cb21f8ff9f18628023c71799`, and base
`f6e8ecd5b09889e79aa169ce103b2eb9681cec9f`; the synthetic parents are base then
head. Task 1 did not query or mutate the remote and did not rerun a workflow.

| Role | Job ID | Conclusion | Job observation | `Test` step observation |
|---|---:|---|---:|---:|
| Checks | `108309461453` | `success` | `9s` | n/a |
| Ubuntu | `108309461358` | `success` | `307s` | `287s` |
| Windows | `108309461427` | `success` | `741s` | `680s` |

| Platform | Artifact ID | ZIP SHA-256 | JUnit XML SHA-256 | Timing JSON SHA-256 |
|---|---:|---|---|---|
| Ubuntu | `10894627359` | `3670232e32405fd1342e45eef655c7640f8650d5e52dacc29383715196faa15e` | `44474a56fc90e93d267df3f11318d12acf0a4515bc71e0c9db2f02bfcd0d8d1b` | `bd208ba1e6a502b553e0f00e7e8914fb925073a21b3329a26d96af447d46d4f7` |
| Windows | `10894793997` | `f7afad089e74456e76e1b3133a0a55c8d5f296c5a557af16b1009e80c6f6300f` | `1b993ea2dcf7245fceec7fb7213d4212d6a77f94925cc4c7274eaf3d0a62acdb` | `cde109559e59aa89cc9ddba2dff0c8c796aad77735defd1c7fd62614b9d88c12` |

`sha256sum` reproduced all six values. Each ZIP's member list is exactly
`pytest-result.xml` and `pytest-timing.json`; the Ubuntu members are
`2,492,737` and `38,440` bytes, and the Windows members are `2,504,983` and
`39,445` bytes. Every extracted file is byte-for-byte equal to its corresponding
ZIP member. The retained evidence directory was read only.

## Exact platform outcomes and normalized skips

The plan's longest-existing-module-prefix JUnit parser was materialized as
`/tmp/stage_a_identity.py`, compiled, Ruff-checked, and Ruff-format-checked.
It found no duplicate or unmapped identity. Both complete ordered arrays equal
the fresh source collection exactly.

| Platform | Passed | Skipped | Failures | Errors | Total | Testcase sum | XML suite time | `Test` step | Job |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Ubuntu | `16,595` | `14` | `0` | `0` | `16,609` | `268.312s` | `285.254s` | `287s` | `307s` |
| Windows | `16,542` | `67` | `0` | `0` | `16,609` | `646.538s` | `675.274s` | `680s` | `741s` |

Timing JSON `case_count` is exactly `16,609` on each platform. Every per-file
case count and duration sum equals its JUnit source within `1e-9`; each timing
JSON `total_seconds` equals the complete testcase sum within `1e-9`. In
particular, Windows `646.538s` testcase sum, `675.274s` XML suite time, `680s`
Test-step observation, and `741s` job observation remain distinct measures.

The normalized ordered skip arrays are reproduced literally in Appendices B and
C. Their exact serialization is `(json.dumps(pairs, indent=2) + "\n").encode("utf-8")`.
The resulting hashes are Ubuntu
`14f1511f840fb2fdc1680123dde29a7143405829af97141d62c5099aa4f265af`
and Windows
`41a767f45f49215310104dc611a4e9b60e4cb251e90f850b80a6f3b1cd9bcfb6`.
No Stage A target is skipped. Exact-array equality confirms there is no Node,
settings-codec, or unexpected native-availability skip.

## Preview baseline and observer evidence

The retained Windows artifact records the four disconnected Preview readiness
observations exactly:

| Identity | Windows testcase observation |
|---|---:|
| `tests/test_preview_presentation.py::test_main_adapters_never_present_on_pump_and_coalesce_while_page_blocked` | `5.150s` |
| `tests/test_preview_presentation.py::test_identified_capture_through_main_while_old_delivery_is_blocked` | `5.009s` |
| `tests/test_preview_geometry_publication.py::test_retained_drag_and_commit_notify_distinct_authorities` | `5.057s` |
| `tests/test_preview_geometry_publication.py::test_off_apply_refreshes_retained_geometry_without_eve_start[True]` | `5.059s` |
| **Total** | **`20.275s`** |

A temporary fixture-boundary observer then ran the exact four IDs locally once.
All four passed (`4 passed in 23.55s`), and all four calls to the fixture's
legacy `wait_state` found the current runtime callback to be
`Api._preview_runtime_changed`, not the fixture's notifying `publish` callback:

| Identity | Callback at legacy wait | Local wait observation |
|---|---|---:|
| `tests/test_preview_presentation.py::test_main_adapters_never_present_on_pump_and_coalesce_while_page_blocked` | `Api._preview_runtime_changed` | `5.000402s` |
| `tests/test_preview_presentation.py::test_identified_capture_through_main_while_old_delivery_is_blocked` | `Api._preview_runtime_changed` | `5.000476s` |
| `tests/test_preview_geometry_publication.py::test_retained_drag_and_commit_notify_distinct_authorities` | `Api._preview_runtime_changed` | `5.000201s` |
| `tests/test_preview_geometry_publication.py::test_off_apply_refreshes_retained_geometry_without_eve_start[True]` | `Api._preview_runtime_changed` | `5.000363s` |

This is direct baseline evidence of four disconnected condition waits. The local
elapsed values only diagnose the mechanism; the retained Windows JUnit values
above remain the frozen hosted observations. The source `eve_on()` body is
unchanged from merged `463bccb0` and has exact source-plus-final-newline SHA-256
`685f6f1b8950c70c811b3eebc0213ad1bf547488acc214a207ef4b9cd6526f47`:

```python
def eve_on(r, revision=1):
    r.runtime.set_eve(True, revision)
    r.wait_state(lambda state: state.eve == "active")
```

Task 2 adds the test-local trigger observer while leaving the production runtime
unchanged. A fresh archive of `463bccb0` received every permanent Task 2 and
Task 3 test snippet before any repository test edit; its exact seven-file
relevant selection passed all `494` identities. The repository candidate then
passed the four target IDs, and dynamic instrumentation observed exactly one
`trigger_and_wait_state()` call in each target. AST inspection found exactly four
calls total—two presentation EVE transitions, one geometry EVE transition, and
the companions `[True]` transition—with their original predicates unchanged,
no fifth call, and zero legacy `r.wait_state()` calls in those target bodies.
The companions `[False]` row remains untriggered. `eve_on()` remains byte-for-byte
unchanged at SHA-256
`685f6f1b8950c70c811b3eebc0213ad1bf547488acc214a207ef4b9cd6526f47`.

The complete eight-file `runtime_pump` consumer selection then passed all `388`
identities in frozen order, with ordered final-newline SHA-256
`36e61c70b9d081f2302bd2928f2b83e2c8d6e9032fe2c9fa8dd0c2eeee0d784f`.
The other five consumer files are byte-for-byte unchanged from `463bccb0`.
Production `wingman/preview/runtime.py`, `wingman/ui/api.py`, and
`wingman/ui/fleetpresentation.py` retain their protected hashes. These are
structural callback-completion results; no elapsed-time saving is claimed.

## Timing baseline and bounded-oracle evidence

The retained Windows observation for
`tests/test_fleetsharing_timing.py::test_rolling_diagnostic_allows_legal_one_ms_per_second_drift_for_2101_prefixes`
is exactly `13.320s`.

The prescribed temporary plugin ran that unchanged identity once and it passed
(`1 passed in 11.53s`). Its exact structural report was:

```json
{
  "candidate_calls": 2101,
  "commit_calls": 2101,
  "exitstatus": 0,
  "oracle_calls": 2101,
  "oracle_checks": 2208151
}
```

Thus the baseline performs `2,101` production candidates, `2,101` commits,
`2,101` independent oracle calls, and exactly `2,208,151` oracle membership
checks (`2101 * 2102 / 2`).

Task 3 changed only the rolling test's oracle input. The expected slice is
independently derived as `exchanges[max(0, second - 95):]` from the literal
inclusive 95-second protocol rule and the trace's fixed one-second request-start
cadence; it does not read candidate state, production timing constants, or a
production cutoff. Fresh GREEN instrumentation reported exactly `2,101`
candidates, `2,101` commits, `2,101` oracle calls, and `197,136` membership
checks. The complete timing module passed all `41` identities in frozen order,
with hash `f4fe35e78a92078c923fd894382c38924501fe6d1f3a4e56a8f8839c0382e37a`.
The rolling test still checks every exact vector and interval, detached state,
commit, 96-record bound, final server value `2202100`, and clear inconsistency
latch.

## Screenshot baseline and focused-walk evidence

The retained Windows artifact records these eight complete-walk observations:

| Identity | Windows testcase observation |
|---|---:|
| `tests/test_shoot_screens.py::test_walk_records_setup_failure_as_failed_shot` | `0.874s` |
| `tests/test_shoot_screens.py::test_walk_applies_and_clears_device_metrics_for_narrow_screen` | `2.257s` |
| `tests/test_shoot_screens.py::test_walk_clears_device_metrics_even_when_narrow_screenshot_fails` | `0.783s` |
| `tests/test_shoot_screens.py::test_walk_applies_device_metrics_before_narrow_setup_script` | `1.525s` |
| `tests/test_shoot_screens.py::test_walk_narrow_setup_runs_inside_device_metrics_override_on_failure` | `0.578s` |
| `tests/test_shoot_screens.py::test_walk_failure_path_records_set_eval_attempt_clear_in_order` | `0.428s` |
| `tests/test_shoot_screens.py::test_walk_failure_path_records_attempt_before_clear_not_only_clear` | `0.847s` |
| `tests/test_shoot_screens.py::test_walk_injects_fittings_fixture_before_stage_actions` | `1.615s` |
| **Total** | **`8.907s`** |

The prescribed temporary walk plugin ran the normal 35-ID order once and all 35
passed (`35 passed in 10.28s`). It observed exactly `35` real `shoot.walk()`
calls and `515` visits: all eight changed IDs performed the same exact 61-key
production walk, while the 27 unchanged focused IDs each performed one visit.
The not-yet-created candidate fixture had `0` constructions, as expected at
baseline. Existing test assertions therefore exercised the setup-failure,
metrics set/clear, successful setup/capture/clear, failure attempt/clear, and
Fittings injection operation contracts during those real walks.

An independent import of `scripts/shoot_screens.py` found `61` unique ordered
screens, `14` `at_floor` screens, and `13` screens whose route is `fittings`.
The inventory order is fixed by the protected source hash above. Production
`shoot.walk()` and `shoot.SCREENS` were not replaced or edited.

Task 3 froze those original `Screen` objects and the exact 61-key order in the
test module, then selected only the owning rows for seven formerly broad tests.
The exact eight identities passed with ordered hash
`d42ecdf5d0c82bdd29e86f43c9553eefee50dfdd8fceee1e65430dad589c9774`.
Instrumentation observed five real walks and `78` visits with exact selector
lengths `2/61/1/shared-1/13`: both Preview setup rows, the complete production
inventory, the Preview success row, one immutable Preview failure receipt shared
by four consumers, and every Fittings row in production order. The complete walk
separately proved all 61 ordered keys and `error is None` for every shot; its 14
floor set/clear pairs each contained a successful capture between set and clear.
All 13 Fittings visits injected the fixture, and every later stage began with the
reset script before its action assertion.

The four failure-receipt consumers passed together (`4 passed`) with exactly one
module fixture construction, one real walk, and one visit. Each same node also
passed alone in a separate pytest process. The receipt contains only read-only
shot mappings, a tuple of operations, and the final boolean override state, and
returns after its bounded monkeypatch context exits.

Normal, reverse-within-fifteen, and seed-`20260926`-shuffle-within-fifteen orders
each passed the exact 35 unique identities with their frozen respective hashes.
Each lifetime-safe run constructed one receipt and performed exactly 32 real
walks and 105 visits, with sorted walk lengths `[1] * 29 + [2, 13, 61]` and one
exact full, Fittings, and two-Preview visit list. The separate round-robin
cross-module order passed the exact same identity set; its observed four receipt
constructions, 35 walks, and 108 visits are diagnostics only and are not used as
lifetime evidence across module teardown and re-entry.

The three affected Windows areas remain separate observations:

| Area | Identities | Windows testcase observation |
|---|---:|---:|
| Disconnected Preview readiness waits | `4` | `20.275s` |
| Rolling timing oracle | `1` | `13.320s` |
| Complete screenshot walks | `8` | `8.907s` |
| **Affected testcase upper sum** | **`13`** | **`42.502s`** |

`42.502s` is only the arithmetic sum of these testcase observations. It is not
a projected saving, lower bound, p95, Test-step, job, throughput, or critical-path
claim.

## TDD RED/GREEN record

Task 2 used literal collectable RED before the permanent edit. A temporary stub
raising `AssertionError("trigger wait not implemented")` was installed with only
the four intended import/call conversions. The frozen four IDs collected in their
exact order and each produced a call-phase `failure`; every traceback contained
exactly `AssertionError: trigger wait not implemented`, with no import, name,
collection, setup, skip, or timeout failure. The three files were restored in a
`finally` block and exact bytes, SHA-256, binary diff, and NUL-delimited status
were all reproduced before GREEN was written. RED was not committed.

GREEN replaced the fixture wait closure with the exact two-mode helper, retained
the original mutable `r.states`, and added the exception-safe trigger observer.
The same frozen four IDs passed. Static and dynamic gates then proved the exact
four call sites, one invocation per target, unchanged predicates, zero old
disconnected waits in those bodies, and unchanged `eve_on()`.

Task 3 established its timing RED with the baseline instrumentation still
wrapping the real candidate, commit, and oracle calls. A temporary final-oracle
assertion required `oracle_checks == 197136`; the unchanged rolling body failed
in the call phase at exact actual value `2,208,151`, after `2,101` candidate and
oracle calls. The final assertion deliberately prevented the last commit, so the
RED report recorded `2,100` commits. The temporary assertion was external and
was not committed. After bounding only the expected oracle slice, the same
instrumentation passed with exact counts `2,101/2,101/2,101/197,136` for
candidates, commits, oracle calls, and membership checks. The screenshot changes
then passed their existing eight identities and the mutation qualification below
without adding or renaming a test. Independent review found that the two-row
Preview setup-failure test retained both per-shot error assertions but did not
itself pin the selected output order. The correction added the exact
`groups`-then-`narrow` key tuple immediately after `shoot.walk()` without changing
those error assertions or any identity/signature.

Task 5 polish found that the full traversal's nth-set/nth-clear pairing did not
prove interval ownership: a temporary delegating wrapper queued every real clear
until `walk()` returned, preserving all 14 set and clear counts, and the old test
still passed (`1 passed`). After replacing the pairing with the exact operation
state machine, that same mutation failed in the call phase at the unique
`floor metrics interval captured more than once` assertion. The wrapper then
restored exact test bytes, SHA-256, binary diff, and NUL-delimited status; the
unmutated identity passed again. This RED changes no identity, signature, screen
selection, or production behavior.

## Mutation and fault qualification

Task 2 materialized the external in-memory runtime qualification suite under
`/tmp`. Its exact-ID collection plugin observed the prescribed `18` unique IDs in
order. The one-component-classname JUnit parser mapped those collected IDs
without guessing, and all `18` outcomes were `passed`. The probes covered direct
and composed legacy snapshot semantics, arm-before-trigger, delegate blocking,
terminal error precedence, exact state/return/error identity, current-snapshot
equality, matching no/partial reconciliation failures, nonmatching-first error
precedence, replacement preservation, sequential depth one, concurrent rejection
before trigger, stale-target rejection, exact trigger-error cleanup, exact
waiter-side `BaseException` identity, owned cleanup, replacement-safe cleanup,
and exact cleanup-failure `__cause__`; no current marked wrapper remained.

Each observer mutant was applied separately and failed only its exact selected
external ID in the call phase at the required unique assertion:

| Mutant | Exact owning failure |
|---|---|
| Missing delegation | `test_delegate_is_called_once_with_exact_state_and_return` — `captured delegate did not receive the exact state once` |
| Premature notify | `test_wait_condition_cannot_complete_before_blocked_delegate` — `wait condition returned before delegate completion` |
| Callback error counted as success | `test_matching_callback_error_is_exact_and_never_successful[none]` — `DID NOT RAISE ValueError` |
| First error ignored | `test_nonmatching_error_precedes_later_matching_success` — `DID NOT RAISE RuntimeError` |
| Terminal-race error ignored | `test_terminal_finalization_prioritizes_error_before_owned_disarm` — `DID NOT RAISE RuntimeError` |
| Unconditional restore | `test_replacement_during_delegate_is_not_overwritten` — `replacement callback was overwritten` |
| Wrapper accumulation | `test_concurrent_wait_is_rejected_before_its_trigger_runs` — `concurrent trigger ran` |
| Exceptional cleanup deleted | `test_wait_baseexception_restores_owned_observer` — `owned exceptional cleanup did not restore delegate` |

Every mutant run rejected timeout, wait-probe-release, collection, fixture,
setup/teardown, and competing observer failures. After each exact restoration,
the terminal race, premature-completion probe, all three interruption/cleanup
probes, matching `[partial]`, stale-target, trigger-error, and sequential cases
all passed again. Every mutation restored exact bytes, SHA-256, binary diff, and
NUL-delimited status before the next row.

Task 3 applied nine production timing mutations independently. Each exact
selected JUnit row failed in the call phase at its intended retained assertion,
with no timeout, collection, fixture, setup/teardown, or later defensive-overflow
masking:

| Timing defect | Exact owning witness |
|---|---|
| Exclusive 95-second boundary | binary-ratio `[95.0-2]` vector comparison |
| Receipt time substituted for request start | request-start retention vector comparison |
| Pruning removed | rolling first expired-prefix vector comparison |
| 94-second window | binary-ratio `[95.0-2]` vector comparison |
| 96-second window | binary-ratio `[95.00000000000001-1]` vector comparison |
| Capacity changed to 95 | rolling `prepared is not None` edge assertion |
| Server time stalled | rolling final `last_server_time_ms == 2202100` assertion |
| Legal recurrence latched | rolling candidate-presence assertion |
| Candidate base committed instead of candidate state | rolling vector comparison |

Task 3 also applied 14 screenshot defects or test-double faults independently.
Every selected JUnit identity failed in the call phase at the named assertion,
not during setup, collection, or a timeout:

| Screenshot defect | Exact owning witness |
|---|---|
| First production screen omitted | full traversal exact 61-key assertion |
| First two production screens reordered | full traversal exact 61-key assertion |
| Ordinary `uploader` capture failed | exact keys passed, then the separate all-shot `error is None` assertion failed |
| Every non-early floor override omitted | focused Preview success-order lookup for `set:840x625` |
| Only `fittings-narrow` floor override omitted | full traversal `floor set count mismatch` |
| Twelfth floor set deferred until after capture | full traversal `floor capture did not occur between set and clear` |
| Preview group setup skipped | exact two-row test's group error assertion |
| Preview narrow setup skipped | exact two-row test's narrow error assertion |
| Verifier moved after screenshot | focused Preview postcondition `captures == []` assertion |
| Screenshot call replaced with bytes | shared attempt-order consumer's `screenshot_attempt` assertion |
| Final clear omitted | shared clear/inactive consumer's clear assertion |
| Cleanup evaluation omitted | selected new/current cleanup identities each failed their cleanup assertion |
| Fittings injection moved after reset/preparation | Fittings `stage[0]` reset-order assertion |
| Fittings selector omitted `fittings-unfiled` | exact 13-key tuple assertion |

Task 5 reran those 14 original screenshot mutations against the strengthened
final-tree test and added the deferred-all-clears fault above as a fifteenth
qualification row. All 15 failed at their intended call-phase assertions without
timeout, collection, fixture, setup, or teardown masking. In particular, omitting
only the non-Preview `fittings-narrow` set still failed `floor set count mismatch`;
deferring its set until after capture still failed at the state machine's
`floor metrics clear before successful capture`; and omitting the failure-path
clear still failed the shared clear/inactive consumer. The new all-clears-deferred
fault retained exact counts and old nth-pair ordering but failed on the first
second capture inside an active floor interval. Every row restored exact bytes,
SHA-256, binary diff from `HEAD`, and NUL-delimited status.

The review correction received its own RED: temporarily reversing the real
`screens_for_gate(True)` result made the setup-failure identity fail in the call
phase at the new tuple assertion, with actual `narrow`-then-`groups` versus
expected `groups`-then-`narrow`. It did not reach either retained per-shot error
assertion. The production script was then restored with exact bytes, SHA-256,
binary diff, and NUL-delimited status.

All 23 original Task 3 mutations restored exact target bytes and SHA-256, binary
diff from `HEAD`, and NUL-delimited porcelain status before the next row. The
additional review-correction RED used the same restoration guarantees. Unmutated
timing, screenshot, and receipt-consumer reruns remained green after restoration.

## Identity, order, and structure verification

At the Task 1 baseline, the five in-scope source files were byte-equal to merged
`463bccb0`:

| Baseline in-scope test file | SHA-256 | Test functions |
|---|---|---:|
| `tests/test_preview_runtime_review.py` | `99956369ad5351db363f95e545578f721a2efb12e6c32a5812fe9d5177d0975c` | `12` |
| `tests/test_preview_presentation.py` | `965357c1cc8df351129e599b2730c4273f0bdc4499ccb3233e0f7807857273cc` | `7` |
| `tests/test_preview_geometry_publication.py` | `87eb1544143ba9a967a2577f7dbd413d4f73f71e3e2c673a96c95aab2cd04f3f` | `12` |
| `tests/test_fleetsharing_timing.py` | `0b40d25707b3af8f8adba8e5457bda3b7050477ae1515c87e6450c3011feca13` | `24` |
| `tests/test_shoot_screens.py` | `b8a97b8773a9438739e9ec202cd6a21fd106445d08370f7a0b863a64b1487255` | `98` |

AST recording found exactly `153` unique `test_*` function definitions.
Canonical JSON containing filename, function name, function kind,
positional/positional-only/keyword-only arguments, vararg, kwarg, and decorator
AST has SHA-256
`b143456e8f8087e6e9f6879cfa4fe708fd164eba1d1647b9812986bffd7715cf`.
The corresponding 313 collected `[nodeid, sorted marker names]` records have
SHA-256 `a47c53c5c62e994c94411aea01276d3477651dd0186e5793d7f0a6c782112ea8`.
Parameterized IDs are retained in the decorator AST and in collected node IDs.
Those names, signatures, decorators, markers, and collected order are the exact
baseline data, with zero differences at Task 1.

Task 2 reran the identity/signature gate against a fresh `463bccb0` archive.
All `313` five-file identities and sorted marker rows are exactly equal with
ordered hash
`a21d48abcdfaeb9b2b33ab5e1b089f5da4e692f01bebe94c104908728235eaef`;
all current test names, signatures, decorators, parameters, IDs, and markers are
unchanged. The Preview consumer JUnit independently confirms the frozen `388`
identity order/hash. Only the intended three Preview test files differ among the
eight `runtime_pump` consumers.

The Task 3 identity/signature gate retained all `313` five-file identities and
sorted markers in exact order, with frozen hash
`a21d48abcdfaeb9b2b33ab5e1b089f5da4e692f01bebe94c104908728235eaef`.
It found exactly four—and only four—signature substitutions in
`tests/test_shoot_screens.py`, each from `(tmp_path, monkeypatch)` to
`(preview_narrow_failure_walk)`:

- `test_walk_clears_device_metrics_even_when_narrow_screenshot_fails`;
- `test_walk_narrow_setup_runs_inside_device_metrics_override_on_failure`;
- `test_walk_failure_path_records_set_eval_attempt_clear_in_order`;
- `test_walk_failure_path_records_attempt_before_clear_not_only_clear`.

An empty, missing, or fifth candidate change fails that comparison. A fresh
seven-file relevant run passed all `494` identities in exact frozen order with
hash `ad677b5f7f9b2667401ccfc39295de021c8a320498d59a3679b05497491b229e`.
This includes complete `220`-, `90`-, and `91`-identity runs for
`test_shoot_screens.py`, `test_new_screenshots.py`, and
`test_current_screenshots.py`. The executable screenshot worker tests passed
`12` identities, and `node --test tests/fixtures/screenshot_dom.test.cjs` passed
all `35` cases with zero failures, skips, cancellations, or todos.

## Complete local endpoint

Task 4 rebuilt the locked development environment (`56` packages resolved, `39`
checked), found Node `v26.5.0`, built the settings codec with Cargo's locked release
profile, copied it to `packaging/bin/wingman-settings-codec`, and observed
`codec.codec_available() is True` before pytest.

Fresh focused verification passed on its first execution; no failed order was
retried:

- the exact Preview four passed with one trigger-helper call per identity, and the
  complete eight-file Preview consumer selection passed all `388` exact ordered
  identities;
- the external observer file collected and passed its exact `18` identities; its
  parser used the observed classname/name map and confirmed waiter interruption
  identity, owned restoration, legitimate-replacement preservation,
  cleanup-failure cause chaining, and no current marked wrapper;
- the rolling identity passed with exactly `2,101` candidate calls, `2,101`
  commits, `2,101` oracle calls, and `197,136` oracle checks; all `41` timing
  identities then passed in frozen order;
- the changed screenshot eight passed with one receipt construction, five walks,
  and `78` visits; the contiguous fifteen passed with one construction, `12`
  walks, and `85` visits;
- normal, reverse-within-fifteen, and seed-`20260926`-shuffle-within-fifteen
  orders each passed the exact `35` identities with their frozen hashes, one
  receipt construction, `32` walks, and `105` visits. The mixed order passed the
  same exact identity set; its observed four constructions, `35` walks, and `108`
  visits remain diagnostics only and are not lifecycle acceptance evidence;
- the seven-file relevant selection passed all `494` exact ordered identities;
  static and dynamic checks again found exactly four trigger-helper calls, no
  fifth call, unchanged predicates, zero old waits in those target bodies, and
  the exact unchanged `eve_on()` hash.

The required Api/protocol/isolation/lifecycle command passed `1,793` tests with
zero skips, failures, or errors. The complete codec-backed local run then passed
exactly `16,595` and skipped the expected `14`, totaling `16,609`; it completed in
`434.67s`, while the JUnit testcase sum was `395.550s`. The JUnit identities equal
fresh source collection byte-for-order with final-newline SHA-256
`f468ba1954d3ff0ab693dd721ff8a7a4d12266e16d8568035de4245a6c616100`.
The normalized ordered skip array equals Appendix B exactly and hashes to
`14f1511f840fb2fdc1680123dde29a7143405829af97141d62c5099aa4f265af`.
There were zero failures/errors and no Node, codec, or unexpected native skip.
All five targeted test-file subsequences retained their frozen identity order.

Independent gates passed: every page module loaded under `node scripts/js_smoke.js`;
the direct screenshot DOM fixture passed `35/35`; Cargo passed its one codec test;
global Ruff check passed; Ruff format reported `520 files already formatted`;
documentation passed `7/7`; and the baseline-range diff check passed. All `23`
temporary runners/plugins/tests used by Task 4 passed `py_compile`, Ruff check,
and Ruff format check.

Task 4's pre-polish fault pass reran all `31` then-required mutations: all eight
observer, nine timing, and fourteen screenshot defects failed at their exact
intended call-phase identities without timeout or later masking. The observer runner also
reran nine unmutated cleanup/race cases after every row. The literal four-ID RED,
external-JUnit parser self-test, signature exception gate, and disposable
restoration-failure simulation passed. Every mutation row restored exact bytes,
SHA-256, binary diff from `HEAD`, and NUL-delimited porcelain status before the
next row. Post-mutation Preview, timing, and structural-order instruments passed
again from the restored tree.

Task 5's screenshot-state-machine correction then passed the complete
`test_shoot_screens.py` inventory (`220 passed`) and the exact ordered relevant
selection (`494 passed`, hash
`ad677b5f7f9b2667401ccfc39295de021c8a320498d59a3679b05497491b229e`).
The normal, reverse-within-fifteen, and seed-`20260926` shuffle orders each passed
35 identities with their frozen hashes and exactly one receipt construction,
32 walks, and 105 visits. The mixed order passed all 35 identities; its observed
four constructions, 35 walks, and 108 visits remain diagnostics only. The
14 original screenshot mutations plus the deferred-all-clears mutation passed
the exact-failure/restoration runner (`15` rows). Together with the unchanged
eight observer and nine timing rows, the final mutation catalog is exactly `32`
rows (`8 + 9 + 15`); all 32 reran with exact intended failures and restoration
from the correction tree. Focused Ruff check and format check passed for the
changed test, documentation passed, and the exact scope,
protected hashes, and diff checks remained green.

LOCAL CONCLUSION: Stage A preserves the exact ordered 16,609 identities and local outcomes while removing the approved same-identity deterministic work. Structural callback completion, 2,101 transitions/197,136 oracle checks, and 32 walks/105 visits are acceptance evidence. All elapsed values are observations only; no speedup, lower bound, p95, job, or critical-path claim is made.

## Reviews, scope, restoration, and leftovers

Task 4 required implementation self-review confirms:

- **Scope:** exactly the consented spec, plan, results ledger, and five in-scope
  tests differ from `463bccb0`. Presentation differs only by the trigger-helper
  import and two named EVE conversions; geometry differs only by that import, the
  retained-drag EVE conversion, and companions `[True]` conversion. All `13`
  protected hashes match, and the protected production/workflow/configuration/
  packaging/fixture range diff is empty.
- **Identity:** complete collection and JUnit retain exact `16,609` order/hash and
  `+0/-0`; all targeted orders match, markers and parameters are unchanged, and
  the signature gate admits exactly the four named receipt-consumer substitutions
  from `(tmp_path, monkeypatch)` to `(preview_narrow_failure_walk)`.
- **Preview observer:** the test-local helper atomically arms before the trigger,
  rejects an already-true target, captures the actual callback, separates
  successful completions from errors, delegates before completion, preserves
  exact return and exception objects, gives the first matching or nonmatching
  callback error precedence, and exposes that same object to the waiter and
  production-style catch. It does not replay or wake production state, rejects a
  marked concurrent wrapper before trigger, and restores only an observer it owns
  while preserving a legitimate replacement. The supplied predicate and literal
  five-second bound are unchanged.
- **Preview structure:** the old captured/running-callback unsafe return remains
  reproduced by the external legacy witnesses. `eve_on()` is byte-for-byte
  unchanged; exactly the four named disconnected transitions use
  `trigger_and_wait_state()`, with no fifth use and structurally zero old timeout
  waits. The retained hosted `20.275s` value is an observation only.
- **Timing:** the rolling case retains all `2,101` candidates and commits, derives
  its independent expected input from the literal inclusive 95-second rule and
  fixed one-second cadence, performs exactly `197,136` oracle checks, and retains
  exact vectors/intervals, the `<= 96` bound, final `2202100`, and clear
  inconsistency latch.
- **Screenshots:** all exact eight IDs and selectors/lists pass. One complete
  traversal proves all `61` ordered screens, all-shot success, and all `14` floor
  branches through an exact inactive → set → one capture → clear → inactive
  state machine that rejects nested sets, second captures, stray clears, and a
  live interval at traversal end; the two Preview setup failures, one success
  order, immutable module-scoped failure receipt, all `13` Fittings screens, and
  all `27` existing focused walks remain covered. Each lifetime-safe order proves
  one construction, `32` walks, and `105` visits; mixed order is outcome-only
  evidence.
- **Mutations:** the exact final catalog is `32` rows—eight observer, nine timing,
  and fifteen screenshot—and every mutant fails its intended assertion. Matching
  no/partial reconciliation and nonmatching callback errors preserve exact
  objects; the ordinary failed shot retains its key and fails the
  separate all-shot assertion. No timeout or later failure is credited, and every
  temporary edit restores exactly.
- **Order:** Preview transitions are trigger-armed. Normal, reverse, and
  deterministic-shuffle contiguous screenshot orders passed without retry; the
  mixed cross-module order passed without a singleton, walk-count, or visit-count
  acceptance claim.
- **Prerequisites/gates:** Node, the release codec, full pytest and exact skips,
  JS smoke, direct DOM fixture, Cargo, global Ruff check/format, documentation,
  diff, exact scope, narrow-diff, and protected-hash gates are fresh and green.
- **Claims:** retained `646.538s`, `680s`, and `42.502s` values and fresh local
  `434.67s`/`395.550s` values are observations only. No speedup, lower bound, p95,
  job, throughput, or critical-path conclusion is drawn.
- **Leftovers:** no overlay, scratch/report, XML/JSON/ZIP evidence, mutation,
  counter, debug output, mutable receipt, unfinished marker, local `/tmp` path,
  disabled assertion, zero workflow budget, or Stage B/C implementation is
  tracked or staged. The requested Task 4 report remains outside the worktree.

Task 3 self-review additionally confirms:

- only `tests/test_fleetsharing_timing.py`, `tests/test_shoot_screens.py`, and
  this results ledger are modified relative to the Task 2 commit;
- the implementation is byte-for-byte equal to the plan-qualified Task 3
  candidate after Ruff formatting;
- the timing bound is test-premise-derived and leaves every production candidate,
  detached-state check, commit, capacity, and final-state assertion intact;
- `_walk_screens()` returns original import-time production objects in requested
  order; the sole full traversal owns exact inventory, all-shot success, and all
  14 floor branches;
- the failure receipt is frozen and detached, with no CDP, path, mutable operation
  list, or live monkeypatch retained;
- focused Ruff check and format check passed; local polish in fix mode found no
  safe correction, and independent review's one medium missing-order assertion
  was corrected with a dedicated RED and fresh Task 3 verification;
- production timing and screenshot source, unchanged new/current screenshot
  tests, fixtures, generated JUnit/JSON, and temporary mutation scripts are not
  staged or tracked.

Task 2 self-review additionally confirms:

- the implementation is byte-for-byte equal to the plan-qualified Task 2
  candidate;
- observer installation, terminal selection, and owned disarm occur under the
  runtime condition, while the local completion condition never takes the
  runtime condition;
- one outer `BaseException` boundary covers trigger, wait, predicate/snapshot,
  callback, timeout, and final cleanup paths; the original body exception remains
  primary and a cleanup failure is exposed as its explicit cause;
- restoration never invokes the production setter, resets `_published`, wakes or
  republishes runtime state, or overwrites a legitimate replacement;
- focused Ruff check and Ruff format check passed for all three modified test
  files, and `git diff --check` passed;
- no production, other Preview test, XML, JSON, cache, probe, or mutation script
  is staged or tracked.

Task 1 self-review confirms:

- the baseline branch ancestry is exact and the starting tree was clean;
- source/test/workflow/configuration bytes match merged `463bccb0`;
- all temporary parsers and plugins live under `/tmp`, compiled, and passed Ruff
  check/format check;
- temporary instrumentation changed runtime objects only inside their pytest
  processes and left no versioned source edit;
- the retained PR #290 artifact directory was read only;
- the only Task 1 versioned path is this results ledger;
- no XML, JSON, ZIP, cache, generated evidence, debug counter, mutation, or local
  script is staged or tracked;
- no subagent or independent review was used, as explicitly required for this
  task.

Task 1 concern was historical: the worktree initially lacked pytest and the
release codec, so Task 1 made no fresh local complete-suite claim. Task 4 closed
that prerequisite gap by rerunning locked synchronization, building and installing
the release codec, asserting codec availability, and completing the exact local
endpoint above.

## Publication stop and hosted evidence

This task reads already retained, previously authorized PR #290 baseline evidence
only. It did not push, update a PR, dispatch/rerun Actions, download a new
artifact, or mutate any remote. There is no Stage A candidate hosted outcome.
Candidate publication and hosted comparison remain stopped pending separate
explicit authorization.

PRE-AUTHORIZATION STOP: do not push, create or update a pull request, dispatch or rerun GitHub Actions, download a candidate-run artifact, or make a hosted acceptance claim until the maintainer explicitly authorizes publication of the frozen reviewed executable head.

## Appendix A — exact targeted identity lists

### Preview four

```text
tests/test_preview_presentation.py::test_main_adapters_never_present_on_pump_and_coalesce_while_page_blocked
tests/test_preview_presentation.py::test_identified_capture_through_main_while_old_delivery_is_blocked
tests/test_preview_geometry_publication.py::test_retained_drag_and_commit_notify_distinct_authorities
tests/test_preview_geometry_publication.py::test_off_apply_refreshes_retained_geometry_without_eve_start[True]
```

### Rolling timing one

```text
tests/test_fleetsharing_timing.py::test_rolling_diagnostic_allows_legal_one_ms_per_second_drift_for_2101_prefixes
```

### Changed screenshot eight

```text
tests/test_shoot_screens.py::test_walk_records_setup_failure_as_failed_shot
tests/test_shoot_screens.py::test_walk_applies_and_clears_device_metrics_for_narrow_screen
tests/test_shoot_screens.py::test_walk_clears_device_metrics_even_when_narrow_screenshot_fails
tests/test_shoot_screens.py::test_walk_applies_device_metrics_before_narrow_setup_script
tests/test_shoot_screens.py::test_walk_narrow_setup_runs_inside_device_metrics_override_on_failure
tests/test_shoot_screens.py::test_walk_failure_path_records_set_eval_attempt_clear_in_order
tests/test_shoot_screens.py::test_walk_failure_path_records_attempt_before_clear_not_only_clear
tests/test_shoot_screens.py::test_walk_injects_fittings_fixture_before_stage_actions
```

### Contiguous `test_shoot_screens.py` fifteen

```text
tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture[settings-wanderer-controls-narrow]
tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture[profiles-copy-scope]
tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture[fittings-copy-preflight-bottom-narrow]
tests/test_shoot_screens.py::test_walk_records_setup_failure_as_failed_shot
tests/test_shoot_screens.py::test_walk_applies_and_clears_device_metrics_for_narrow_screen
tests/test_shoot_screens.py::test_walk_clears_device_metrics_even_when_narrow_screenshot_fails
tests/test_shoot_screens.py::test_walk_applies_device_metrics_before_narrow_setup_script
tests/test_shoot_screens.py::test_walk_narrow_setup_runs_inside_device_metrics_override_on_failure
tests/test_shoot_screens.py::test_walk_failure_path_records_set_eval_attempt_clear_in_order
tests/test_shoot_screens.py::test_walk_failure_path_records_attempt_before_clear_not_only_clear
tests/test_shoot_screens.py::test_walk_injects_fittings_fixture_before_stage_actions
tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails[fittings-copy-progress]
tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails[settings-previews-groups]
tests/test_shoot_screens.py::test_alerts_base_capture_walk_waits_then_frames_or_records_failure[False]
tests/test_shoot_screens.py::test_alerts_base_capture_walk_waits_then_frames_or_records_failure[True]
```

### Unchanged new-screenshot eight

```text
tests/test_new_screenshots.py::test_new_capture_cleanup_runs_after_any_failure[profiles-setup-import-prepare]
tests/test_new_screenshots.py::test_new_capture_cleanup_runs_after_any_failure[profiles-setup-import-stage]
tests/test_new_screenshots.py::test_new_capture_cleanup_runs_after_any_failure[profiles-setup-import-verify]
tests/test_new_screenshots.py::test_new_capture_cleanup_runs_after_any_failure[profiles-setup-import-capture]
tests/test_new_screenshots.py::test_new_capture_cleanup_runs_after_any_failure[settings-previews-crop-narrow-prepare]
tests/test_new_screenshots.py::test_new_capture_cleanup_runs_after_any_failure[settings-previews-crop-narrow-stage]
tests/test_new_screenshots.py::test_new_capture_cleanup_runs_after_any_failure[settings-previews-crop-narrow-verify]
tests/test_new_screenshots.py::test_new_capture_cleanup_runs_after_any_failure[settings-previews-crop-narrow-capture]
```

### Unchanged current-screenshot twelve

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
```

The exact normal 35-ID order is the contiguous fifteen followed by the new eight
and current twelve above. Its ordered hash is
`75e7172a2c9685582b2e4adbc15decd71bc2ebb978f65b84acf9f738c2546786`.
Reversing only the fifteen yields
`dfef25628da7c26bd98db8f4fc5862bd5dc2c7c73888b92197fd1279bf8c4ef1`;
seed-`20260926` shuffling only the fifteen yields
`04a1f9125d3bbbb0dbef9eed72916b8a11db8d0b6cbc08782f084f50d6a5e59f`.
The unchanged focused 27 are the seven non-changed IDs in the fifteen plus the
new eight and current twelve.

## Appendix B — exact normalized Ubuntu skip array

The rows below are the exact ordered `[nodeid, normalized_message]` pairs used by
the serialization and hash stated above.

| # | Node ID | Normalized reason |
|---:|---|---|
| `1` | `tests/test_clipserve.py::test_a_live_reader_does_not_block_deletion` | `delete-while-open is a Windows sharing rule` |
| `2` | `tests/test_evesettings_profilecopy.py::test_prepare_copy_rejects_a_real_windows_server_junction_outside_the_root` | `requires a real Windows junction` |
| `3` | `tests/test_evesettings_profilecopy.py::test_prepare_copy_rejects_a_real_windows_profile_junction_outside_the_server` | `requires a real Windows junction` |
| `4` | `tests/test_evesettings_profilecopy.py::test_cleanup_refuses_a_stage_shaped_windows_junction_rather_than_following_it` | `requires a real Windows junction` |
| `5` | `tests/test_eveskills_dpapi.py::test_round_trips_on_windows` | `requires real DPAPI` |
| `6` | `tests/test_eveskills_dpapi.py::test_crypt32_binding_is_cached` | `requires real WinDLL` |
| `7` | `tests/test_preview_host.py::test_stop_from_another_thread_really_exits_the_pump` | `needs a real message pump and window station` |
| `8` | `tests/test_preview_win32.py::test_every_used_function_is_declared` | `binds user32/gdi32/dwmapi` |
| `9` | `tests/test_preview_win32.py::test_pointer_sized_returns_are_not_left_at_the_c_int_default` | `binds user32/gdi32/dwmapi` |
| `10` | `tests/test_preview_win32.py::test_bind_is_cached_so_declarations_are_applied_once` | `binds user32/gdi32/dwmapi` |
| `11` | `tests/test_tray.py::test_adapter_loads_against_the_pinned_pystray_windows_backend` | `pystray Windows backend` |
| `12` | `tests/test_ui_setup_profile.py::test_recognized_file_shaped_junction_refuses[core_char_31.dat]` | `requires real Windows junction` |
| `13` | `tests/test_ui_setup_profile.py::test_recognized_file_shaped_junction_refuses[prefs.ini]` | `requires real Windows junction` |
| `14` | `tests/test_wanderer_integration.py::test_real_windows_credential_document_roundtrip_replace_binding_and_remove` | `real Windows user-bound DPAPI required` |

## Appendix C — exact normalized Windows skip array

The rows below are the exact ordered `[nodeid, normalized_message]` pairs used by
the serialization and hash stated above.

| # | Node ID | Normalized reason |
|---:|---|---|
| `1` | `tests/test_api_evesettings.py::test_state_reports_an_unreadable_backup_store` | `this user can read a mode-000 directory` |
| `2` | `tests/test_chrome.py::test_enable_resize_is_a_no_op_off_windows` | `the guard under test` |
| `3` | `tests/test_chrome.py::test_enable_taskbar_minimize_is_a_no_op_off_windows` | `the guard under test` |
| `4` | `tests/test_eveauth_state.py::test_authority_primary_and_backup_are_owner_only_on_posix` | `POSIX mode bits; Windows relies on DPAPI` |
| `5` | `tests/test_evesettings_backup.py::test_an_unreadable_store_is_reported_not_read_as_empty` | `this user can read a mode-000 directory` |
| `6` | `tests/test_evesettings_backup.py::test_pruning_an_unreadable_store_deletes_nothing` | `this user can read a mode-000 directory` |
| `7` | `tests/test_evesettings_ops.py::test_case_distinct_targets_are_not_collapsed` | `this filesystem folds case, so these two paths genuinely are the same directory` |
| `8` | `tests/test_evesettings_profilecopy.py::test_prepare_copy_rejects_a_server_junction_outside_the_root` | `POSIX symlink semantics used to fabricate the escape` |
| `9` | `tests/test_evesettings_profilecopy.py::test_prepare_copy_rejects_a_profile_junction_outside_the_server` | `POSIX symlink semantics used to fabricate the escape` |
| `10` | `tests/test_evesettings_profilecopy.py::test_stage_copy_rejects_a_recognized_file_link_outside_the_profile` | `POSIX symlink semantics used to fabricate the escape` |
| `11` | `tests/test_evesettings_profilecopy.py::test_cleanup_refuses_a_stage_shaped_symlink_rather_than_following_it` | `POSIX symlink semantics` |
| `12` | `tests/test_evesettings_tree.py::test_profiles_have_a_stable_path_tiebreaker` | `C:/Users/runneradmin/AppData/Local/Temp/pytest-of-USER/pytest-N/PYTEST_TMP cannot hold two names differing only by case` |
| `13` | `tests/test_evesettings_tree.py::test_the_case_folding_tiebreaker_still_settles_the_order_it_folds` | `C:/Users/runneradmin/AppData/Local/Temp/pytest-of-USER/pytest-N/PYTEST_TMP cannot hold two names differing only by case` |
| `14` | `tests/test_evesettings_tree.py::test_is_under_rejects_a_symlink_escaping_the_root` | `POSIX symlink semantics` |
| `15` | `tests/test_evesettings_tree.py::test_a_denied_probe_says_denied_rather_than_answering_no` | `this user can read a mode-000 directory` |
| `16` | `tests/test_evesettings_tree.py::test_a_denied_child_marks_the_tree_unreadable` | `this user can read a mode-000 directory` |
| `17` | `tests/test_eveskills_dpapi.py::test_protect_refuses_off_windows_rather_than_crashing` | `Windows has crypt32` |
| `18` | `tests/test_eveskills_dpapi.py::test_unprotect_refuses_off_windows_rather_than_crashing` | `Windows has crypt32` |
| `19` | `tests/test_eveskills_skillids.py::test_bak_mode_is_hardened_on_the_recovery_write_back_path_too` | `POSIX mode bits; on Windows DPAPI does the work` |
| `20` | `tests/test_eveskills_state.py::test_the_document_is_owner_only_on_posix` | `POSIX mode bits; on Windows DPAPI does the work` |
| `21` | `tests/test_eveskills_state.py::test_bak_mode_is_hardened_on_the_recovery_write_back_path_too_on_posix` | `POSIX mode bits; on Windows DPAPI does the work` |
| `22` | `tests/test_fleetsharing_state.py::test_saved_file_is_owner_only_on_posix` | `POSIX mode bits; Windows relies on DPAPI` |
| `23` | `tests/test_preflight.py::test_the_real_reader_degrades_rather_than_raising_off_windows` | `off-Windows degradation; on Windows it really reads the registry` |
| `24` | `tests/test_preflight.py::test_the_real_message_box_is_a_no_op_off_windows` | `would pop a real modal dialog and hang the suite` |
| `25` | `tests/test_preview_chrome.py::test_unmarked_pixels_match_independent_pre_marker_reference[RAQM-False-clipped-17-47-Pi\u2026-H\u2026]` | `Pillow was built without RAQM; BASIC coverage still runs` |
| `26` | `tests/test_preview_chrome.py::test_unmarked_pixels_match_independent_pre_marker_reference[RAQM-False-clipped-20-48-P\u2026-H\u2026]` | `Pillow was built without RAQM; BASIC coverage still runs` |
| `27` | `tests/test_preview_chrome.py::test_unmarked_pixels_match_independent_pre_marker_reference[RAQM-False-clipped-23-47-\u2026-\u2026]` | `Pillow was built without RAQM; BASIC coverage still runs` |
| `28` | `tests/test_preview_chrome.py::test_unmarked_pixels_match_independent_pre_marker_reference[RAQM-False-108-17-47-Pi\u2026-H\u2026]` | `Pillow was built without RAQM; BASIC coverage still runs` |
| `29` | `tests/test_preview_chrome.py::test_unmarked_pixels_match_independent_pre_marker_reference[RAQM-False-108-20-48-P\u2026-H\u2026]` | `Pillow was built without RAQM; BASIC coverage still runs` |
| `30` | `tests/test_preview_chrome.py::test_unmarked_pixels_match_independent_pre_marker_reference[RAQM-False-108-23-47-\u2026-\u2026]` | `Pillow was built without RAQM; BASIC coverage still runs` |
| `31` | `tests/test_preview_chrome.py::test_unmarked_pixels_match_independent_pre_marker_reference[RAQM-False-316-17-47-Pi\u2026-H\u2026]` | `Pillow was built without RAQM; BASIC coverage still runs` |
| `32` | `tests/test_preview_chrome.py::test_unmarked_pixels_match_independent_pre_marker_reference[RAQM-False-316-20-48-P\u2026-H\u2026]` | `Pillow was built without RAQM; BASIC coverage still runs` |
| `33` | `tests/test_preview_chrome.py::test_unmarked_pixels_match_independent_pre_marker_reference[RAQM-False-316-23-47-\u2026-\u2026]` | `Pillow was built without RAQM; BASIC coverage still runs` |
| `34` | `tests/test_preview_chrome.py::test_unmarked_pixels_match_independent_pre_marker_reference[RAQM-True-clipped-17-47-Pi\u2026-H\u2026]` | `Pillow was built without RAQM; BASIC coverage still runs` |
| `35` | `tests/test_preview_chrome.py::test_unmarked_pixels_match_independent_pre_marker_reference[RAQM-True-clipped-20-48-P\u2026-H\u2026]` | `Pillow was built without RAQM; BASIC coverage still runs` |
| `36` | `tests/test_preview_chrome.py::test_unmarked_pixels_match_independent_pre_marker_reference[RAQM-True-clipped-23-47-\u2026-\u2026]` | `Pillow was built without RAQM; BASIC coverage still runs` |
| `37` | `tests/test_preview_chrome.py::test_unmarked_pixels_match_independent_pre_marker_reference[RAQM-True-108-17-47-Pi\u2026-H\u2026]` | `Pillow was built without RAQM; BASIC coverage still runs` |
| `38` | `tests/test_preview_chrome.py::test_unmarked_pixels_match_independent_pre_marker_reference[RAQM-True-108-20-48-P\u2026-H\u2026]` | `Pillow was built without RAQM; BASIC coverage still runs` |
| `39` | `tests/test_preview_chrome.py::test_unmarked_pixels_match_independent_pre_marker_reference[RAQM-True-108-23-47-\u2026-\u2026]` | `Pillow was built without RAQM; BASIC coverage still runs` |
| `40` | `tests/test_preview_chrome.py::test_unmarked_pixels_match_independent_pre_marker_reference[RAQM-True-316-17-47-Pi\u2026-H\u2026]` | `Pillow was built without RAQM; BASIC coverage still runs` |
| `41` | `tests/test_preview_chrome.py::test_unmarked_pixels_match_independent_pre_marker_reference[RAQM-True-316-20-48-P\u2026-H\u2026]` | `Pillow was built without RAQM; BASIC coverage still runs` |
| `42` | `tests/test_preview_chrome.py::test_unmarked_pixels_match_independent_pre_marker_reference[RAQM-True-316-23-47-\u2026-\u2026]` | `Pillow was built without RAQM; BASIC coverage still runs` |
| `43` | `tests/test_ui_setup_profile.py::test_manifest_refuses_special_files_and_aliases_before_reading[directory-core_char_31.dat]` | `POSIX special files and unprivileged symlinks` |
| `44` | `tests/test_ui_setup_profile.py::test_manifest_refuses_special_files_and_aliases_before_reading[directory-core_public__.yaml]` | `POSIX special files and unprivileged symlinks` |
| `45` | `tests/test_ui_setup_profile.py::test_manifest_refuses_special_files_and_aliases_before_reading[directory-prefs.ini]` | `POSIX special files and unprivileged symlinks` |
| `46` | `tests/test_ui_setup_profile.py::test_manifest_refuses_special_files_and_aliases_before_reading[fifo-core_char_31.dat]` | `POSIX special files and unprivileged symlinks` |
| `47` | `tests/test_ui_setup_profile.py::test_manifest_refuses_special_files_and_aliases_before_reading[fifo-core_public__.yaml]` | `POSIX special files and unprivileged symlinks` |
| `48` | `tests/test_ui_setup_profile.py::test_manifest_refuses_special_files_and_aliases_before_reading[fifo-prefs.ini]` | `POSIX special files and unprivileged symlinks` |
| `49` | `tests/test_ui_setup_profile.py::test_manifest_refuses_special_files_and_aliases_before_reading[socket-core_char_31.dat]` | `POSIX special files and unprivileged symlinks` |
| `50` | `tests/test_ui_setup_profile.py::test_manifest_refuses_special_files_and_aliases_before_reading[socket-core_public__.yaml]` | `POSIX special files and unprivileged symlinks` |
| `51` | `tests/test_ui_setup_profile.py::test_manifest_refuses_special_files_and_aliases_before_reading[socket-prefs.ini]` | `POSIX special files and unprivileged symlinks` |
| `52` | `tests/test_ui_setup_profile.py::test_manifest_refuses_special_files_and_aliases_before_reading[link-inside-core_char_31.dat]` | `POSIX special files and unprivileged symlinks` |
| `53` | `tests/test_ui_setup_profile.py::test_manifest_refuses_special_files_and_aliases_before_reading[link-inside-core_public__.yaml]` | `POSIX special files and unprivileged symlinks` |
| `54` | `tests/test_ui_setup_profile.py::test_manifest_refuses_special_files_and_aliases_before_reading[link-inside-prefs.ini]` | `POSIX special files and unprivileged symlinks` |
| `55` | `tests/test_ui_setup_profile.py::test_manifest_refuses_special_files_and_aliases_before_reading[link-outside-core_char_31.dat]` | `POSIX special files and unprivileged symlinks` |
| `56` | `tests/test_ui_setup_profile.py::test_manifest_refuses_special_files_and_aliases_before_reading[link-outside-core_public__.yaml]` | `POSIX special files and unprivileged symlinks` |
| `57` | `tests/test_ui_setup_profile.py::test_manifest_refuses_special_files_and_aliases_before_reading[link-outside-prefs.ini]` | `POSIX special files and unprivileged symlinks` |
| `58` | `tests/test_ui_setup_profile.py::test_manifest_refuses_special_files_and_aliases_before_reading[link-broken-core_char_31.dat]` | `POSIX special files and unprivileged symlinks` |
| `59` | `tests/test_ui_setup_profile.py::test_manifest_refuses_special_files_and_aliases_before_reading[link-broken-core_public__.yaml]` | `POSIX special files and unprivileged symlinks` |
| `60` | `tests/test_ui_setup_profile.py::test_manifest_refuses_special_files_and_aliases_before_reading[link-broken-prefs.ini]` | `POSIX special files and unprivileged symlinks` |
| `61` | `tests/test_ui_setup_profile.py::test_manifest_refuses_special_files_and_aliases_before_reading[hardlink-core_char_31.dat]` | `POSIX special files and unprivileged symlinks` |
| `62` | `tests/test_ui_setup_profile.py::test_manifest_refuses_special_files_and_aliases_before_reading[hardlink-core_public__.yaml]` | `POSIX special files and unprivileged symlinks` |
| `63` | `tests/test_ui_setup_profile.py::test_manifest_refuses_special_files_and_aliases_before_reading[hardlink-prefs.ini]` | `POSIX special files and unprivileged symlinks` |
| `64` | `tests/test_ui_setup_profile.py::test_windows_name_aliases_are_refused_not_ignored[CORE_CHAR_31.DAT]` | `case-sensitive POSIX alias fabrication` |
| `65` | `tests/test_ui_setup_profile.py::test_windows_name_aliases_are_refused_not_ignored[PREFS.INI]` | `case-sensitive POSIX alias fabrication` |
| `66` | `tests/test_ui_setup_profile.py::test_windows_name_aliases_are_refused_not_ignored[core_public__.yaml.]` | `case-sensitive POSIX alias fabrication` |
| `67` | `tests/test_ui_setup_profile.py::test_windows_name_aliases_are_refused_not_ignored[prefs.ini ]` | `case-sensitive POSIX alias fabrication` |
