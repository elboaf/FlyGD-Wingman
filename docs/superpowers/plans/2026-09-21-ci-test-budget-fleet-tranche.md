# CI Test Budget — Fleet Consolidation Tranche Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut the five measured Fleet test hotspots roughly in half while preserving their distinct timing, authority, persistence, concurrency, signed-client, and maximum-resource contracts.

**Architecture:** First separate virtual scheduler coverage from representative durable filesystem crossings, then replace expensive Cartesian products with explicit boundary/pairwise contract sets. Keep source-admission persistence real, replace repeated lifecycle stress with symbolic capacity-boundary setup, use the existing mutation witnesses one final time, and delete those witnesses rather than moving them to another product-test tier. Register resource metadata now, but do not change any CI selector or introduce sharding until hosted timings authorize the later workflow plan.

**Tech Stack:** Python 3.11, pytest, JUnit XML, stdlib `xml.etree.ElementTree`, Rust settings codec prerequisite, GitHub Actions timing artifacts.

**Spec:** `docs/ci-test-budget-redesign.md`

## Global Constraints

- Required pull-request critical path remains capped at 300 seconds with a 240-second operating target; this tranche does not claim that target by itself.
- Complete Windows product verification remains capped at 600 seconds.
- Runtime and distinct contracts—not raw test count—decide success.
- Do not adopt pytest-xdist, change workflow selectors, add shards, create `extended.yml`, or add a permanent mutation job in this tranche.
- New `resource`, `extended`, and `mutation` markers must be registered under strict marker checking before use; only `resource` is assigned in this tranche.
- Current CI/build/release/autorelease commands still run all tests after this tranche. Marker-based selection belongs to the later workflow plan.
- Actual Node and the built release settings codec remain mandatory for full-suite verification; inspect all skips.
- Virtual scheduler products may use `_InMemoryStateStore`, but representative signed-client, JSON, capacity-validation, and atomic-file crossings must remain explicit.
- `tests/test_fleetsharing_source_admission.py` remains file-backed; its save-before-I/O assertions are load-bearing.
- Temporary production mutations must be reverted before every commit. No shipped `wingman/` file changes belong in this tranche.
- The 47 MB response test owns exact successful maximum decoding and a 75-second parent-process wall budget. Peak allocation is evidence, not a pass/fail threshold.
- Use symbolic limits such as `protocol.MAX_SOURCE_INTENTS`; do not copy `255`, `256`, or `257` as independent authorities.
- Preserve current test function parameters until the permanent mutation witnesses are retired; those witnesses call tests by name and signature.

## File Structure

### Created

- `docs/ci-test-budget-fleet-tranche-results.md` — exact baseline, per-task node counts/timings, mutation evidence, verification commands, hosted Windows result, and stop/go conclusion for the next plan.

### Modified

- `pyproject.toml` — strict pytest marker registration only; no selection defaults.
- `scripts/summarize_pytest_junit.py` — preserve `resource.*` JUnit properties in timing JSON.
- `tests/test_ci_timing.py` — timing-property parser and marker-ownership guards.
- `tests/test_fleetsharing_transport_resources.py` — classify and enforce the maximum-response resource contract.
- `tests/test_fleetsharing_cadence.py` — inject state stores, make collision horizons relative, shorten ordinary scenarios, and consolidate expensive matrices.
- `tests/test_fleetsharing_source_admission.py` — replace high-cost Cartesian products with explicit contract tuples.
- `tests/test_fleetsharing_worker_revision.py` — replace 260 identical durable lifecycles with three real recurrences plus symbolic metadata-boundary setup; remove mutation witnesses after final use.

### Deleted

- `tests/test_fleetsharing_worker_timing_mutations.py` — remove all 25 permanent mutation-of-test witnesses after final sensitivity verification.

## Interfaces Produced by This Tranche

Cadence produces these exact callable interfaces:

- `durable_cadence_store(path: Path) -> FileStore`
- `run_owner(*, publications=(), publisher=False, phase=0, latency=0.08, watch=False, duration=120, configure=lambda *_: None, telemetry_until=None, state_store=None)`
- `run_trace_owner(tmp_path, *, phase=0, watch=False, latency=0.08, duration=120, configure=lambda *_: None, publications=None, state_store=None)`
- `simultaneous_metadata(worker, client, timeline, *, offset=10) -> float`

`VirtualWait` adds a public test-only `start: float` field. `state_store=None` means `_InMemoryStateStore(PAIRED_STATE)`. Durable representatives pass a concrete store returned by `durable_cadence_store(path)`. `simultaneous_metadata` returns the exact scheduled due time so fairness assertions do not retain a hard-coded `1030`.

```python
# scripts/summarize_pytest_junit.py
# Additional summarize() field:
{
    "resource_evidence": [
        {
            "node_id": str,
            "properties": {str: str},  # only resource.* properties
        }
    ]
}
```

---

### Task 1: Resource Classification and Machine-Readable Evidence

**Files:**
- Modify: `pyproject.toml:115-116`
- Modify: `scripts/summarize_pytest_junit.py:47-101`
- Modify: `tests/test_ci_timing.py`
- Modify: `tests/test_fleetsharing_transport_resources.py:212-241`

**Interfaces:**
- Consumes: existing `summarize(input_path: Path) -> dict[str, object]`
- Produces: strict marker registration, `resource_evidence` timing JSON, and one `resource`-owned 47 MB test with a 75-second parent wall budget.

- [ ] **Step 1: Add a failing JUnit resource-property parser test**

Append this case to `tests/test_ci_timing.py`:

```python
def test_summarize_preserves_resource_properties(tmp_path: Path):
    junit_xml = tmp_path / "resource.xml"
    junit_xml.write_text(
        """<testsuite>
  <testcase classname="tests.test_resource" name="test_maximum" time="4.5">
    <properties>
      <property name="resource.subprocess_wall_seconds" value="4.25" />
      <property name="resource.memory_metric" value="traced_peak_bytes" />
      <property name="resource.memory_peak" value="1234" />
      <property name="unrelated" value="ignored" />
    </properties>
  </testcase>
</testsuite>""",
        encoding="utf-8",
    )

    result = summarize(junit_xml)

    assert result["resource_evidence"] == [
        {
            "node_id": "tests.test_resource.test_maximum",
            "properties": {
                "resource.memory_metric": "traced_peak_bytes",
                "resource.memory_peak": "1234",
                "resource.subprocess_wall_seconds": "4.25",
            },
        }
    ]
```

- [ ] **Step 2: Run the parser test and verify RED**

Run:

```bash
uv run --no-sync python -m pytest \
  tests/test_ci_timing.py::test_summarize_preserves_resource_properties -v
```

Expected: FAIL because `summarize()` has no `resource_evidence` key.

- [ ] **Step 3: Extend the timing summarizer minimally**

In `summarize()`, collect only `<property>` names beginning with `resource.`:

Initialize this list beside `files` and `slowest` before the testcase loop:

```python
resource_evidence: list[dict[str, object]] = []
```

Immediately after computing `node_id` inside the existing testcase loop, add:

```python
properties = {
    str(prop.get("name")): str(prop.get("value", ""))
    for prop in testcase.findall("./properties/property")
    if str(prop.get("name", "")).startswith("resource.")
}
if properties:
    resource_evidence.append(
        {"node_id": node_id, "properties": dict(sorted(properties.items()))}
    )
```

Add `"resource_evidence": resource_evidence` to the existing return dictionary without changing its other keys.

Add a `Resource evidence:` block to `_print_summary()` that prints each node and sorted property without changing existing output.

- [ ] **Step 4: Register the approved markers under strict checking**

Replace the current pytest section in `pyproject.toml` with:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--strict-markers"
markers = [
    "extended: distinct exhaustive or rare compatibility contracts",
    "resource: maximum-size, allocation, or performance probes",
    "mutation: optional test-strength checks that alter implementations",
]
```

Do not add a default `-m` expression.

- [ ] **Step 5: Add marker configuration and ownership guards**

Add to `tests/test_ci_timing.py`:

```python
def test_budget_markers_are_strict_and_registered():
    import tomllib

    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    pytest_config = config["tool"]["pytest"]["ini_options"]
    assert pytest_config["addopts"] == "--strict-markers"
    assert pytest_config["markers"] == [
        "extended: distinct exhaustive or rare compatibility contracts",
        "resource: maximum-size, allocation, or performance probes",
        "mutation: optional test-strength checks that alter implementations",
    ]


def test_only_maximum_response_owns_fleet_transport_resource_marker():
    target = ROOT / "tests" / "test_fleetsharing_transport_resources.py"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(target),
            "--collect-only",
            "-q",
            "-m",
            "resource",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "test_maximum_legal_response_actual_reader_and_codec_in_subprocess" in result.stdout
    assert "test_maximum_put_uses_actual_default_escaping_under_512k" not in result.stdout
    assert "test_memory_probe_falls_back_without_resource" not in result.stdout
```

Run these before adding the decorator. Expected: the configuration test passes after Step 4; the ownership test fails because nothing owns `resource`.

- [ ] **Step 6: Mark and budget the maximum-response test**

In `tests/test_fleetsharing_transport_resources.py`, add `import pytest` and:

```python
MAXIMUM_RESPONSE_RESOURCE_BUDGET_S = 75.0


@pytest.mark.resource
def test_maximum_legal_response_actual_reader_and_codec_in_subprocess(request):
    started = time.perf_counter()
    result = subprocess.run(
        [sys.executable, __file__, "--measure"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    wall_seconds = time.perf_counter() - started
    assert result.returncode == 0, result.stderr
    evidence = json.loads(result.stdout)
    evidence["subprocess_wall_seconds"] = wall_seconds
    for name in (
        "subprocess_wall_seconds",
        "memory_metric",
        "memory_peak",
        "raw_bytes",
        "rows",
        "observations",
    ):
        request.node.user_properties.append(
            (f"resource.{name}", str(evidence[name]))
        )
    assert wall_seconds <= MAXIMUM_RESPONSE_RESOURCE_BUDGET_S, (
        "maximum response resource budget exceeded: "
        + json.dumps(evidence, sort_keys=True)
    )
    print(evidence)
    assert evidence["raw_bytes"] == 47022137
    assert evidence["rows"] == LIMITS["get_rows"]
```

Keep the 300-second subprocess timeout as deadlock protection.

- [ ] **Step 7: Prove the wall budget fails with evidence**

Temporarily set `MAXIMUM_RESPONSE_RESOURCE_BUDGET_S = 0.0`, run:

```bash
uv run --no-sync python -m pytest \
  tests/test_fleetsharing_transport_resources.py -m resource -q -s
```

Expected: FAIL with `maximum response resource budget exceeded` and JSON containing wall time and memory evidence. Restore `75.0` immediately and confirm `git diff` contains no zero budget.

- [ ] **Step 8: Run focused GREEN verification**

```bash
uv run --no-sync python -m pytest tests/test_ci_timing.py -q
uv run --no-sync python -m pytest \
  tests/test_fleetsharing_transport_resources.py -m "not resource" -q
uv run --no-sync python -m pytest \
  tests/test_fleetsharing_transport_resources.py -m resource \
  -q -s --junitxml=/tmp/fleet-resource.xml
uv run --no-sync python scripts/summarize_pytest_junit.py \
  /tmp/fleet-resource.xml /tmp/fleet-resource-timing.json
```

Expected selection: ordinary command selects 2 and deselects 1; resource command selects 1 and deselects 2. Summary JSON contains one `resource_evidence` row.

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml scripts/summarize_pytest_junit.py \
  tests/test_ci_timing.py tests/test_fleetsharing_transport_resources.py
git commit -m "test: classify Fleet transport resource probe"
```

---

### Task 2: Separate Cadence Scheduler and Persistence Seams

**Files:**
- Modify: `tests/test_fleetsharing_cadence.py:1-260,363-420,722-770,1560-1595`

**Interfaces:**
- Consumes: `_InMemoryStateStore(PAIRED_STATE)` from `tests/test_fleetsharing_worker.py`; `FileStore` from `tests/test_fleetsharing_worker_state4.py`.
- Produces: injected `state_store` runners and `durable_cadence_store(path)` used by retained durable representatives.

- [ ] **Step 1: Change existing tests first to establish RED seam expectations**

Import `_InMemoryStateStore` beside `_worker`. In `test_due_independent_bucket_does_not_wait_for_post_operation_poll`, add:

```python
assert isinstance(client.store, _InMemoryStateStore)
```

Change `test_publisher_trace_crosses_real_signed_client` to accept `tmp_path` and call:

```python
store = durable_cadence_store(tmp_path / "publisher-trace.json")
client, _, _, _ = run_owner(
    publisher=True,
    duration=8,
    state_store=store,
)
assert client.store is store
```

Run both tests. Expected: one FAIL because the default is `FileStore`; one FAIL with unexpected `state_store` argument.

- [ ] **Step 2: Add explicit store injection**

Add:

```python
def durable_cadence_store(path):
    store = FileStore(path)
    store.save(PAIRED_STATE)
    return store
```

Add `state_store=None` to `run_owner` after `telemetry_until`. Replace its temporary-directory/store initialization with:

```python
timeline = VirtualWait(1000 + phase, 1000 + duration)
store = state_store or _InMemoryStateStore(PAIRED_STATE)
client = TimedRelay(timeline, store, latency, publications)
```

Remove `tempfile`, `TemporaryDirectory`, and `directory.cleanup()` from this runner; retain `assert worker.stop()` in `finally`.

Add `state_store=None` to `run_trace_owner` after `publications`. Replace its store initialization with:

```python
timeline = VirtualWait(1000 + phase, 1000 + duration)
store = state_store or _InMemoryStateStore(PAIRED_STATE)
relay = TraceRelay(
    timeline,
    store,
    scripted_combat_trace(duration) if publications is None else publications,
    latency,
)
```

- [ ] **Step 3: Keep one explicit durable receiver crossing**

In `test_external_put_trace_preserves_original_origins_and_nullable_values`, pass:

```python
state_store=durable_cadence_store(tmp_path / "external-trace.json")
```

Keep `test_timed_relay_captures_valid_combat_rows_at_json_boundary` file-backed as written. Together with the durable publisher test, these retain PUT, GET, JSON, capacity validation, save-before-I/O, and atomic-file crossings.

- [ ] **Step 4: Run all cadence tests without changing case count**

```bash
uv run --no-sync python -m pytest \
  tests/test_fleetsharing_cadence.py -q --durations=30 \
  --junitxml=/tmp/cadence-seams.xml
uv run --no-sync python scripts/summarize_pytest_junit.py \
  /tmp/cadence-seams.xml /tmp/cadence-seams.json
uv run --no-sync python -m pytest \
  tests/test_fleetsharing_cadence.py --collect-only -q
```

Expected: all 139 current nodes still collect and pass. Record before/after file sums in the results document; do not claim Windows speed from Linux evidence.

- [ ] **Step 5: Commit**

```bash
git add tests/test_fleetsharing_cadence.py
git commit -m "test: split Fleet cadence persistence seams"
```

---

### Task 3: Consolidate Cadence Matrices and Scenario Horizons

**Files:**
- Modify: `tests/test_fleetsharing_cadence.py:56-99,308-507,879-920,970-1160,1311-1478,1596-1615`
- Test: `tests/test_fleetsharing_worker_timing_mutations.py`

**Interfaces:**
- Consumes: Task 2 runner injection.
- Produces: explicit pairwise parameter sets and relative collision scheduling while keeping existing test function names/signatures for Task 6 mutation probes.

- [ ] **Step 1: Make collision scheduling relative before shortening horizons**

Add `self.start = start` in `VirtualWait.__init__` and replace `simultaneous_metadata` with:

```python
def simultaneous_metadata(worker, client, timeline, *, offset=10):
    due_at = timeline.start + offset

    def due():
        for key in worker._due:
            worker._due[key] = timeline.now
        worker._renew_at = timeline.now

    timeline.at(due_at, due)
    return due_at
```

Remove the `due=1030` default from `assert_scenario_fairness`; require callers to pass the exact due time. Existing repeated-burst calls continue passing `1030`, `1060`, and `1090` explicitly.

- [ ] **Step 2: Replace the two period/phase/skew Cartesian decorators**

For both `test_source_phase_and_small_clock_skew_do_not_withdraw` and `test_expiring_proof_refresh_progress_is_independent_of_local_publication`, use:

```python
@pytest.mark.parametrize(
    "period,phase,skew",
    [
        (5, 0, -0.5),
        (6, 0, 0.5),
        (5, 2, 0.5),
        (6, 2, -0.5),
        (5, 4, -0.5),
        (6, 4, 0.5),
    ],
)
```

This covers both periods and skew signs at every phase, plus both signs for each period.

- [ ] **Step 3: Replace the expensive publisher/receiver products**

Use these exact tuples:

Apply this decorator to `test_healthy_sparse_publication_stays_live_in_quiet_receiver`:

```python
@pytest.mark.parametrize(
    "phase,watch,latency",
    [
        (0, False, 0.025),
        (0.2, True, 0.08),
        (0.5, False, 0.12),
        (0.9, False, 0.08),
        (0.9, True, 0.12),
    ],
)
```

Apply this decorator to `test_source_watch_and_simultaneous_metadata_renewal_do_not_starve_read`:

```python
@pytest.mark.parametrize(
    "phase,latency",
    [
        (0, 0.025),
        (0, 0.12),
        (0.5, 0.08),
        (0.9, 0.12),
    ],
)
```

Apply this decorator to `test_current_receiver_matches_exact_freshness_without_local_publication`:

```python
@pytest.mark.parametrize(
    "phase,watch,latency",
    [
        (0, True, 0.025),
        (0.2, False, 0.12),
        (0.5, True, 0.08),
        (0.9, False, 0.025),
        (0.9, True, 0.12),
    ],
)
```

Pass `duration=20` to both publisher and receiver runners in these three families. Pass `end=timeline.end` into mixed/healthy bound assertions. For fairness, pass `due=client.timeline.start + 10` or `due=relay.timeline.start + 10`.

- [ ] **Step 4: Reduce renewed-source latency combinations**

Replace the 2 × 4 product with:

```python
@pytest.mark.parametrize(
    "changing,latency",
    [
        (False, 0.08),
        (True, 0.2),
        (False, 0.6),
        (True, 0.6),
    ],
)
```

Keep `duration=60`; proof renewal recurrence is the contract.

- [ ] **Step 5: Remove the duplicate publisher-plus-receiver delayed family**

Delete `test_full_delayed_response_is_honestly_stale_or_expired`. Keep `test_current_receiver_delayed_get_cannot_rejuvenate_old_payload`; it owns stale/expired response behavior through the external-trace oracle and real GET client path. Keep `test_publisher_trace_crosses_real_signed_client` as the signed PUT owner.

Do not collapse the inexpensive pure boundary tables. They provide precise node IDs and are not the runtime problem.

- [ ] **Step 6: Run permanent mutation witnesses before and after consolidation**

Run:

```bash
uv run --no-sync python -m pytest \
  tests/test_fleetsharing_worker_timing_mutations.py::test_known_scenario_classes_detect_even_never_serviced_operations \
  tests/test_fleetsharing_worker_timing_mutations.py::test_healthy_bounds_reject_throttled_but_recovering_snapshots \
  tests/test_fleetsharing_worker_timing_mutations.py::test_expiry_coverage_detects_refresh_stopping_after_three_successes \
  tests/test_fleetsharing_worker_timing_mutations.py::test_external_trace_oracle_kills_wrong_projection \
  tests/test_fleetsharing_worker_timing_mutations.py::test_external_trace_oracle_is_independent_of_display_classification \
  -q
```

Expected: PASS means every deliberately weakened implementation is still detected by the retained direct tests. If a witness fails because a deleted parameter row was its only detector, restore that row or choose another representative before proceeding.

- [ ] **Step 7: Run GREEN cadence verification and record exact inventory**

```bash
uv run --no-sync python -m pytest \
  tests/test_fleetsharing_cadence.py -q --durations=30 \
  --junitxml=/tmp/cadence-consolidated.xml
uv run --no-sync python scripts/summarize_pytest_junit.py \
  /tmp/cadence-consolidated.xml /tmp/cadence-consolidated.json
uv run --no-sync python -m pytest \
  tests/test_fleetsharing_cadence.py --collect-only -q
```

Expected inventory is approximately 75 nodes, not a pass criterion. Record the actual count and timing. All contract representatives and mutation witnesses must pass.

- [ ] **Step 8: Commit**

```bash
git add tests/test_fleetsharing_cadence.py
git commit -m "test: consolidate Fleet cadence contracts"
```

---

### Task 4: Consolidate Source-Admission Completion and Error Products

**Files:**
- Modify: `tests/test_fleetsharing_source_admission.py:650-1570`

**Interfaces:**
- Consumes: existing `publication_rig`, `CompletionInstallBarrier`, `error_install_case`, and durable `PublicationClient`.
- Produces: explicit pairwise completion/error tuples with every work kind, response class, invalidation class, save boundary, and current-authority control represented.

- [ ] **Step 1: Replace off-completion authority product with nine tuples**

Use:

```python
@pytest.mark.parametrize(
    "http_error,authority",
    [
        (False, "deadline_equal"),
        (True, "deadline_over"),
        (False, "deadline_extended"),
        (False, "approved_capabilities"),
        (False, "session_approved_capabilities"),
        (False, "acknowledged_capabilities"),
        (False, "auth"),
        (False, "new_intent"),
        (False, "new_session"),
    ],
)
```

Keep the function body and all authority-specific assertions unchanged.

- [ ] **Step 2: Replace obsolete error installation with six tuples**

```python
@pytest.mark.parametrize(
    "kind,error,invalidation",
    [
        ("publication", (403, "forbidden"), "new_intent"),
        ("off", (403, "forbidden"), "lifecycle"),
        ("publication", (401, "unauthorized"), "auth"),
        ("off", (401, "unauthorized"), "shared_rights"),
        ("publication", (503, "service_unavailable"), "lifecycle"),
        ("off", (503, "service_unavailable"), "new_intent"),
    ],
)
```

This retains both work kinds, all three HTTP classes, and all four invalidation modes.

- [ ] **Step 3: Replace durable 401 and original-source completion products**

Use:

```python
@pytest.mark.parametrize(
    "kind,boundary,replacement",
    [
        ("publication", "during_save", "new_intent"),
        ("off", "during_save", "lifecycle"),
        ("publication", "after_save", "lifecycle"),
        ("off", "after_save", "new_intent"),
    ],
)
```

For `test_original_source_guards_actual_completion_install`, use six `revoke=True` combinations across `publication`/`inactive` and `None`/403/503, plus one current control:

```python
[
    (kind, error, True)
    for kind in ("publication", "inactive")
    for error in (None, (403, "forbidden"), (503, "service_unavailable"))
] + [("publication", None, False)]
```

- [ ] **Step 4: Replace success-status, post-save reset, and leaf-lock products**

Use these exact sets:

```python
# test_publication_success_status_install_keeps_original_intent
[
    ("publication", True),
    ("off", True),
    ("off_refused", True),
    ("publication", False),
]
```

```python
# test_original_source_guards_post_save_401_reset
[
    ("publication", "during_save", True),
    ("inactive", "during_save", True),
    ("publication", "reset_acquisition", True),
    ("inactive", "reset_acquisition", True),
    ("publication", "reset_acquisition", False),
]
```

```python
# test_completion_leaf_lock_order_and_nonconsuming_costs
[
    ("publication", None),
    ("off", None),
    ("publication", (403, "forbidden")),
    ("inactive", (401, "unauthorized")),
    ("off", (401, "unauthorized")),
    ("off", (503, "service_unavailable")),
]
```

- [ ] **Step 5: Run temporary production mutation probes**

With a clean index, apply each mutation separately in `wingman/fleetsharing/worker.py`, run the named retained family, then `git restore wingman/fleetsharing/worker.py` before the next mutation:

1. Replace the post-client `self._check(fence, work=work)` immediately before `_check_publication_completion` with `pass`; retained obsolete error/current completion cases must fail.
2. Replace each publish branch calling `self._check_publication_completion(selected, fence, work, receipt)` with a no-op branch; retained original-source completion cases must fail.
3. In `validate_publication()`, bypass `_check_locked(fence, work=work)`; retained final-authority cases must fail.
4. In the 401 completion path, bypass the original-source/current-intent check that precedes durable reset; retained post-save reset cases must fail.

After every probe:

```bash
git diff -- wingman/fleetsharing/worker.py
git restore wingman/fleetsharing/worker.py
git diff --exit-code -- wingman/fleetsharing/worker.py
```

A probe that fails during setup or at an unrelated assertion is not evidence; restore the relevant deleted row.

- [ ] **Step 6: Run focused GREEN verification**

```bash
uv run --no-sync python -m pytest \
  tests/test_fleetsharing_source_admission.py \
  -q --durations=30 --junitxml=/tmp/source-admission-a.xml
```

Record the actual node count and timing; do not commit any production diff.

- [ ] **Step 7: Commit**

```bash
git add tests/test_fleetsharing_source_admission.py
git commit -m "test: consolidate Fleet completion authority contracts"
```

---

### Task 5: Consolidate Source-Admission Barrier and Member Products

**Files:**
- Modify: `tests/test_fleetsharing_source_admission.py:190-620,1640-2026`

**Interfaces:**
- Consumes: Task 4 explicit completion tuples and existing durable rig.
- Produces: separated barrier/authority coverage and representative member/right classifications.

- [ ] **Step 1: Replace the 5 × 5 barrier/change product with nine cases**

Use:

```python
@pytest.mark.parametrize(
    "barrier,change",
    [
        ("unwrap", "source"),
        ("save", "source"),
        ("signing", "source"),
        ("prehook", "source"),
        ("after_start", "source"),
        ("signing", "off"),
        ("signing", "timing"),
        ("signing", "source_control"),
        ("signing", "automatic"),
    ],
)
```

Delete `test_source_invalidation_before_or_after_real_hook`; its signing/source and after-start/source contracts now live in this table. In `test_source_control_generation_fences_selected_and_completed_put`, retain only the `after_start` row because signing is represented above.

- [ ] **Step 2: Reduce inactivity and retained-conflict classifications**

For `test_only_proven_source_inactivity_withdraws_without_anchor`, retain:

```python
[
    ("empty", True),
    ("inactive", True),
    ("zero_live", False),
    ("unavailable", False),
    ("stale", False),
    ("invalid_m", False),
]
```

Drop `legacy`, represented by multi-member uncertainty, and `revoked`, represented by source-revocation completion tests.

For retained evidence conflicts, keep:

```python
["row_deadline", "effect_deadline", "same_m_empty"]
```

`same_m_inactive` has the same retained-evidence authority and external effect as `same_m_empty`.

- [ ] **Step 3: Reduce the multi-member permission product without losing classifications**

Replace the `kind × eligible_bob` product with one tuple per kind:

```python
@pytest.mark.parametrize(
    "kind,withdraw,eligible_bob",
    [
        ("known_inactive", True, False),
        ("one_direction_available", True, True),
        ("unavailable", False, True),
        ("legacy", False, True),
        ("nan_deadline", False, True),
        ("invalid_numeric", False, True),
        ("missing_observation_id", False, True),
        ("future_activity", False, True),
        ("unknown_owner", False, True),
    ],
)
```

`test_conflicting_member_beside_inactive_is_not_hidden_by_permission` remains the independent permission-filtered conflict contract.

- [ ] **Step 4: Reduce final held-rights product**

Use:

```python
@pytest.mark.parametrize(
    "field,kind",
    [
        ("approved_capabilities", "combat"),
        ("session_approved_capabilities", "combat"),
        ("acknowledged_capabilities", "combat"),
        ("approved_capabilities", "inactive"),
        ("acknowledged_capabilities", "off"),
    ],
)
```

Retain every held-rights field and every publication kind.

- [ ] **Step 5: Keep the deadline rollback row that owns persistence**

For `test_cached_permission_deadline_expires_after_signing_without_utc_renewal`, retain only `rollback=True`; the ordinary deadline path remains covered by direct deadline tests. Preserve every assertion about restored durable state.

- [ ] **Step 6: Run barrier and rights mutation probes**

Temporarily weaken one production check at a time:

1. In `before_send`, change `elif selected.source.admit_start(validate_publication) is not True:` to `elif False:`; the signing/source representative must fail.
2. Remove the post-start `_check(fence, work=work)` before client completion; the after-start/source representative must fail.
3. In `_combat_disclosure`, omit each rights collection in turn; its retained `combat` representative must fail.
4. Allow uncertain member classification to fall through to inactivity withdrawal; at least one retained uncertain-member row must fail.

Restore `wingman/fleetsharing/worker.py` after each probe and require a clean production diff before continuing.

- [ ] **Step 7: Run complete source-admission GREEN verification**

```bash
uv run --no-sync python -m pytest \
  tests/test_fleetsharing_source_admission.py \
  -q --durations=30 --junitxml=/tmp/source-admission-final.xml
uv run --no-sync python scripts/summarize_pytest_junit.py \
  /tmp/source-admission-final.xml /tmp/source-admission-final.json
uv run --no-sync python -m pytest \
  tests/test_fleetsharing_source_admission.py --collect-only -q
```

Expected inventory is near 120 nodes, not a pass criterion. Record the actual count and timing.

- [ ] **Step 8: Commit**

```bash
git add tests/test_fleetsharing_source_admission.py
git commit -m "test: consolidate Fleet source admission contracts"
```

---

### Task 6: Replace Repeated Source-Retirement Stress With Symbolic Boundaries

**Files:**
- Modify: `tests/test_fleetsharing_worker_revision.py:322-385,512-600`
- Read: `wingman/fleetsharing/protocol.py:33`
- Read: `wingman/fleetsharing/worker.py:2044-2055,2768-2781`
- Read: `wingman/fleetsharing/scheduling.py:54-59`

**Interfaces:**
- Consumes: `protocol.MAX_SOURCE_INTENTS`, `_source_work_key()`, `_prune_source_work()`, scheduler metadata maps.
- Produces: three real durable lifecycle recurrences and direct below/at/above metadata-pruning coverage under the existing `test_terminal_only_source_retirement_bounds_observation_and_retry_metadata` name.

- [ ] **Step 1: Split three real lifecycles from symbolic metadata boundaries**

Rename the existing `test_terminal_only_source_retirement_bounds_observation_and_retry_metadata` function to `test_terminal_source_retirement_repeats_real_durable_lifecycle` and change only its `for n in range(260):` line to `for n in range(3):`. Keep its complete file-backed setup and every assertion inside the loop: receipt URL observed, dismissal succeeds, stable retry/failure/served metadata remains, and read deadline never moves backward. Keep its final observation/generation/scheduler pruning assertions as the end-to-end recurrence check.

Recreate the original function name with parameters `(tmp_path, retired_count)` and apply this decorator:

```python
@pytest.mark.parametrize(
    "retired_count",
    [
        p.MAX_SOURCE_INTENTS - 1,
        p.MAX_SOURCE_INTENTS,
        p.MAX_SOURCE_INTENTS + 1,
    ],
)
```

Replace the function body with the following code, indented once beneath the existing function definition. It uses one real persistent authority without running retired commands through HTTP:

```python
from tests.fleetsharing_worker_control_helpers import ControlRelay
from tests.test_fleetsharing_worker_state4 import file_rig

worker, _, store, mono = file_rig(tmp_path)
relay = ControlRelay(worker, store)
reply = relay.reply

def unavailable(request, saved):
    if "/receipts/" in request.full_url:
        return {"protocol": 2, "error": "service_unavailable"}, 503
    return reply(request, saved)

relay.reply = unavailable
worker.resume_pending()
drive(worker, mono, 3)
assert worker.request_source_stop(
    UUID, expected_generation=0, expected_automatic=None
)
drive(worker, mono, 3)
persistent = s.load(store.path).pending_source_commands[0]

retired = {
    f"{number + 1:08x}-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    for number in range(retired_count)
}
stable = worker._source_work_key(persistent)
stale_keys = {f"source:stop:{source_id}" for source_id in retired}
worker._source_observe = retired | {persistent.source_id}
worker._source_generations = {source_id: 1 for source_id in retired}
worker._source_generations[persistent.source_id] = 7

unrelated = "automatic:stable"
deadline = mono[0] + 100000
for key in stale_keys | {stable, unrelated}:
    worker._scheduler.retry_at[key] = deadline
    worker._scheduler.failures[key] = 6
    worker._scheduler._served[key] = 99
read_deadline = worker._scheduler.deadlines["read"]

worker.iterate_once()

assert worker._source_observe == {persistent.source_id}
assert worker._source_generations == {persistent.source_id: 7}
for metadata in (
    worker._scheduler.retry_at,
    worker._scheduler.failures,
    worker._scheduler._served,
):
    assert all(not key.startswith("source:") or key == stable for key in metadata)
assert worker._scheduler.retry_at[unrelated] == deadline
assert worker._scheduler.failures[unrelated] == 6
assert worker._scheduler._served[unrelated] == 99
assert worker._scheduler.deadlines["read"] >= read_deadline
```

- [ ] **Step 2: Verify RED with each pruning mechanism removed**

Run the rewritten original test after each temporary mutation:

1. Remove `self._source_observe.intersection_update(command.source_id for command in self._state.pending_source_commands)` in `_prune_source_work`; expect observation assertion failure.
2. Remove `self._scheduler.retain("source:", {self._source_work_key(c) for c in self._state.pending_source_commands})`; expect source scheduler metadata assertion failure.
3. Remove the `_source_generations` dictionary retention in the owner turn at `wingman/fleetsharing/worker.py:2050-2054`; expect generation assertion failure.

Restore `wingman/fleetsharing/worker.py` after every probe.

- [ ] **Step 3: Run GREEN worker-revision verification**

```bash
uv run --no-sync python -m pytest \
  tests/test_fleetsharing_worker_revision.py::test_terminal_source_retirement_repeats_real_durable_lifecycle \
  tests/test_fleetsharing_worker_revision.py::test_terminal_only_source_retirement_bounds_observation_and_retry_metadata \
  -q --durations=0
```

Expected: four nodes pass—one three-cycle durable recurrence plus three symbolic boundary rows.

- [ ] **Step 4: Run the existing source-metadata mutant against the replacement**

```bash
uv run --no-sync python -m pytest \
  tests/test_fleetsharing_worker_revision.py::test_revision_guards_kill_in_memory_mutants[source_metadata] \
  -q
```

Expected: PASS, meaning the replacement test still kills removal of source-observation pruning.

- [ ] **Step 5: Commit**

```bash
git add tests/test_fleetsharing_worker_revision.py
git commit -m "test: target Fleet source retirement capacity"
```

---

### Task 7: Run and Retire Permanent Mutation Witnesses

**Files:**
- Delete: `tests/test_fleetsharing_worker_timing_mutations.py`
- Modify: `tests/test_fleetsharing_worker_revision.py:512-600`

**Interfaces:**
- Consumes: final direct regressions from Tasks 3–6.
- Produces: no committed mutation-of-test corpus; direct product regressions remain.

- [ ] **Step 1: Run all 25 timing witnesses one final time**

```bash
uv run --no-sync python -m pytest \
  tests/test_fleetsharing_worker_timing_mutations.py -q
```

Expected: 25 passed. Each pass means its deliberately altered implementation was detected. Save terminal output in the results document; do not commit generated logs.

- [ ] **Step 2: Run all eight revision witnesses one final time**

```bash
uv run --no-sync python -m pytest \
  tests/test_fleetsharing_worker_revision.py::test_revision_guards_kill_in_memory_mutants \
  -q
```

Expected: 8 passed, including `source_metadata` against Task 6’s replacement.

- [ ] **Step 3: Delete the permanent witnesses**

```bash
rm tests/test_fleetsharing_worker_timing_mutations.py
```

Delete `test_revision_guards_kill_in_memory_mutants` and imports used only by that function. Do not add `@pytest.mark.mutation`; the approved decision is deletion after temporary use.

- [ ] **Step 4: Run direct product regressions after deletion**

```bash
uv run --no-sync python -m pytest \
  tests/test_fleetsharing_worker_timing.py \
  tests/test_fleetsharing_worker_revision.py \
  tests/test_fleetsharing_cadence.py \
  -q --durations=30
```

Expected: all direct product regressions pass and collection references no deleted module/function.

- [ ] **Step 5: Check packaging/source guards for deleted references**

```bash
rg -n "test_fleetsharing_worker_timing_mutations|test_revision_guards_kill_in_memory_mutants" . \
  --glob '!docs/history/**' \
  --glob '!docs/ci-test-budget-fleet-tranche-results.md'
```

Expected: no active source, workflow, or test references. Historical documentation may retain its original names.

- [ ] **Step 6: Commit**

```bash
git add -A tests/test_fleetsharing_worker_timing_mutations.py \
  tests/test_fleetsharing_worker_revision.py
git commit -m "test: remove temporary Fleet mutation witnesses"
```

---

### Task 8: Tranche Evidence, Full Verification, and Stop/Go Report

**Files:**
- Create: `docs/ci-test-budget-fleet-tranche-results.md`
- Verify: all files changed in Tasks 1–7

**Interfaces:**
- Consumes: JUnit/timing JSON from each task and the reference CI evidence named in the spec.
- Produces: an auditable tranche result and the measured input for the separate remaining-hotspot plan.

- [ ] **Step 1: Write the results document from actual evidence**

Create the results document with these exact sections: `Source identities`, `Contract changes`, `Mutation evidence`, `Local timing evidence`, `Hosted Windows evidence`, and `Stop/go conclusion`. Under source identities, record the literal outputs of `git merge-base origin/main HEAD` and `git rev-parse HEAD`, plus Windows reference run `35534240008` at `78adb17a8346f4810f48863dd10a87c386091948`. Use tables for before/after nodes, retained representatives, mutation commands/results, and local file timings.

Do not enter estimates in result fields. If hosted Windows evidence is unavailable, write `Hosted Windows evidence unavailable; workflow and sharding planning remain unauthorized.`

- [ ] **Step 2: Install full-suite prerequisites in this worktree**

```bash
uv sync --locked --extra dev
node --version
cargo build --locked --release \
  --manifest-path packaging/settings-codec/Cargo.toml \
  --target-dir packaging/settings-codec/target
uv run --no-sync python -c "import os, pathlib, shutil; from wingman.evesettings import codec; name = 'wingman-settings-codec' + ('.exe' if os.name == 'nt' else ''); source = pathlib.Path('packaging/settings-codec/target/release') / name; target = pathlib.Path('packaging/bin') / name; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target); assert codec.codec_available(), 'Native integration tests require the built codec'"
```

- [ ] **Step 3: Run focused required and resource evidence**

```bash
uv run --no-sync python -m pytest \
  tests/test_fleetsharing_cadence.py \
  tests/test_fleetsharing_source_admission.py \
  tests/test_fleetsharing_worker_revision.py \
  tests/test_fleetsharing_transport_resources.py \
  tests/test_ci_timing.py \
  -m "not resource" -q -rs --durations=50 \
  --junitxml=/tmp/fleet-required.xml
uv run --no-sync python scripts/summarize_pytest_junit.py \
  /tmp/fleet-required.xml /tmp/fleet-required.json

uv run --no-sync python -m pytest \
  tests/test_fleetsharing_transport_resources.py \
  -m resource -q -s --durations=0 \
  --junitxml=/tmp/fleet-resource.xml
uv run --no-sync python scripts/summarize_pytest_junit.py \
  /tmp/fleet-resource.xml /tmp/fleet-resource.json
```

Inspect selected/deselected counts and `resource_evidence`.

- [ ] **Step 4: Run full local verification**

```bash
uv run --no-sync python -m pytest tests/ -q -rs --durations=50 \
  --junitxml=/tmp/fleet-tranche-full.xml
uv run --no-sync python scripts/summarize_pytest_junit.py \
  /tmp/fleet-tranche-full.xml /tmp/fleet-tranche-full.json
node scripts/js_smoke.js
cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
git diff --check
```

Expected: no failures; inspect every skip and reject Node/codec availability skips.

- [ ] **Step 5: Inspect final scope and accidental leftovers**

```bash
git status --short
git diff --stat HEAD~7..HEAD
git diff --check HEAD~7..HEAD
rg -n "DEBUG-|MAXIMUM_RESPONSE_RESOURCE_BUDGET_S = 0|TODO|TBD" \
  pyproject.toml scripts tests docs/ci-test-budget-fleet-tranche-results.md
```

Expected: no debug instrumentation, zero budget, placeholders, production changes, workflow changes, or generated XML/JSON tracked.

- [ ] **Step 6: Obtain hosted Windows evidence before budget claims**

After explicit authorization to publish the implementation branch, trigger its ordinary PR CI. Resolve the branch and run ID instead of hand-substituting them:

```bash
BRANCH=$(git branch --show-current)
gh run list -R elboaf/FlyGD-Wingman --branch "$BRANCH" \
  --workflow ci.yml --limit 5
RUN_ID=$(gh run list -R elboaf/FlyGD-Wingman --branch "$BRANCH" \
  --workflow ci.yml --limit 1 --json databaseId --jq '.[0].databaseId')
gh run view "$RUN_ID" -R elboaf/FlyGD-Wingman --json jobs,url,headSha
```

Download `pytest-evidence-windows-latest`, compare the five targeted file totals and Windows Test-step wall time to run `35534240008`, and record exact URLs/SHA. Do not describe Linux timing as Windows improvement.

- [ ] **Step 7: Commit the evidence report**

```bash
git add docs/ci-test-budget-fleet-tranche-results.md
git commit -m "docs: record Fleet test budget tranche"
```

- [ ] **Step 8: Stop at the tranche boundary**

Do not implement broader hotspot reductions, marker selectors, budget manifests, nightly workflows, or Windows shards in this plan. Use the final Windows ranking to write the next implementation plan and seek review.
