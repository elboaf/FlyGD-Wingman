# Broad CI waste reduction — Stage A results

This ledger is cumulative. This first entry freezes the merged PR #290 baseline
for Stage A. Candidate implementation, mutation, local endpoint, and candidate
hosted fields intentionally remain unfilled until their owning tasks execute.
Elapsed values below are observations only; none is a speedup, lower bound, p95,
throughput, job, or critical-path claim.

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
checks (`2101 * 2102 / 2`). The future bounded-oracle candidate result is not
prefilled here.

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

## Identity, order, and structure verification

The five in-scope source files are byte-equal to merged `463bccb0`:

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
Current names, signatures, decorators, markers, and collected order are exact
baseline data, with zero current signature differences.

Task 2 reran the identity/signature gate against a fresh `463bccb0` archive.
All `313` five-file identities and sorted marker rows are exactly equal with
ordered hash
`a21d48abcdfaeb9b2b33ab5e1b089f5da4e692f01bebe94c104908728235eaef`;
all current test names, signatures, decorators, parameters, IDs, and markers are
unchanged. The Preview consumer JUnit independently confirms the frozen `388`
identity order/hash. Only the intended three Preview test files differ among the
eight `runtime_pump` consumers.

The future endpoint gate must permit exactly four—and only four—signature
substitutions in `tests/test_shoot_screens.py`, each from
`(tmp_path, monkeypatch)` to `(preview_narrow_failure_walk)`:

- `test_walk_clears_device_metrics_even_when_narrow_screenshot_fails`;
- `test_walk_narrow_setup_runs_inside_device_metrics_override_on_failure`;
- `test_walk_failure_path_records_set_eval_attempt_clear_in_order`;
- `test_walk_failure_path_records_attempt_before_clear_not_only_clear`.

An empty, missing, or fifth candidate change will fail that future comparison.

## Complete local endpoint

Not run in Task 1. The locked development environment was synchronized only
after the existing worktree environment lacked pytest. Source collection,
artifact parsing, the exact Preview four, rolling-one instrumentation, and the
normal 35 screenshot operation set are green. The retained PR #290 artifacts,
not a new local full-suite invocation, establish the frozen complete baseline.
Task 4 owns fresh Node, release-codec, full pytest, Cargo, Ruff, documentation,
and complete endpoint evidence; no candidate endpoint outcome is prefilled.

## Reviews, scope, restoration, and leftovers

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

Task 1 concern: the worktree initially lacked pytest, so
`uv sync --locked --extra dev` installed the locked development environment
before collection. The release codec remains absent and no local complete suite
is claimed. This is not a baseline defect because both retained platform
artifact arrays have exact outcomes and no codec skip; Task 4 must build/install
the codec before its fresh full-suite endpoint.

## Publication stop and hosted evidence

This task reads already retained, previously authorized PR #290 baseline evidence
only. It did not push, update a PR, dispatch/rerun Actions, download a new
artifact, or mutate any remote. There is no Stage A candidate hosted outcome.
Candidate publication and hosted comparison remain stopped pending separate
explicit authorization.

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
