# CI Test Strategy Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the complete cross-platform suite materially faster and measurable without deleting cases or reducing Windows pull-request coverage.

**Architecture:** Add machine-readable timing around the existing full suite, then replace per-scenario Node startup with a reusable NDJSON worker while retaining one pytest/JUnit node ID per scenario. Migrate the measured worst setup and formations harnesses, close the existing Cargo gap in release-owned gates, and use hosted evidence to decide whether any later consolidation or platform classification is necessary.

**Tech Stack:** Python 3.11, pytest, Node.js CommonJS/`vm`, GitHub Actions, Rust/Cargo, PyYAML for existing workflow contract tests.

**Spec:** `docs/ci-test-strategy-design.md`

## Global Constraints

- The complete pytest suite continues to run on both Ubuntu and Windows pull-request jobs throughout this phase.
- Do not delete, merge, mark `extended`, or omit any existing pytest scenario in this phase.
- Preserve required status names exactly: `checks`, `test (ubuntu-latest)`, and `test (windows-latest)`.
- Node and the built release settings codec remain mandatory prerequisites; missing prerequisites must not become skips.
- Preserve one pytest/JUnit node ID and one timeout per frontend scenario.
- Every scenario receives fresh VM, DOM, handlers, bridge queues, and environment overlays.
- `release.yml`, `autorelease.yml`, and `build.yml` retain their own Windows test gate before artifact creation or publication.
- The complete release-owned gate includes full pytest and the independent Cargo regression.
- No coverage-percentage gate, browser framework, frontend framework, or generalized orchestration dependency is introduced.
- Use the existing pinned `actions/upload-artifact` SHA `043fb46d1a93d7aae656e7c1c64a875d1fc6a0a` when uploading timing evidence.
- Commands that claim full-suite coverage must inspect `-rs` output and must use the built codec described in `AGENTS.md`.

---

## File map

### New files

- `scripts/summarize_pytest_junit.py` — converts pytest JUnit XML into stable JSON and a human-readable timing summary.
- `tests/test_ci_timing.py` — unit tests for JUnit timing aggregation and malformed/absent input behavior.
- `tests/node_scenario_worker.py` — test-only persistent Node worker client with NDJSON request/reply, timeout, stderr capture, crash recovery, and deterministic close.
- `tests/test_node_scenario_worker.py` — real-Node protocol tests for success, failure, timeout, crash/restart, UTF-8, and environment overlays.
- `docs/ci-test-strategy-phase-1-results.md` — final hosted timing evidence and stop/go decision, created only after implementation runs exist.

### Modified files

- `.github/workflows/ci.yml` — trigger hygiene, duration output, timing summary, and JUnit/timing artifacts without changing test selection or status names.
- `.github/workflows/release.yml` — add the independent Cargo regression to the owned Windows gate.
- `.github/workflows/autorelease.yml` — add the independent Cargo regression to the owned Windows gate.
- `.github/workflows/build.yml` — add the independent Cargo regression to the manual build gate.
- `tests/test_packaging_completeness.py` — pin workflow trigger, timing artifact, prerequisite ordering, and Cargo ownership contracts.
- `tests/test_ui_setup_page.py` — session-scoped parsed markup/common replies and persistent worker fixture; scenario IDs remain unchanged.
- `tests/fixtures/ui_setup_page.cjs` — expose one isolated async scenario function and serve NDJSON requests in one process.
- `tests/test_formations_page.py` — persistent worker fixture and explicit scenario encoding overlay; scenario IDs remain unchanged.
- `tests/fixtures/formations_page.cjs` — expose one isolated async scenario function and serve NDJSON requests in one process.
- `pyproject.toml` and `uv.lock` — modified only if the measured bounded `pytest-xdist` experiment passes its adoption criteria.

---

### Task 1: Machine-readable pytest timing

**Files:**
- Create: `scripts/summarize_pytest_junit.py`
- Create: `tests/test_ci_timing.py`

**Interfaces:**
- Produces: `summarize(input_path: Path) -> dict[str, object]`
- Produces CLI: `python scripts/summarize_pytest_junit.py INPUT.xml OUTPUT.json [--if-present]`
- JSON schema: `{"total_seconds": float, "case_count": int, "files": {str: {"seconds": float, "cases": int}}, "slowest": [{"node_id": str, "seconds": float}]}`

- [ ] **Step 1: Write failing aggregation tests**

Create `tests/test_ci_timing.py` with fixtures containing multiple `<testsuite>` elements, skipped cases, and setup/call timing represented by each testcase's `time` attribute. Assert that `summarize()`:

```python
assert result["case_count"] == 3
assert result["total_seconds"] == pytest.approx(3.75)
assert result["files"]["tests/test_alpha.py"] == {
    "seconds": pytest.approx(3.5),
    "cases": 2,
}
assert result["slowest"][0] == {
    "node_id": "tests.test_alpha.test_slow[param]",
    "seconds": pytest.approx(3.0),
}
```

Also assert that malformed XML raises a concise `TimingError`, a missing input fails normally, and CLI `--if-present` exits zero without creating JSON.

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```bash
uv run --no-sync python -m pytest tests/test_ci_timing.py -q
```

Expected: collection fails because `scripts.summarize_pytest_junit` does not exist.

- [ ] **Step 3: Implement the stdlib-only summarizer**

Implement with `argparse`, `json`, `pathlib`, and `xml.etree.ElementTree`. Derive a file key from `classname` by converting a leading `tests.` package path to `tests/<module>.py`; retain unknown class names under `"<unknown>"`. Sort `slowest` by descending seconds then node ID and cap it at 30. Print total, file totals, and slowest cases to stdout before writing UTF-8 JSON atomically through a sibling temporary file and `Path.replace()`.

- [ ] **Step 4: Verify GREEN and CLI behavior**

Run:

```bash
uv run --no-sync python -m pytest tests/test_ci_timing.py -q
uv run --no-sync python scripts/summarize_pytest_junit.py /tmp/absent.xml /tmp/absent.json --if-present
```

Expected: all tests pass; absent optional input prints a notice, exits zero, and creates no output.

- [ ] **Step 5: Commit Task 1**

```bash
git add scripts/summarize_pytest_junit.py tests/test_ci_timing.py
git commit -m "test: report pytest timing by file"
```

---

### Task 2: CI observability and trigger hygiene

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `tests/test_packaging_completeness.py`

**Interfaces:**
- Consumes: Task 1 timing CLI.
- Produces artifacts named `pytest-evidence-ubuntu-latest` and `pytest-evidence-windows-latest`, each containing `pytest-result.xml` and `pytest-timing.json` when pytest starts.

- [ ] **Step 1: Write failing workflow contract tests**

Add tests to `tests/test_packaging_completeness.py` that parse `.github/workflows/ci.yml` and assert:

```python
assert workflow[True]["push"]["branches"] == ["main"]
assert workflow[True]["pull_request"] is None
assert workflow["concurrency"]["group"] == (
    "ci-${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}"
)
```

Account for PyYAML parsing YAML 1.1's `on` key as boolean `True`, matching existing workflow parsing. Also assert the pytest command contains `--durations=30`, a following `if: always()` timing step invokes the Task 1 CLI with `--if-present`, and an `if: always()` upload step uses the pinned artifact action and OS-qualified artifact name.

- [ ] **Step 2: Run focused tests and verify RED**

```bash
uv run --no-sync python -m pytest \
  tests/test_packaging_completeness.py \
  tests/test_js_smoke.py::test_ci_runs_the_gate_directly -q
```

Expected: new trigger, duration, summary, and artifact assertions fail against the old workflow; existing smoke/prerequisite assertions remain green.

- [ ] **Step 3: Update the workflow without changing job IDs**

Change ordinary push coverage to `branches: [main]`, retain `pull_request`, and use the PR-aware concurrency key from the design. Add `--durations=30` to the existing full pytest command. After pytest, run:

```yaml
- name: Summarize test timing
  if: always()
  run: uv run --no-sync python scripts/summarize_pytest_junit.py pytest-result.xml pytest-timing.json --if-present
```

Then upload both evidence files with `if: always()`, `if-no-files-found: warn`, and:

```yaml
name: pytest-evidence-${{ matrix.os }}
path: |
  pytest-result.xml
  pytest-timing.json
```

Keep `Surface failures` and all prerequisite ordering intact.

- [ ] **Step 4: Verify workflow contracts**

```bash
uv run --no-sync python -m pytest \
  tests/test_packaging_completeness.py \
  tests/test_js_smoke.py::test_ci_runs_the_gate_directly -q
uv run --no-sync python - <<'PY'
import pathlib, yaml
path = pathlib.Path('.github/workflows/ci.yml')
data = yaml.safe_load(path.read_text(encoding='utf-8'))
assert data['jobs']['test']['strategy']['matrix']['os'] == ['ubuntu-latest', 'windows-latest']
print('workflow parses and required matrix names remain stable')
PY
```

Expected: all tests pass and matrix job names remain unchanged.

- [ ] **Step 5: Commit Task 2**

```bash
git add .github/workflows/ci.yml tests/test_packaging_completeness.py
git commit -m "ci: publish test timing evidence"
```

---

### Task 3: Persistent Node scenario worker

**Files:**
- Create: `tests/node_scenario_worker.py`
- Create: `tests/test_node_scenario_worker.py`

**Interfaces:**
- Produces: `NodeScenarioWorker(argv: Sequence[str], *, cwd: Path, startup_timeout: float = 10.0)`
- Produces: `request(scenario: str, payload: Mapping[str, object] | None = None, *, timeout: float = 60.0) -> dict[str, object]`
- Produces: `close() -> None`
- Protocol request: `{"id": int, "scenario": str, "payload": object}` plus one trailing newline.
- Protocol reply: `{"id": int, "scenario": str, "ok": bool, "duration_ms": float, "error": str, "stack": str}` plus one trailing newline.

- [ ] **Step 1: Write real-Node protocol tests**

In `tests/test_node_scenario_worker.py`, write a temporary CJS worker that reads lines with `node:readline`, echoes UTF-8 payloads, returns an assertion-style failure, exits during a `crash` request, delays a `timeout` request, and reports an explicit request environment field. Assert:

```python
assert worker.request("echo", {"text": "Étiquette 𐐀"})["ok"] is True
with pytest.raises(NodeScenarioFailure, match="synthetic failure"):
    worker.request("fail")
with pytest.raises(NodeScenarioTimeout, match="timeout"):
    worker.request("timeout", timeout=0.05)
with pytest.raises(NodeScenarioCrash, match="crash"):
    worker.request("crash")
assert worker.request("echo-after-restart", {"text": "fresh"})["ok"] is True
```

Also assert IDs cannot cross replies, stderr from the active process appears in crash diagnostics, `close()` is idempotent, and no worker survives fixture teardown.

- [ ] **Step 2: Run worker tests and verify RED**

```bash
uv run --no-sync python -m pytest tests/test_node_scenario_worker.py -q
```

Expected: collection fails because `tests.node_scenario_worker` does not exist.

- [ ] **Step 3: Implement the worker client**

Use `subprocess.Popen` with fixed argv, `shell=False`, UTF-8 text pipes, and line buffering. A daemon stdout reader parses replies into a `queue.Queue`; a daemon stderr reader retains a bounded tail. Serialize `request()` with a lock, assign monotonically increasing IDs, and reject malformed or mismatched replies. On timeout or EOF, terminate/kill with bounded waits, clear process state, and raise a typed exception containing scenario and stderr. The next request starts a fresh process. `close()` terminates the current child and joins reader threads without swallowing a primary request error.

Do not use `select`, which does not support Windows pipes consistently.

- [ ] **Step 4: Verify worker behavior repeatedly**

```bash
uv run --no-sync python -m pytest tests/test_node_scenario_worker.py -q
uv run --no-sync python -m pytest tests/test_node_scenario_worker.py -q --count=10
```

If `pytest-repeat` is not installed, use:

```bash
for i in $(seq 1 10); do
  uv run --no-sync python -m pytest tests/test_node_scenario_worker.py -q || exit 1
done
```

Expected: all repetitions pass and process inspection shows no surviving temporary workers.

- [ ] **Step 5: Commit Task 3**

```bash
git add tests/node_scenario_worker.py tests/test_node_scenario_worker.py
git commit -m "test: add persistent Node scenario worker"
```

---

### Task 4: Migrate setup-page runtime scenarios

**Files:**
- Modify: `tests/test_ui_setup_page.py`
- Modify: `tests/fixtures/ui_setup_page.cjs`
- Test: `tests/test_ui_setup_page.py`

**Interfaces:**
- Consumes: `NodeScenarioWorker.request()` from Task 3.
- Worker startup argv: markup JSON path, `wingman/web/uisetup.js`, and `sys.executable`.
- Request payload: `{"mode": "import" | "export", "env": {"PYTHONIOENCODING": str} | {}}`.
- Reply uses Task 3 protocol and preserves existing scenario names as pytest IDs.

- [ ] **Step 1: Add worker-mode contract tests before changing scenarios**

Add focused tests in `tests/test_ui_setup_page.py` or `tests/test_node_scenario_worker.py` that start the setup CJS with a temporary minimal scenario request and assert it accepts two sequential requests without exiting, reports unknown scenarios against the correct request ID, and executes an `A → B → A` isolation sentinel with matching A results.

Keep the existing parameter list untouched.

- [ ] **Step 2: Run the focused worker-mode tests and verify RED**

```bash
uv run --no-sync python -m pytest tests/test_ui_setup_page.py -k 'worker_protocol or isolation_sentinel' -q
```

Expected: failure because `ui_setup_page.cjs` still expects one scenario in `process.argv` and exits after it.

- [ ] **Step 3: Parse page markup and common replies once**

Create session-scoped fixtures using `tmp_path_factory`:

```python
@pytest.fixture(scope="session")
def setup_page_markup(tmp_path_factory):
    page = SetupPageTree()
    page.feed((WEB / "index.html").read_text(encoding="utf-8"))
    path = tmp_path_factory.mktemp("setup-page") / "page.json"
    path.write_text(json.dumps(page.root, ensure_ascii=False), encoding="utf-8")
    return path
```

Construct stable `limits`, standard `export`, and native projection replies once in Python using the same production `Api`, `ProfilesController`, `setup_model`, `setup_sharing`, and `tests.setup_fixtures.wire` calls currently embedded in CJS. Write them to a UTF-8 fixture JSON passed in worker startup argv. Keep scenario-dependent boundary operations (`eve-unknown`, `malformed-text`, `stale-manifest`) in a real Python child initially because they own temporary filesystem/controller behavior.

- [ ] **Step 4: Refactor CJS into a request-scoped function**

Move all mutable top-level state—DOM nodes, handlers, bridge arrays, promises, counters, scenario, and coupled-mode state—inside:

```javascript
async function runScenario(request, staticFixtures) {
  const scenario = request.scenario;
  const started = performance.now();
  // Existing scenario body, with fresh state for this request.
  return {duration_ms: performance.now() - started};
}
```

Use `node:readline` to process requests serially. For every request, create fresh production `vm` contexts and pass `request.payload.env` only to scenario-specific `spawnSync` calls:

```javascript
const env = {...process.env, ...(request.payload.env || {})};
spawnSync(pythonExe, argv, {...options, env});
```

Reply with the Task 3 envelope. Track and reject unhandled promise rejections per request. Clear request-owned timers in `finally`. Do not cache production module state across scenarios.

- [ ] **Step 5: Switch pytest scenarios to the persistent fixture**

Create a session-scoped worker fixture, retain the existing `@pytest.mark.parametrize("scenario", SCENARIOS + IMPORT_SCENARIOS)`, and replace `subprocess.run()` with:

```python
payload = {
    "mode": "import" if scenario in IMPORT_SCENARIOS else "export",
    "env": (
        {"PYTHONIOENCODING": "cp1252"}
        if scenario in {"unicode-locale", "import-unicode"}
        else {}
    ),
}
setup_page_worker.request(scenario, payload, timeout=60.0)
```

Do not mutate the parent pytest environment for encoding scenarios.

- [ ] **Step 6: Compare old and new semantics**

Before deleting the one-shot entry path, run every scenario through both modes and compare pass/fail plus named scenario output:

```bash
uv run --no-sync python -m pytest tests/test_ui_setup_page.py -q -rs --junitxml=/tmp/setup-worker.xml
```

Also run fixed forward, reverse, and seeded order through a dedicated worker isolation test. Print the seed. Expected: all existing scenario node IDs pass; no Node/codec skips; reverse/shuffle produce the same outcomes.

- [ ] **Step 7: Measure focused improvement**

Run the setup module three times in one-shot mode and three times in worker mode on the same machine using `/usr/bin/time -p`. Record median elapsed time and child-process counts in the commit message or implementation notes. Worker mode must be faster and must reduce Node launches from one per scenario to one per pytest session.

- [ ] **Step 8: Commit Task 4**

```bash
git add tests/test_ui_setup_page.py tests/fixtures/ui_setup_page.cjs
git commit -m "test: reuse setup page Node runtime"
```

---

### Task 5: Migrate formations runtime scenarios

**Files:**
- Modify: `tests/test_formations_page.py`
- Modify: `tests/fixtures/formations_page.cjs`
- Test: `tests/test_formations_page.py`

**Interfaces:**
- Consumes: `NodeScenarioWorker.request()` from Task 3.
- Worker startup argv: shared markup JSON path, `wingman/web/formations.js`, and `sys.executable`.
- Request payload: `{"env": {"PYTHONIOENCODING": str} | {}}`.

- [ ] **Step 1: Add failing sequential/isolation tests**

Add a worker protocol test that sends `commit-keeps-newer-edit`, another scenario, then `commit-keeps-newer-edit` again and verifies both outer outcomes match. Add an unknown-scenario request and assert the failure names only that request.

- [ ] **Step 2: Verify RED against the one-shot CJS**

```bash
uv run --no-sync python -m pytest tests/test_formations_page.py -k 'worker_protocol or isolation' -q
```

Expected: failure because `formations_page.cjs` processes only `process.argv[3]` and exits.

- [ ] **Step 3: Share parsed markup and start one worker**

Use a session fixture based on `tmp_path_factory` to parse `index.html` once. Start one formations worker per pytest session. Keep `pythonReply()` as a real child-process boundary for dynamic parse/validation requests in this task; changing that bridge is not required to prove the Node-startup gain.

- [ ] **Step 4: Make all formations state request-local**

Wrap the current mutable top-level harness state and scenario dispatch in `runScenario(request)`. Recreate DOM, `WM`, arrays, deferred promises, and production `vm` context for every request. Pass explicit request environment to `spawnSync`; do not mutate `process.env`. Serve serial NDJSON and return Task 3 reply envelopes with duration.

- [ ] **Step 5: Preserve existing pytest node IDs**

Keep both existing parameterizations. Replace `_run_formation_editor(tmp_path, scenario)` with `formations_worker.request(scenario, payload, timeout=60.0)`. The two locale tests send `{"PYTHONIOENCODING": "cp1252"}` explicitly.

- [ ] **Step 6: Verify semantics, ordering, and timing**

```bash
uv run --no-sync python -m pytest tests/test_formations_page.py -q -rs --junitxml=/tmp/formations-worker.xml
```

Run forward, reverse, and a printed seeded shuffle through the isolation test. Compare one-shot and worker pass/fail before deleting one-shot mode. Measure three same-machine runs of each mode and confirm one Node launch per session.

- [ ] **Step 7: Commit Task 5**

```bash
git add tests/test_formations_page.py tests/fixtures/formations_page.cjs
git commit -m "test: reuse formations Node runtime"
```

---

### Task 6: Complete release-owned native gate

**Files:**
- Modify: `.github/workflows/release.yml`
- Modify: `.github/workflows/autorelease.yml`
- Modify: `.github/workflows/build.yml`
- Modify: `tests/test_packaging_completeness.py`

**Interfaces:**
- Produces the same Cargo command in all four full-test workflows: `cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml`.

- [ ] **Step 1: Generalize the failing Cargo ownership contract**

Replace the CI-only assertion with a parameterized test over every `(workflow, test-job)` in `PYTEST_JOBS`. Assert a non-optional `Test settings codec` step follows pytest and exactly matches the locked Cargo command.

- [ ] **Step 2: Verify RED**

```bash
uv run --no-sync python -m pytest \
  tests/test_packaging_completeness.py::test_every_full_test_workflow_keeps_the_independent_codec_regression -q
```

Expected: CI passes its parameter; release, autorelease, and build parameters fail because their Cargo step is absent.

- [ ] **Step 3: Add Cargo regression to each owned gate**

After pytest in each Windows test job, add:

```yaml
- name: Test settings codec
  run: cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml
```

Do not add `continue-on-error` or an availability condition.

- [ ] **Step 4: Verify all workflow contracts**

```bash
uv run --no-sync python -m pytest tests/test_packaging_completeness.py -q
```

Expected: all prerequisite, codec-install, and independent-regression contracts pass for CI, release, autorelease, and manual build workflows.

- [ ] **Step 5: Commit Task 6**

```bash
git add .github/workflows/release.yml .github/workflows/autorelease.yml \
  .github/workflows/build.yml tests/test_packaging_completeness.py
git commit -m "ci: run codec regression before every build"
```

---

### Task 7: Full local verification and changed-code polish

**Files:**
- Inspect all files changed in Tasks 1–6.
- Modify only high-confidence findings directly related to those changes.

**Interfaces:**
- Produces a clean candidate for hosted timing runs.

- [ ] **Step 1: Build and install the required release codec**

Run the exact prerequisite sequence from `AGENTS.md`:

```bash
uv sync --locked --extra dev
node --version
cargo build --locked --release --manifest-path packaging/settings-codec/Cargo.toml --target-dir packaging/settings-codec/target
uv run --no-sync python -c "import os, pathlib, shutil; from wingman.evesettings import codec; name = 'wingman-settings-codec' + ('.exe' if os.name == 'nt' else ''); source = pathlib.Path('packaging/settings-codec/target/release') / name; target = pathlib.Path('packaging/bin') / name; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target); assert codec.codec_available()"
```

- [ ] **Step 2: Run focused gates**

```bash
uv run --no-sync python -m pytest \
  tests/test_ci_timing.py \
  tests/test_node_scenario_worker.py \
  tests/test_ui_setup_page.py \
  tests/test_formations_page.py \
  tests/test_packaging_completeness.py \
  tests/test_js_smoke.py -q -rs
node scripts/js_smoke.js
cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml
```

Expected: all pass; no Node or codec availability skips.

- [ ] **Step 3: Run the complete Linux suite with timing evidence**

```bash
uv run --no-sync python -m pytest tests/ -q -rs --durations=30 --junitxml=/tmp/wingman-phase1.xml
uv run --no-sync python scripts/summarize_pytest_junit.py /tmp/wingman-phase1.xml /tmp/wingman-phase1.json
```

Expected: full pass; only documented Windows-only skips; timing JSON contains all collected cases and both migrated harness modules.

- [ ] **Step 4: Run static verification**

```bash
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
git diff --check
```

Expected: all pass.

- [ ] **Step 5: Run `polish-core --fix` and inspect every edit**

Use the repository-required changed-code polish skill against the phase base. Accept only correctness and maintainability fixes within this plan. Rerun Steps 2–4 after any edit.

- [ ] **Step 6: Commit polish if it changed files**

```bash
git add <only-files-changed-by-polish>
git commit -m "test: polish persistent harness workers"
```

If polish makes no changes, do not create an empty commit.

---

### Task 8: Hosted stop/go benchmark

**Files:**
- Create: `docs/ci-test-strategy-phase-1-results.md`
- Modify: `pyproject.toml`, `uv.lock`, and `.github/workflows/ci.yml` only if bounded xdist meets the adoption rule below.

**Interfaces:**
- Consumes timing artifacts produced by Task 2.
- Produces a recorded decision: `STOP_FULL_WINDOWS`, `ADOPT_XDIST`, or `AUTHORIZE_CONSOLIDATION_PLAN`.

- [ ] **Step 1: Push the implementation branch and collect ten comparable PR runs**

For each run, record run URL, source SHA, cache state, job start/completion, pytest step duration, Windows/Ubuntu timing JSON, case count, skips, and worker scenario p95. Do not count cancelled runs, reruns of a different SHA, or runs with missing timing artifacts.

- [ ] **Step 2: Calculate the confidence-preserving result**

Use earliest required-job start to latest required-job completion, excluding queue time. Calculate median and p95 for Windows pytest and required critical path. Confirm process counts show one Node process per migrated harness session rather than per scenario.

- [ ] **Step 3: Apply the first stop rule**

If required-path p95 is at most five minutes, record `STOP_FULL_WINDOWS`. Do not add xdist, consolidate cases, create markers, or reduce Windows selection solely to chase the three-minute target.

- [ ] **Step 4: Benchmark bounded xdist only if the ceiling is missed**

Run a separate ten-run comparison using exactly two workers and file-level distribution:

```bash
uv run --with pytest-xdist --no-sync python -m pytest tests/ -n 2 --dist loadfile -q -rs --durations=30 --junitxml=pytest-result.xml
```

Adopt xdist only when all ten runs pass with identical collected/skip coverage, no worker/harness flakes, useful JUnit annotations, bounded child-process pressure, and at least 20 percent p95 improvement over serial Windows pytest.

- [ ] **Step 5: Lock xdist only if adopted**

If the adoption rule passes, add `pytest-xdist` to the dev extra, update `uv.lock`, change only the two CI matrix pytest commands to `-n 2 --dist loadfile`, and rerun the full Task 7 verification. Record `ADOPT_XDIST`.

If xdist fails the rule, leave dependencies and workflow unchanged.

- [ ] **Step 6: Record the stop/go evidence**

Create `docs/ci-test-strategy-phase-1-results.md` containing:

- exact baseline run `34309253993` and SHA `ba85247ad95125168912a353c14963a68682d7d5`;
- all accepted comparison run URLs/SHAs;
- serial and, if needed, xdist median/p95;
- collected counts and skip reasons on both platforms;
- before/after Node and nested Python process counts;
- per-harness aggregate and scenario p95;
- the decision token and rationale.

Record `AUTHORIZE_CONSOLIDATION_PLAN` only if the optimized full Windows suite still exceeds five minutes and bounded xdist either fails its adoption rule or cannot bring the p95 under five minutes. That token authorizes writing a separate contract-consolidation plan; it does not authorize deleting tests in this phase.

- [ ] **Step 7: Verify and commit the results**

```bash
uv run --no-sync python -m pytest tests/test_documentation.py tests/test_packaging_completeness.py -q
git diff --check
git add docs/ci-test-strategy-phase-1-results.md pyproject.toml uv.lock .github/workflows/ci.yml
git commit -m "docs: record CI phase one benchmark"
```

Stage only files that actually changed; omit xdist files when it was not adopted.

---

## Final review gate

- [ ] Inspect `git diff <phase-base>..HEAD --stat` and every changed file.
- [ ] Confirm no existing scenario name or pytest parameter disappeared.
- [ ] Confirm `test (windows-latest)` still runs full `tests/` unless the only change is accepted `-n 2 --dist loadfile` parallelism.
- [ ] Confirm all three release/build workflows run full pytest followed by Cargo.
- [ ] Confirm branch-protection job names did not change.
- [ ] Confirm the results document contains one unambiguous stop/go token.
- [ ] Run `change-explainer` against the final diff after fresh verification.
