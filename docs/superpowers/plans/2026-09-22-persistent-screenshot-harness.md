# Persistent Screenshot Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace repeated one-shot Node launches in the screenshot and Fittings page tests with isolated persistent workers without deleting any observable contract.

**Architecture:** Keep one `NodeScenarioWorker` process per harness family and create a fresh VM, DOM, bridge queues, timers, rejection listener, and console for every request. Static markup and production-source paths are startup inputs; generated shooter expressions, fixture payloads, regression selectors, screenshots, and scenario names remain request payloads. This tranche preserves every existing business-scenario identity and separates process-overhead work from the subsequent matrix-consolidation plan.

**Tech Stack:** Python 3.11, pytest 9, Node.js 26, CommonJS, `node:vm`, line-delimited JSON, existing `tests.node_scenario_worker.NodeScenarioWorker`.

**Spec:** `docs/ci-test-budget-redesign.md`

## Global Constraints

- Current authority is merged `main` at `c4a2b2060de8f8317e61a732708a9b5bd88beb98`; do not reuse the stale pre-merge PR worktree or its 777-node six-file inventory.
- The exact four target files collect 572 identities at the base: `test_shoot_screens.py` 240, `test_new_screenshots.py` 89, `test_current_screenshots.py` 156, and `test_fittings_page.py` 87.
- Preserve every base node ID except the one aggregate Fittings state-machine ID, which is intentionally replaced by its same eleven independently reportable scenario IDs. That split adds ten net identities; fifteen explicitly named protocol/isolation tests bring the planned final four-file inventory from 572 to 597. Task 0 records the exact base ID set before source changes.
- Do not delete, pairwise-reduce, rename, or reparameterize existing screenshot business scenarios in this tranche. Matrix consolidation is a separate plan after hosted worker evidence.
- Existing negative screenshot scenarios such as `missing`, `covered`, `hidden`, `invalid`, and geometry corruption are successful tests: they prove the verifier rejects bad state and must continue returning `ok: true` with their exact PASS label. Only explicit `protocol_probe` requests may intentionally return `ok: false`.
- Do not change production files, workflow selectors, marker policy, branch protection, persisted data, screenshot keys, generated shooter expressions, packaging/configuration, or pywebview behavior.
- Do not adopt pytest-xdist. Process reuse is serial within each worker.
- Preserve Node absence behavior. `test_shoot_screens.py`, `test_new_screenshots.py`, and `test_current_screenshots.py` must fail if Node is absent. Existing Fittings-owned tests retain their `skipif` markers. A shared worker factory must never call `pytest.skip()`.
- Every worker request starts with a fresh VM, `createDOM()` result, handlers, bridge queues, focus, scroll state, mutable fixture clone, timer registry, unhandled-rejection listener, and request-local console.
- Stdout is protocol-only. Worker diagnostics go in the structured reply or bounded stderr; production logging must never become an unframed protocol line.
- Preserve every current PASS string exactly. The conversion changes transport, not business diagnostics.
- Assertion-style protocol-probe failures keep the worker alive only after request cleanup completes. Timeout, EOF, malformed reply, reply-ID mismatch, and reply-scenario mismatch continue to discard and restart through `NodeScenarioWorker`.
- Generated prepare/stage/verify/cleanup expressions and monkeypatched fixture values remain request-dynamic. Do not cache mutable DOM nodes, selector results, VM globals, or generated scripts.
- Preserve full JavaScript stacks through `NodeScenarioFailure`; do not replace them with aggregate return-code assertions.
- Temporary one-shot compatibility may exist only while migrating callers. Remove it after repository search proves both Python callers of `screenshot_pages.cjs` use workers.
- UI setup controller/profile filesystem-fixture work is out of scope and belongs to a separate tranche.
- Any request with a live tracked timer or unhandled rejection after its normal drain fails before reply. `finally` still cancels timers and removes listeners; cleanup probes verify the next request remains clean.
- Each task is test-first, ends in a focused commit, and receives a fresh task review before the next task begins.

---

## File Structure

### Shared infrastructure

- `tests/node_scenario_worker.py` — process lifecycle, request correlation, timeout/crash handling, stderr tail, and stack-note rendering. Modify only when a failing general protocol test proves a defect shared by existing workers; the final polish adds detection for a retained worker that exits after an `ok` reply.
- `tests/fixtures/screenshot_dom.cjs` — per-call DOM primitive. Preserve its CommonJS `createDOM` export and direct Node behavior while also exposing one closure-free factory source that screenshot workers evaluate inside each request VM.

### Files changed by this plan

- `tests/fixtures/screenshot_pages.cjs` — persistent worker for generated screenshot expressions used by `test_shoot_screens.py` and `test_new_screenshots.py`.
- `tests/test_shoot_screens.py` — text-preserving session markup, worker fixture, six protocol/isolation nodes, and `_run_gap_capture` conversion.
- `tests/test_new_screenshots.py` — standard-markup worker fixture, one process-reuse node, `run_screenshot_page` conversion, and shared Fittings worker consumption.
- `tests/fixtures/current_screenshot_pages.cjs` — independent current-owner worker.
- `tests/test_current_screenshots.py` — session markup/worker fixtures, four protocol/isolation nodes, and `run_current_page` conversion.
- `tests/fixtures/fittings_page.cjs` — checked-in Fittings harness, first extracted unchanged and then converted to a fresh-VM worker.
- `tests/fittings_scenario_worker.py` — shared worker factory and request adapter; no pytest skip behavior.
- `tests/conftest.py` — one session-scoped `fittings_page_worker` fixture shared by Fittings and new-screenshot modules.
- `tests/test_fittings_page.py` — four protocol/isolation nodes, worker migration, and eleven explicit state-machine identities.
- `tests/fixtures/persistent_screenshot_harness_base_nodes.txt` — normalized exact 572-node base set, committed before source changes so separate task sessions do not depend on `/tmp` retention.
- `docs/ci-persistent-screenshot-harness-results.md` — baseline IDs, exact protocol additions, process counts, local/hosted timings, verification, and stop/go result.

### Planned identity additions

| File | Existing | State split | Protocol/isolation | Planned final |
|---|---:|---:|---:|---:|
| `test_shoot_screens.py` | 240 | 0 | 6 | 246 |
| `test_new_screenshots.py` | 89 | 0 | 1 | 90 |
| `test_current_screenshots.py` | 156 | 0 | 4 | 160 |
| `test_fittings_page.py` | 87 | +10 | 4 | 101 |
| **Total** | **572** | **+10** | **+15** | **597** |

Protocol additions are named in their task. Any count change requires a recorded ruling and updated node-set comparison before implementation continues.

---

### Task 0: Freeze Base Inventory and Scope

**Files:**
- Create: `tests/fixtures/persistent_screenshot_harness_base_nodes.txt`
- Create: `docs/ci-persistent-screenshot-harness-results.md`

**Interfaces:**
- Produces: tracked exact base node-ID evidence, launch inventory, source identities, and changed-path allowlist used by Task 6.
- Consumes: hosted baseline run `35684157184`, whose target counts match current merged `main` collection.

- [ ] **Step 1: Record exact source and hosted identities**

Run:

```bash
git rev-parse HEAD
git merge-base HEAD main
gh run view 35684157184 -R elboaf/FlyGD-Wingman --json headSha,jobs,url
```

Record `c4a2b2060de8f8317e61a732708a9b5bd88beb98` as the source base. Download PR #277's Windows JUnit artifact and prove the normalized target node set matches current collection before accepting it as the comparator:

```bash
rm -rf /tmp/wingman-pr277-screenshot-baseline
mkdir -p /tmp/wingman-pr277-screenshot-baseline
gh run download 35684157184 -R elboaf/FlyGD-Wingman \
  -n pytest-evidence-windows-latest \
  -D /tmp/wingman-pr277-screenshot-baseline
```

Normalize each target JUnit case as `classname.replace('.', '/') + '.py::' + name` and compare the four-file set with current collection. Record that the artifact checkout and `c4a2b206` share all 572 target node IDs. Do not claim the artifact executed the squash SHA itself.

- [ ] **Step 2: Freeze the exact 572-node base set**

```bash
uv run --no-sync python -m pytest \
  tests/test_shoot_screens.py \
  tests/test_new_screenshots.py \
  tests/test_current_screenshots.py \
  tests/test_fittings_page.py \
  --collect-only -q -p no:cacheprovider \
  | python -c "import sys; print(''.join(sorted(line for line in sys.stdin if line.startswith('tests/') and '::' in line)), end='')" \
  > tests/fixtures/persistent_screenshot_harness_base_nodes.txt
```

Validate counts from the tracked file and write the per-file and total counts into the results document. Compare it byte-for-byte with the normalized PR #277 Windows target set produced in Step 1.

- [ ] **Step 3: Freeze the one-shot launch inventory**

Record exact call sites with:

```bash
rg -n "subprocess\.run|screenshot_pages\.cjs|current_screenshot_pages\.cjs|_run_fittings_node" \
  tests/test_shoot_screens.py \
  tests/test_new_screenshots.py \
  tests/test_current_screenshots.py \
  tests/test_fittings_page.py
```

Record **345 current Node child launches across the four files**: 114 migrated generated-screenshot launches, 31 out-of-scope Alerts launches, 78 new-screenshot launches, 82 current-screenshot launches, and 40 Fittings launches. The worker scope migrates 314 launches; the 31 `screenshot_alerts.cjs` launches remain unchanged. Keep the exact family derivation in the results document; do not infer Windows seconds per launch.

- [ ] **Step 4: Write the baseline and scope section**

The initial results document must contain:

- source base and PR #277 hosted baseline URLs;
- exact four-file 572-node inventory;
- exact node-ID artifact path and reproduction command;
- launch call sites and counts;
- target Windows sums: 38.610s, 26.005s, 25.852s, and 23.838s;
- allowed changed paths from this plan;
- explicit statement that no matrix deletion occurs.

- [ ] **Step 5: Commit Task 0**

```bash
git add \
  tests/fixtures/persistent_screenshot_harness_base_nodes.txt \
  docs/ci-persistent-screenshot-harness-results.md
git commit -m "docs: baseline persistent screenshot harness"
```

---

### Task 1: Convert the Generated Screenshot Harness and `test_shoot_screens.py`

**Files:**
- Modify: `tests/fixtures/screenshot_pages.cjs`
- Modify: `tests/test_shoot_screens.py`
- Test: `tests/test_new_screenshots.py`
- Test: `tests/test_node_scenario_worker.py`
- Test: `tests/test_screenshot_dom.py`

**Interfaces:**
- Consumes: `NodeScenarioWorker.request(scenario: str, payload: Mapping[str, object] | None, *, timeout: float) -> dict[str, object]`.
- Produces: worker mode selected by `--worker`, startup argv `<markup-json> <web-root>`, and request payload fields `key`, `gap`, `regression`, `prepare`, `stage`, `verify`, `cleanup`, `fixture`, `reset`, and `texts`.
- Produces: `gap_capture_worker: NodeScenarioWorker` and `_request_gap_capture(worker, key, scenario) -> dict[str, object]`.
- Temporary compatibility: existing `<payload-json> <web-root>` one-shot argv remains until Task 2 converts `test_new_screenshots.py`.

**Six added nodes:** one reuse/business-isolation test, one combined VM throw/rejection stack-and-recovery probe, two order tests, and two pending-timer cleanup probes.

- [ ] **Step 1: Add session markup and worker fixtures**

```python
@pytest.fixture(scope="session")
def gap_capture_markup(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tree = _CaptureTextTree()
    tree.feed((WEB / "index.html").read_text(encoding="utf-8"))
    path = tmp_path_factory.mktemp("gap-capture-worker") / "page.json"
    path.write_text(json.dumps(tree.root, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture(scope="session")
def gap_capture_worker(gap_capture_markup: Path):
    node = shutil.which("node")
    assert node is not None, "node is not installed"
    worker = NodeScenarioWorker(
        [node, str(ROOT / "tests/fixtures/screenshot_pages.cjs"), "--worker",
         str(gap_capture_markup), str(WEB)],
        cwd=ROOT,
    )
    try:
        yield worker
    finally:
        worker.close()
```

- [ ] **Step 2: Add failing protocol tests that do not reinterpret business scenarios**

Existing negative scenarios remain successful:

```python
def test_gap_capture_worker_reuses_process_and_preserves_business_outcomes(
    gap_capture_worker: NodeScenarioWorker,
):
    first = _request_gap_capture(
        gap_capture_worker, "settings-wanderer-controls-narrow", "settled"
    )
    process = gap_capture_worker._proc
    negative = _request_gap_capture(
        gap_capture_worker, "settings-wanderer-controls-narrow", "missing"
    )
    second = _request_gap_capture(
        gap_capture_worker, "settings-wanderer-controls-narrow", "settled"
    )
    assert first["output"] == (
        "PASS screenshot gap settings-wanderer-controls-narrow settled"
    )
    assert negative["output"] == (
        "PASS screenshot gap settings-wanderer-controls-narrow missing"
    )
    assert second["output"] == first["output"]
    assert gap_capture_worker._proc is process


def test_gap_capture_worker_vm_failures_preserve_stack_and_recover(
    gap_capture_worker: NodeScenarioWorker,
):
    _request_gap_capture(
        gap_capture_worker, "settings-wanderer-controls-narrow", "settled"
    )
    process = gap_capture_worker._proc
    for mode, stack_name in [
        ("vm-throw", "protocolVmThrow"),
        ("vm-reject", "protocolVmReject"),
    ]:
        with pytest.raises(NodeScenarioFailure) as failure:
            gap_capture_worker.request(
                f"protocol/{mode}", {"protocol_probe": mode}, timeout=20.0
            )
        assert stack_name in failure.value.stack
        _request_gap_capture(
            gap_capture_worker, "settings-wanderer-controls-narrow", "settled"
        )
        assert gap_capture_worker._proc is process
```

Add `test_gap_capture_worker_is_order_independent` with two parameter IDs, `settled-missing-settled` and `covered-settled-hidden`; every business request succeeds and returns its exact PASS label. Add `test_gap_capture_worker_cancels_pending_timer` with IDs `pending-timer-normal-exit` and `pending-timer-assertion-exit`; both intentionally return structured failure because a live timer is forbidden, then a clean business request succeeds on the same process.

- [ ] **Step 3: Run the six protocol nodes to verify RED**

```bash
uv run --no-sync python -m pytest \
  tests/test_shoot_screens.py \
  -k 'gap_capture_worker' -q --tb=short
```

Expected: FAIL because worker mode and `_request_gap_capture` do not exist.

- [ ] **Step 4: Refactor `screenshot_pages.cjs` into fresh request execution**

Keep only modules and immutable startup JSON outside `runScenario`. Use request-local output capture:

```javascript
const outputLines = [];
const requestConsole = {
  log: (...args) => outputLines.push(args.join(' ')),
  info: (...args) => outputLines.push(args.join(' ')),
  debug: (...args) => outputLines.push(args.join(' ')),
  warn: (...args) => outputLines.push(args.join(' ')),
  error: (...args) => { throw new Error(args.join(' ')); },
};
```

Inject `requestConsole` into the VM. Replace each existing terminal PASS `console.log` with `outputLines.push` using the exact existing string. Require exactly one terminal PASS line and return it unchanged.

Track timers and rejection listeners per request. For protocol probes:

```javascript
if (request.payload?.protocol_probe === 'vm-throw') {
  run(`(() => { function protocolVmThrow() { throw new Error('protocol VM throw'); }
    protocolVmThrow(); })()`);
}
if (request.payload?.protocol_probe === 'vm-reject') {
  run(`(() => { function protocolVmReject() {
    Promise.reject(new Error('protocol VM rejection')); }
    protocolVmReject(); })()`);
}
if (request.payload?.protocol_probe?.startsWith('pending-timer-')) {
  requestSetTimeout(() => outputLines.push('leaked timer'), 0);
  if (request.payload.protocol_probe === 'pending-timer-assertion-exit') {
    throw new Error('protocol cleanup probe failure');
  }
}
```

After normal scenario drain, turn the first captured unhandled rejection into the structured request failure and assert no live timer. `finally` removes the listener and cancels all timers. The serve wrapper records the baseline `process.listeners('unhandledRejection')` list before `runScenario`, verifies the same list after `runScenario` returns or throws, and only then writes the reply. This makes VM rejection stacks, listener cleanup, and both pending-timer failures observable while ensuring cleanup precedes reply.

The NDJSON loop is the only worker stdout writer and uses `isNativeError(error)` for stack extraction. Preserve one-shot mode by wrapping its payload in a synthetic request; print only the exact returned PASS line from that compatibility entry point.

- [ ] **Step 5: Implement request payload construction in Python**

Compute text-preserving markup and leaf text once per session. `_request_gap_capture` passes generated strings and current monkeypatched fixtures in memory. Its composite protocol label is `<key>/<scenario>` while the business PASS string remains unchanged.

- [ ] **Step 6: Run full compatibility gates before committing**

```bash
uv run --no-sync python -m pytest \
  tests/test_node_scenario_worker.py \
  tests/test_screenshot_dom.py \
  tests/test_shoot_screens.py \
  tests/test_new_screenshots.py \
  -q -rs --durations=50
node --test tests/fixtures/screenshot_dom.test.cjs
```

`test_new_screenshots.py` is mandatory here because it remains the untouched one-shot caller of the modified dual-mode fixture.

- [ ] **Step 7: Commit Task 1**

```bash
git add tests/fixtures/screenshot_pages.cjs tests/test_shoot_screens.py
git commit -m "test: reuse generated screenshot worker"
```

---

### Task 2: Convert `test_new_screenshots.py` and Retire One-Shot Compatibility

**Files:**
- Modify: `tests/test_new_screenshots.py`
- Modify: `tests/fixtures/screenshot_pages.cjs`
- Test: `tests/test_shoot_screens.py`

**Interfaces:**
- Consumes: Task 1 worker argv and payload contract.
- Produces: `new_screenshot_worker: NodeScenarioWorker` using standard `PageTree` markup.
- Removes: one-shot mode after search proves no caller remains.

**One added node:** standard-markup process reuse across a positive scenario and an existing negative-verifier scenario, both of which return `ok: true`.

- [ ] **Step 1: Add standard-markup session fixtures and a RED reuse test**

Use `settings-previews-groups` with a scalar fidelity regression and the real mapping regression `{"geometry": "missing-summary"}`:

```python
def test_new_screenshot_worker_reuses_process_and_preserves_negative_contracts(
    new_screenshot_worker: NodeScenarioWorker,
):
    first = _request_screenshot_page(
        new_screenshot_worker, "settings-previews-groups", "fidelity"
    )
    process = new_screenshot_worker._proc
    negative = _request_screenshot_page(
        new_screenshot_worker,
        "settings-previews-groups",
        {"geometry": "missing-summary"},
    )
    second = _request_screenshot_page(
        new_screenshot_worker, "settings-previews-groups", "fidelity"
    )
    assert first["output"] == (
        "PASS screenshot fidelity settings-previews-groups fidelity"
    )
    assert negative["output"] == "PASS screenshot Groups geometry missing-summary"
    assert second["output"] == first["output"]
    assert new_screenshot_worker._proc is process
```

- [ ] **Step 2: Run the reuse test to verify RED**

```bash
uv run --no-sync python -m pytest \
  tests/test_new_screenshots.py \
  -k 'worker_reuses_process' -q --tb=short
```

- [ ] **Step 3: Convert payload construction without narrowing regression types**

```python
def _request_screenshot_page(
    worker: NodeScenarioWorker,
    key: str,
    regression: object | None = None,
) -> dict[str, object]:
    screen = next(screen for screen in shoot.SCREENS if screen.key == key)
    payload: dict[str, object] = {
        "key": key,
        "prepare": shoot.new_screen_prepare_script(screen),
        "stage": shoot.screen_setup_script(screen),
        "verify": shoot.new_screen_verify_script(screen),
        "cleanup": shoot.new_screen_cleanup_script(screen),
        "regression": regression,
    }
    # Preserve the existing Fittings and crop payload branches exactly.
    return worker.request(f"{key}/{regression!r}", payload, timeout=20.0)
```

Copy the existing Fittings/crop payload branches without changing field names or values. Migrate all callers and remove temp JSON writes/direct subprocess assertions.

- [ ] **Step 4: Remove one-shot mode only after exact caller search**

```bash
rg -n "screenshot_pages\.cjs|subprocess\.run" tests scripts
```

The only `screenshot_pages.cjs` Python launches must be `NodeScenarioWorker` startup argv. Remove compatibility mode and make invalid startup argv exit nonzero on stderr before reading requests.

- [ ] **Step 5: Run both modules and fixture gates**

```bash
uv run --no-sync python -m pytest \
  tests/test_node_scenario_worker.py \
  tests/test_screenshot_dom.py \
  tests/test_shoot_screens.py \
  tests/test_new_screenshots.py \
  -q -rs --durations=50
node --test tests/fixtures/screenshot_dom.test.cjs
node scripts/js_smoke.js
```

- [ ] **Step 6: Commit Task 2**

```bash
git add tests/fixtures/screenshot_pages.cjs tests/test_new_screenshots.py
git commit -m "test: reuse new screenshot worker"
```

---

### Task 3: Convert Current-Owner Screenshot Scenarios

**Files:**
- Modify: `tests/fixtures/current_screenshot_pages.cjs`
- Modify: `tests/test_current_screenshots.py`
- Test: `tests/test_page_conventions.py`

**Interfaces:**
- Produces: `current_screenshot_worker: NodeScenarioWorker`, startup argv `<markup-json> <web-root>`, and request-dynamic current-owner payloads.
- Fresh state includes Fleet, Companion and Wanderer fixtures, waiting replies, owner generations, focus, scroll, tabs, dialog state, intervals, timers, and bridge queues.

**Four added nodes:** owner-family reuse, one combined VM throw/rejection stack-and-recovery probe, and two pending-timer cleanup probes.

- [ ] **Step 1: Add exact-key RED tests**

```python
def test_current_screenshot_worker_isolates_owner_families(
    current_screenshot_worker: NodeScenarioWorker,
):
    _request_current_page(
        current_screenshot_worker, "settings-companions-populated", "normal"
    )
    process = current_screenshot_worker._proc
    _request_current_page(current_screenshot_worker, "settings-wanderer", "late-read")
    _request_current_page(
        current_screenshot_worker, "settings-fleet-sharing", "late-synthetic"
    )
    invalid = _request_current_page(
        current_screenshot_worker, "settings-companions-populated", "invalid"
    )
    assert invalid["output"] == (
        "PASS current screenshot settings-companions-populated invalid"
    )
    _request_current_page(
        current_screenshot_worker, "settings-companions-populated", "normal"
    )
    assert current_screenshot_worker._proc is process
```

Add `test_current_screenshot_worker_vm_failures_preserve_stack_and_recover`, which sends both `vm-throw` and `vm-reject` probes inside one pytest node and asserts VM function names in their stacks plus same-process recovery. Add `test_current_screenshot_worker_cancels_pending_timer` with IDs `pending-timer-normal-exit` and `pending-timer-assertion-exit`. Do not use `invalid` as a protocol failure.

- [ ] **Step 2: Run worker tests to verify RED**

```bash
uv run --no-sync python -m pytest \
  tests/test_current_screenshots.py \
  -k 'worker_' -q --tb=short
```

- [ ] **Step 3: Move all mutable CJS state into fresh request execution**

Startup retains only modules, immutable page JSON, production-source paths, and the NDJSON loop. Every request creates `createDOM(page)`, VM, `window`, request-local console, production module loads, bridge queues, waiting replies, cloned live fixtures, revisions, dialogs, focus, scroll, timers, intervals, and rejection listener.

Preserve exact current PASS strings. Existing `invalid` requests return `ok: true`; only explicit protocol probes return `ok: false`. The serve loop records `process.listeners('unhandledRejection')` before `runScenario`, asserts the identical listener list after cleanup on both return and throw, and only then emits the structured reply.

- [ ] **Step 4: Convert `run_current_page` callers**

Pass every existing generated field unchanged. Use `<key>/<scenario>` only for protocol correlation. Preserve the two-iteration capture lifecycle, late-read, late-synthetic, cleanup verification, and ordinary live behavior resumption.

- [ ] **Step 5: Run current-owner and neighboring suites**

```bash
uv run --no-sync python -m pytest \
  tests/test_current_screenshots.py \
  tests/test_shoot_screens.py \
  tests/test_new_screenshots.py \
  tests/test_dev_harness.py \
  tests/test_page_conventions.py \
  -q -rs --durations=50
node scripts/js_smoke.js
```

- [ ] **Step 6: Commit Task 3**

```bash
git add tests/fixtures/current_screenshot_pages.cjs tests/test_current_screenshots.py
git commit -m "test: reuse current screenshot worker"
```

---

### Task 4: Extract the Fittings Harness Without Behavior Changes

**Files:**
- Create: `tests/fixtures/fittings_page.cjs`
- Modify: `tests/test_fittings_page.py`
- Test: `tests/test_new_screenshots.py`

**Interfaces:**
- Preserves: one-shot argv `<markup-json> <scenario> <fittings-js>` and exact stdout/stderr/exit behavior.
- Removes: embedded `_COPY_ACCESSIBILITY_HARNESS` Python string and per-test harness-file write.
- Does not introduce worker mode or change pytest identities.

- [ ] **Step 1: Add a RED lexical ownership test**

Add a temporary test asserting the checked-in fixture exists and the Python module no longer owns a giant CJS string. Before extraction, the fixture-exists assertion fails. Remove this temporary test after GREEN and before the Task 4 commit so Task 4 changes no retained pytest identity.

- [ ] **Step 2: Run the ownership test to verify RED**

```bash
uv run --no-sync python -m pytest \
  tests/test_fittings_page.py \
  -k 'checked_in_harness' -q --tb=short
```

- [ ] **Step 3: Move the embedded CJS byte-for-byte into the fixture**

Create `tests/fixtures/fittings_page.cjs` from `_COPY_ACCESSIBILITY_HARNESS`. Change `_run_fittings_node` to execute that file directly while retaining page JSON, scenario, script path, timeout, encoding, captured output, and `CompletedProcess` behavior. Remove the embedded string and temp harness write only.

- [ ] **Step 4: Run full behavior-neutral extraction gates**

```bash
uv run --no-sync python -m pytest \
  tests/test_fittings_page.py \
  tests/test_new_screenshots.py \
  -q -rs --durations=50
node --check tests/fixtures/fittings_page.cjs
```

The pre/post node set and outcomes must be identical. Delete the temporary ownership test before committing, rerun collection, and prove no retained identity was added or removed.

- [ ] **Step 5: Commit Task 4**

```bash
git add tests/fixtures/fittings_page.cjs tests/test_fittings_page.py
git commit -m "test: extract Fittings page harness"
```

---

### Task 5: Convert the Shared Fittings Harness to a Fresh-VM Worker

**Files:**
- Create: `tests/fittings_scenario_worker.py`
- Modify: `tests/conftest.py`
- Modify: `tests/fixtures/fittings_page.cjs`
- Modify: `tests/test_fittings_page.py`
- Modify: `tests/test_new_screenshots.py`
- Test: `tests/test_bridge_contract.py`

**Interfaces:**
- Produces: `create_fittings_worker(tmp_path_factory: pytest.TempPathFactory) -> NodeScenarioWorker`; raises `AssertionError("node is not installed")` rather than skipping when Node is missing.
- Produces: `request_fittings_scenario(worker, scenario, *, screenshot=None) -> dict[str, object]`.
- Produces: one session fixture `fittings_page_worker` registered in `tests/conftest.py` and shared by both modules.
- Worker startup argv: `<markup-json> <fittings-js> <panel-js>`.
- CJS always loads `fittings.js`; it first loads `panel.js` exactly when `scenario === "dialog-description" || scenario.startsWith("interleaving-")`, preserving current order.

**Four added nodes:** reuse/business-isolation, one combined VM throw/rejection stack-and-recovery probe, and two pending-timer cleanup probes. Existing Fittings tests retain their Node `skipif`; unmarked new-screenshot pending-confirmation tests fail if shared fixture creation finds no Node.

- [ ] **Step 1: Add shared factory, fixture, and RED protocol tests**

`tests/fittings_scenario_worker.py`:

```python
def create_fittings_worker(
    tmp_path_factory: pytest.TempPathFactory,
) -> NodeScenarioWorker:
    node = shutil.which("node")
    assert node is not None, "node is not installed"
    tree = PageTree()
    tree.feed((WEB / "index.html").read_text(encoding="utf-8"))
    markup = tmp_path_factory.mktemp("fittings-worker") / "page.json"
    markup.write_text(json.dumps(tree.root, ensure_ascii=False), encoding="utf-8")
    return NodeScenarioWorker(
        [node, str(ROOT / "tests/fixtures/fittings_page.cjs"), str(markup),
         str(WEB / "fittings.js"), str(WEB / "panel.js")],
        cwd=ROOT,
    )


def request_fittings_scenario(
    worker: NodeScenarioWorker,
    scenario: str,
    *,
    screenshot: Mapping[str, object] | None = None,
) -> dict[str, object]:
    return worker.request(
        scenario,
        {"screenshot": screenshot},
        timeout=15.0,
    )
```

Register one session fixture in `tests/conftest.py` that creates, yields, and closes this worker. Do not put skip logic in the fixture.

Add four RED protocol nodes to `test_fittings_page.py`: `test_fittings_worker_reuses_process_and_preserves_business_outcomes`, `test_fittings_worker_vm_failures_preserve_stack_and_recover` (both `vm-throw` and `vm-reject` inside one node), and `test_fittings_worker_cancels_pending_timer` with IDs `pending-timer-normal-exit` and `pending-timer-assertion-exit`. Keep the existing `skipif(Node missing)` marker on those Fittings-owned tests. Use explicit protocol probes for failure; ordinary negative/business scenarios still return PASS.

- [ ] **Step 2: Run protocol tests to verify RED**

```bash
uv run --no-sync python -m pytest \
  tests/test_fittings_page.py \
  -k 'worker_' -q --tb=short
```

- [ ] **Step 3: Convert the checked-in CJS to serial NDJSON with a fresh VM**

Parse immutable page JSON once. For each request:

- create a new VM context and request-local globals rather than assigning `global.*` in the process realm;
- load `panel.js` before `fittings.js` only for the exact existing condition;
- always load `fittings.js`;
- keep screenshot payload request-local;
- use request-local console/timer/rejection tracking;
- preserve every PASS string;
- reply only through NDJSON stdout envelopes;
- record `process.listeners('unhandledRejection')` before `runScenario`, assert the identical list after cleanup on both return and throw, and only then emit the reply.

No request field chooses a source path or script name.

- [ ] **Step 4: Migrate both Python modules to the shared fixture**

Remove `_run_fittings_node` and direct subprocess assertions. `test_copy_accessibility_in_node` and the two pending-confirmation tests request scenarios from `fittings_page_worker` and assert exact structured output.

The pending-confirmation tests remain unmarked; if Node is absent, fixture creation fails. Fittings-owned worker tests retain `skipif` and therefore skip before fixture setup.

- [ ] **Step 5: Split the eleven state-machine scenarios into explicit identities**

Replace the aggregate loop with `@pytest.mark.parametrize("scenario", [...])` containing the exact existing eleven strings. Each node requests one scenario and asserts `reply["output"] == f"PASS {scenario}"`. This is the only intentional transformation of an existing node ID.

- [ ] **Step 6: Run Fittings, screenshot, bridge, and convention suites**

```bash
uv run --no-sync python -m pytest \
  tests/test_fittings_page.py \
  tests/test_new_screenshots.py \
  tests/test_fittings_runtime.py \
  tests/test_bridge_contract.py \
  tests/test_page_conventions.py \
  tests/test_node_scenario_worker.py \
  -q -rs --durations=50
node scripts/js_smoke.js
rg -n "_COPY_ACCESSIBILITY_HARNESS|_run_fittings_node|fittings-harness\.cjs" tests
```

Expected search result: no matches.

- [ ] **Step 7: Commit Task 5**

```bash
git add \
  tests/fixtures/fittings_page.cjs \
  tests/fittings_scenario_worker.py \
  tests/conftest.py \
  tests/test_fittings_page.py \
  tests/test_new_screenshots.py
git commit -m "test: reuse Fittings scenario worker"
```

---

### Task 6: Exact Inventory, Full Verification, and Hosted Stop/Go

**Files:**
- Modify: `docs/ci-persistent-screenshot-harness-results.md`

**Interfaces:**
- Consumes: `tests/fixtures/persistent_screenshot_harness_base_nodes.txt`, final collection, PR #277 hosted artifacts, and all worker protocol tests.
- Produces: exact node-set diff, scope proof, local verification, hosted comparison, and Plan B authorization decision.

- [ ] **Step 1: Freeze and compare final node IDs**

```bash
uv run --no-sync python -m pytest \
  tests/test_shoot_screens.py \
  tests/test_new_screenshots.py \
  tests/test_current_screenshots.py \
  tests/test_fittings_page.py \
  --collect-only -q -p no:cacheprovider \
  > /tmp/wingman-screenshot-harness-final-nodes.txt
```

Use a script to compare final collection with `tests/fixtures/persistent_screenshot_harness_base_nodes.txt`. The allowed difference is exactly:

- remove the one aggregate `test_fittings_state_machine_in_node` ID;
- add its eleven parameterized IDs;
- add the fifteen protocol/isolation IDs named in Tasks 1, 2, 3, and 5.

Every other base node ID must remain present. Expected final total: 597.

- [ ] **Step 2: Prove process reuse and order isolation**

Run the four files in normal and reverse file order. Generate explicit forward, reverse, and one recorded deterministic shuffled node list from final collection; execute each list without an ordering plugin. Protocol tests must prove:

- business negative scenarios return PASS;
- assertion/timer probes fail structurally with JS stack;
- assertion-style failures keep the same process after cleanup;
- timeout/crash probes restart through existing `NodeScenarioWorker` tests;
- A→B→A, owner-family switches, and Fittings screenshot/ordinary switches remain isolated.

- [ ] **Step 3: Build/install prerequisites and run focused evidence**

```bash
node --version
cargo build --locked --release \
  --manifest-path packaging/settings-codec/Cargo.toml \
  --target-dir packaging/settings-codec/target
uv run --no-sync python -c "import os, pathlib, shutil; from wingman.evesettings import codec; name = 'wingman-settings-codec' + ('.exe' if os.name == 'nt' else ''); source = pathlib.Path('packaging/settings-codec/target/release') / name; target = pathlib.Path('packaging/bin') / name; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target); assert codec.codec_available()"
uv run --no-sync python -m pytest \
  tests/test_shoot_screens.py \
  tests/test_new_screenshots.py \
  tests/test_current_screenshots.py \
  tests/test_fittings_page.py \
  -q -rs --durations=50 \
  --junitxml=/tmp/wingman-persistent-screenshot-focused.xml
```

- [ ] **Step 4: Run complete local verification**

```bash
uv run --no-sync python -m pytest tests/ -q -rs --durations=50 \
  --junitxml=/tmp/wingman-persistent-screenshot-full.xml
node scripts/js_smoke.js
node --test tests/fixtures/screenshot_dom.test.cjs
cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
git diff --check
```

Inspect skip reasons; Node and codec availability skips are not acceptable.

- [ ] **Step 5: Enforce changed-path scope**

```bash
git diff --name-only c4a2b206..HEAD -- \
  wingman .github scripts packaging pyproject.toml uv.lock
```

Expected: no output.

Compare all changed paths against this allowlist:

```text
docs/ci-persistent-screenshot-harness-results.md
docs/superpowers/plans/2026-09-22-persistent-screenshot-harness.md
tests/conftest.py
tests/fittings_scenario_worker.py
tests/fixtures/current_screenshot_pages.cjs
tests/fixtures/fittings_page.cjs
tests/fixtures/persistent_screenshot_harness_base_nodes.txt
tests/fixtures/screenshot_dom.cjs
tests/fixtures/screenshot_pages.cjs
tests/node_scenario_worker.py
tests/test_current_screenshots.py
tests/test_fittings_page.py
tests/test_new_screenshots.py
tests/test_node_scenario_worker.py
tests/test_shoot_screens.py
```

Any other path requires an explicit ruling and plan update before completion.

- [ ] **Step 6: Complete the results document and commit local evidence**

Record:

- source/hosted identities and exact checkout caveat;
- 572→597 node transformation with full ID-set proof;
- 345 Node child launches before, including 31 unchanged Alerts launches; 314 in-scope launches before and exact session-worker topology after;
- unchanged business-scenario inventory;
- worker fresh-state, cleanup, crash/restart, diagnostic, and Node-absence contracts;
- normal/reverse/shuffled results;
- focused/full local results, skip inventory, JS smoke, Node fixture test, Cargo and Ruff;
- no product/workflow/configuration change;
- PR #277 Windows reference sums without Linux projection.

```bash
git add docs/ci-persistent-screenshot-harness-results.md
git commit -m "docs: record persistent screenshot harness"
```

- [ ] **Step 7: Obtain comparable hosted evidence before Plan B**

After explicit publication authorization, push and run hosted CI. Download Windows and Ubuntu JUnit/timing artifacts. Compare common business node IDs separately from new protocol nodes, plus:

- four target-file sums;
- pytest step;
- complete job;
- required critical path;
- total testcase sum.

**GO for matrix-consolidation Plan B** only if all required checks pass, exact business nodes remain, process reuse is demonstrated, no leakage occurs, diagnostics retain stacks/labels, and comparable Windows target-file evidence is conclusive.

**INCONCLUSIVE / repeat hosted measurement** if runner behavior is anomalous or artifacts are not comparable. An anomaly never authorizes Plan B.

**STOP / repair this tranche** if target cost materially regresses without explained protocol coverage, failure cleanup poisons later requests, or diagnostics become less actionable.

Workflow selection, budget enforcement, and Windows sharding remain out of scope regardless of this tranche's result.
