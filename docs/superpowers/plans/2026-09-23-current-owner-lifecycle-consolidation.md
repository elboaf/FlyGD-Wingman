# Current-Owner Lifecycle Matrix Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce the current-owner lifecycle matrix from 40 identities to 19 while preserving all ten visual targets and proving four independent production owner boundaries with temporary mutations.

**Architecture:** First harden the Fleet-sharing test fixture so newest-live restoration is visibly observable. Then prove validator, fixture-isolation, newest-live buffering, and Companion delayed-continuation contracts through temporary production mutations; finally derive the reduced `(scenario, key)` case list from `SYNTHETIC` plus three family representatives without changing production code.

**Tech Stack:** Python 3.12, pytest, Node.js/CommonJS VM harness, plain ES5 production JavaScript, Cargo, uv, GitHub Actions JUnit/timing artifacts.

**Spec:** `docs/superpowers/specs/2026-09-23-current-owner-lifecycle-consolidation-design.md`

## Global Constraints

- Source baseline is merged PR #285 at `459c5d6b57f5f35c97d3076bee25a6f65ba515be`.
- Final committed test changes are limited to `tests/test_current_screenshots.py` and `tests/fixtures/current_screenshot_pages.cjs`, plus this plan, the spec, and `docs/ci-current-owner-lifecycle-consolidation-results.md`.
- Production mutations under `wingman/web/` are temporary witnesses only and must be reverted before every commit.
- Keep all ten `normal` identities and retain `late-read`, `late-synthetic`, and `invalid` for `settings-companions-source-narrow`, `settings-wanderer`, and `settings-fleet-sharing`.
- Derive cases from `SYNTHETIC`; do not hand-maintain ten normal pairs or add replacement identities.
- Final target collection is exactly `240 / 90 / 91 / 101 = 522` unique IDs; the synthetic-owner matrix is exactly 19.
- Publish complete normalized 543-ID before and 522-ID after lists, hashes, all 21 exact mappings, and zero additions.
- Fleet is one test family but two independently mutated owners: `WM.fleetScreenshot` and `WM.fleetSharingScreenshot`.
- Only the Companion source-chooser case claims a real delayed synthetic continuation.
- Do not modify production behavior, screenshot tooling, other tests, workflows, dependencies, packaging, markers, budgets, or shards.
- Node and the built release settings codec are required; availability skips are not acceptable full verification.
- Hosted timing is observation only. Do not claim overall wall-clock, runner-efficiency, critical-path, or Stage 2 speedup.

---

### Task 1: Freeze Baseline and Harden Fleet-Sharing Restoration Evidence

**Files:**
- Create: `docs/ci-current-owner-lifecycle-consolidation-results.md`
- Modify: `tests/fixtures/current_screenshot_pages.cjs:564-596,1249-1274`
- Temporarily modify and restore: `wingman/web/fleetsharing.js:406-420`
- Test: `tests/test_current_screenshots.py::test_current_synthetic_owners`

**Interfaces:**
- Consumes: the 543-ID merged Stage 1 inventory, existing `live_sharing` and `live_sharing_newer` request payloads, and Fleet-sharing's buffered `screenshotLive.state` owner.
- Produces: authoritative baseline inventories, a visible newer Fleet-sharing cleanup assertion, and a mutation witness proving that assertion detects stale restoration.

- [ ] **Step 1: Prepare prerequisites and freeze exact baseline identities**

```bash
cd /mnt/c/dev/flygd-wingman/.worktrees/ci-current-owner-lifecycle-consolidation
uv sync --locked --extra dev
node --version
uv run --no-sync python -m pytest \
  tests/test_shoot_screens.py tests/test_new_screenshots.py \
  tests/test_current_screenshots.py tests/test_fittings_page.py \
  --collect-only -q -p no:cacheprovider > /tmp/wingman-owner-before-all.txt
uv run --no-sync python -m pytest \
  tests/test_current_screenshots.py::test_current_synthetic_owners \
  --collect-only -q -p no:cacheprovider > /tmp/wingman-owner-before-matrix.txt
python - <<'PY'
from hashlib import sha256
from pathlib import Path

def nodes(path):
    return [line for line in Path(path).read_text().splitlines() if line.startswith('tests/')]
all_nodes = nodes('/tmp/wingman-owner-before-all.txt')
matrix = nodes('/tmp/wingman-owner-before-matrix.txt')
assert len(all_nodes) == len(set(all_nodes)) == 543
assert len(matrix) == len(set(matrix)) == 40
counts = {f: sum(n.startswith(f + '::') for n in all_nodes) for f in (
    'tests/test_shoot_screens.py', 'tests/test_new_screenshots.py',
    'tests/test_current_screenshots.py', 'tests/test_fittings_page.py')}
assert counts == {
    'tests/test_shoot_screens.py': 240, 'tests/test_new_screenshots.py': 90,
    'tests/test_current_screenshots.py': 112, 'tests/test_fittings_page.py': 101}
for label, values in [('all', all_nodes), ('matrix', matrix)]:
    print(label, len(values), sha256(('\n'.join(values) + '\n').encode()).hexdigest())
PY
```

Record both normalized hashes and all 543 baseline IDs in the results document created in Step 2.

- [ ] **Step 2: Create the results document with explicit task statuses**

Create `docs/ci-current-owner-lifecycle-consolidation-results.md` containing populated sections for scope/authority, exact baseline counts/hashes, the complete 543-ID normalized baseline list, fixture-hardening evidence, mutation evidence, 21-row mapping, local verification, and hosted evidence. Until later tasks, use explicit status text such as `PENDING — Task 2` rather than an unspecified future-work marker.

State the late-synthetic limitation verbatim from the spec: only Companion source selection has real pending synthetic work; Wanderer and Fleet retain current cleanup/idempotence symmetry.

- [ ] **Step 3: Demonstrate the current Fleet-sharing observability gap**

Temporarily change the Fleet-sharing fixture interception in `wingman/web/fleetsharing.js` from:

```javascript
        screenshotLive.state = detached(payload);
```

to:

```javascript
        // MUTATION: discard the newest live sharing projection.
```

Run the future retained identity:

```bash
uv run --no-sync python -m pytest \
  'tests/test_current_screenshots.py::test_current_synthetic_owners[normal-settings-fleet-sharing]' -q
```

Expected before fixture hardening: PASS, proving stale sharing restoration is not visibly asserted. Record this as the pre-hardening gap, then restore the production file by exact inverse edit and require:

```bash
git diff --exit-code -- wingman/web/fleetsharing.js
```

- [ ] **Step 4: Harden the fixture to install and assert the newer sharing projection**

In the generic Fleet live-update branch of `tests/fixtures/current_screenshot_pages.cjs`, replace the presentation-order-only update:

```javascript
      live.sharing.state.presentation_order += 1;
```

with:

```javascript
      live.sharing.state = clone(data.live_sharing_newer);
```

After cleanup, replace the broad sharing-origin assertion:

```javascript
      assert.match(WM.el('sharing-connection').textContent, /https:\/\/live.example/);
```

with an exact assertion against the visibly newer projection:

```javascript
      assert.match(WM.el('sharing-connection').textContent, /https:\/\/newer.example/);
```

Do not change `data.live_sharing_newer`, add bridge calls, or add a test identity.

- [ ] **Step 5: Verify green behavior and the now-failing Fleet-sharing mutation**

Run unmodified production code:

```bash
uv run --no-sync python -m pytest \
  'tests/test_current_screenshots.py::test_current_synthetic_owners[normal-settings-fleet-sharing]' -q
```

Expected: PASS.

Reapply the temporary `screenshotLive.state` assignment deletion from Step 3 and rerun the same identity. Expected: FAIL at the `newer.example` assertion because cleanup restores stale `live.example`. Record the exact assertion, restore `fleetsharing.js`, and require an empty production diff.

- [ ] **Step 6: Run the complete 40-case matrix and commit the fixture evidence**

```bash
uv run --no-sync python -m pytest \
  tests/test_current_screenshots.py::test_current_synthetic_owners -q
node scripts/js_smoke.js
git diff --exit-code -- wingman
git diff --check
```

Expected: 40 passed and JS smoke passed. Commit only the fixture and results document:

```bash
git add tests/fixtures/current_screenshot_pages.cjs \
  docs/ci-current-owner-lifecycle-consolidation-results.md
git commit -m "test: expose newest Fleet sharing restoration"
```

---

### Task 2: Prove Independent Validators and Fixture Isolation

**Files:**
- Modify: `docs/ci-current-owner-lifecycle-consolidation-results.md`
- Temporarily modify and restore:
  - `wingman/web/companions.js:12-39`
  - `wingman/web/wanderer.js:23-57,183-196`
  - `wingman/web/fleet.js:21-48,241-245`
  - `wingman/web/fleetsharing.js:41-104,406-420`

**Interfaces:**
- Consumes: Task 1's hardened Fleet-sharing assertion and the three retained family representatives.
- Produces: eight independent mutation witnesses—validator and fixture isolation for each of four production owners—with no surviving production change.

- [ ] **Step 1: Run all future retained validator/isolation identities green**

```bash
uv run --no-sync python -m pytest \
  'tests/test_current_screenshots.py::test_current_synthetic_owners[invalid-settings-companions-source-narrow]' \
  'tests/test_current_screenshots.py::test_current_synthetic_owners[invalid-settings-wanderer]' \
  'tests/test_current_screenshots.py::test_current_synthetic_owners[invalid-settings-fleet-sharing]' \
  'tests/test_current_screenshots.py::test_current_synthetic_owners[normal-settings-companions-source-narrow]' \
  'tests/test_current_screenshots.py::test_current_synthetic_owners[normal-settings-wanderer]' \
  'tests/test_current_screenshots.py::test_current_synthetic_owners[normal-settings-fleet-sharing]' -q
```

Expected: six passed.

- [ ] **Step 2: Witness malformed-payload ownership separately for all four owners**

For each owner, temporarily insert an early return as the first line of its screenshot function body, before validation:

```javascript
    if (payload && payload.kind === 'wrong') return; // MUTATION
```

Apply it one owner at a time to:

- `WM.companionsScreenshot`; run `invalid-settings-companions-source-narrow`.
- `WM.wandererScreenshot`; run `invalid-settings-wanderer`.
- `WM.fleetScreenshot`; run `invalid-settings-fleet-sharing`.
- `WM.fleetSharingScreenshot`; run `invalid-settings-fleet-sharing`.

Expected each time: FAIL at the retained harness `assert.throws` for that exact method because malformed input no longer rejects. Fleet display and Fleet sharing must be separate runs against the same identity. Record exact failures, remove the mutation by inverse edit, and require an empty diff for that file before proceeding.

- [ ] **Step 3: Witness fixture isolation separately for all four owners**

For each owner, temporarily disable only its fixture interception condition by prefixing it with `false &&`:

- Companions: `if (screenshotFixture) {` in `onCompanionPreviews`.
- Wanderer: `if (screenshotFixture && !synthetic) {` in `receive`.
- Fleet display: `if (screenshotFixture && !synthetic) {` in `render`.
- Fleet sharing: `if (screenshotFixture && !synthetic) {` in `render`.

Run the corresponding retained `normal` identity after each mutation. Expected: FAIL while the harness rechecks synthetic content after newer live delivery, not merely during later cleanup. Record exact assertion and restore before the next mutation.

- [ ] **Step 4: Re-run green retained identities and commit documentation only**

```bash
uv run --no-sync python -m pytest \
  'tests/test_current_screenshots.py::test_current_synthetic_owners[invalid-settings-companions-source-narrow]' \
  'tests/test_current_screenshots.py::test_current_synthetic_owners[invalid-settings-wanderer]' \
  'tests/test_current_screenshots.py::test_current_synthetic_owners[invalid-settings-fleet-sharing]' \
  'tests/test_current_screenshots.py::test_current_synthetic_owners[normal-settings-companions-source-narrow]' \
  'tests/test_current_screenshots.py::test_current_synthetic_owners[normal-settings-wanderer]' \
  'tests/test_current_screenshots.py::test_current_synthetic_owners[normal-settings-fleet-sharing]' -q
git diff --exit-code -- wingman
git diff --check
git add docs/ci-current-owner-lifecycle-consolidation-results.md
git commit -m "docs: prove current-owner validation isolation"
```

---

### Task 3: Prove Newest-Live Restoration and Companion Revocation

**Files:**
- Modify: `docs/ci-current-owner-lifecycle-consolidation-results.md`
- Temporarily modify and restore:
  - `wingman/web/companions.js:4-9,380-410`
  - `wingman/web/wanderer.js:183-196`
  - `wingman/web/fleet.js:241-245`
  - `wingman/web/fleetsharing.js:406-420`

**Interfaces:**
- Consumes: Task 1's visible newer Fleet-sharing projection and the future retained `normal`/`late-synthetic` identities.
- Produces: four newest-live restoration witnesses plus the only genuine delayed-synthetic revocation witness.

- [ ] **Step 1: Witness newest-live buffering separately for all four owners**

Apply one temporary assignment-suppression mutation at a time:

- Companions: replace `screenshotLive = payload;` in the fixture branch of `onCompanionPreviews` with a mutation comment. Run `normal-settings-companions-source-narrow`; expect stale Companion label after cleanup.
- Wanderer: insert `return; // MUTATION: discard newest live projection` as the first statement inside `if (screenshotFixture && !synthetic)`, before its update condition. Run `normal-settings-wanderer`; expect stale map binding after cleanup.
- Fleet display: replace `screenshotLive = section;` in fixture interception with a mutation comment. Run `normal-settings-fleet-sharing`; expect stale Fleet character name after cleanup.
- Fleet sharing: replace `screenshotLive.state = detached(payload);` with a mutation comment. Run `normal-settings-fleet-sharing`; expect stale `live.example` rather than `newer.example` after cleanup.

Each mutation must preserve fixture display and fail only when cleanup restores stale authority. Record the exact assertion, restore by inverse edit, and require an empty production diff after each run.

- [ ] **Step 2: Witness Companion delayed-continuation revocation**

Temporarily weaken both source-chooser revocation fences in `chooseSource`:

```javascript
    function current() { return ready(); } // MUTATION
```

and, in the fixture-source request completion immediately before `sourceBusy = false`, replace:

```javascript
      if (owner !== epoch || attempt !== flow) return;
```

with:

```javascript
      if (false && (owner !== epoch || attempt !== flow)) return; // MUTATION
```

Run:

```bash
uv run --no-sync python -m pytest \
  'tests/test_current_screenshots.py::test_current_synthetic_owners[late-synthetic-settings-companions-source-narrow]' -q
```

Expected: FAIL because the released fixture source continuation survives cleanup and reopens chooser state or violates the no-call/hidden-overlay assertion. Record the exact intended failure. Restore `companions.js` and require an empty production diff.

- [ ] **Step 3: Record the explicit non-claim for other late-synthetic families**

In the results document state that retained Wanderer and Fleet `late-synthetic` identities cover current cleanup/idempotence only; no delayed continuation mutation is claimed because those owners have no fixture-owned pending synthetic work.

- [ ] **Step 4: Re-run future retained lifecycle identities and commit evidence**

```bash
uv run --no-sync python -m pytest \
  'tests/test_current_screenshots.py::test_current_synthetic_owners[normal-settings-companions-source-narrow]' \
  'tests/test_current_screenshots.py::test_current_synthetic_owners[normal-settings-wanderer]' \
  'tests/test_current_screenshots.py::test_current_synthetic_owners[normal-settings-fleet-sharing]' \
  'tests/test_current_screenshots.py::test_current_synthetic_owners[late-synthetic-settings-companions-source-narrow]' \
  'tests/test_current_screenshots.py::test_current_synthetic_owners[late-synthetic-settings-wanderer]' \
  'tests/test_current_screenshots.py::test_current_synthetic_owners[late-synthetic-settings-fleet-sharing]' -q
git diff --exit-code -- wingman
git diff --check
git add docs/ci-current-owner-lifecycle-consolidation-results.md
git commit -m "docs: prove current-owner live restoration"
```

Expected: six passed; documentation-only commit.

---

### Task 4: Derive and Apply the 19-Identity Matrix

**Files:**
- Modify: `tests/test_current_screenshots.py:18-31,687-694`
- Modify: `docs/ci-current-owner-lifecycle-consolidation-results.md`

**Interfaces:**
- Consumes: Tasks 1–3 mutation evidence and unchanged `SYNTHETIC` insertion order.
- Produces: exactly 19 ordinary pytest IDs and a complete 21-row removed-to-retained mapping.

- [ ] **Step 1: Prove the desired count fails before reduction**

```bash
uv run --no-sync python -m pytest \
  tests/test_current_screenshots.py::test_current_synthetic_owners \
  --collect-only -q -p no:cacheprovider > /tmp/wingman-owner-matrix-before.txt
python - <<'PY'
from pathlib import Path
nodes = [n for n in Path('/tmp/wingman-owner-matrix-before.txt').read_text().splitlines() if n.startswith('tests/')]
assert len(nodes) == 19, f'expected 19, still collected {len(nodes)}'
PY
```

Expected: FAIL with 40 collected.

- [ ] **Step 2: Add derived family representatives and cases**

Immediately after `SYNTHETIC`, add:

```python
_SYNTHETIC_OWNER_REPRESENTATIVES = (
    "settings-companions-source-narrow",
    "settings-wanderer",
    "settings-fleet-sharing",
)
_SYNTHETIC_OWNER_CASES = tuple(
    (scenario, key)
    for scenario in ("normal", "late-read", "late-synthetic", "invalid")
    for key in (
        tuple(SYNTHETIC)
        if scenario == "normal"
        else _SYNTHETIC_OWNER_REPRESENTATIVES
    )
)
```

Replace the two stacked decorators above `test_current_synthetic_owners` with:

```python
@pytest.mark.parametrize(("scenario", "key"), _SYNTHETIC_OWNER_CASES)
```

Do not alter `SYNTHETIC`, the test body, or any other test.

- [ ] **Step 3: Verify exact IDs, order, counts, and behavior**

```bash
uv run --no-sync python -m pytest \
  tests/test_current_screenshots.py::test_current_synthetic_owners \
  --collect-only -q -p no:cacheprovider > /tmp/wingman-owner-matrix-after.txt
python - <<'PY'
from pathlib import Path
nodes = [n for n in Path('/tmp/wingman-owner-matrix-after.txt').read_text().splitlines() if n.startswith('tests/')]
assert len(nodes) == len(set(nodes)) == 19
ids = [n.rsplit('[', 1)[1][:-1] for n in nodes]
keys = (
 'settings-companions-populated','settings-companions-detail-narrow',
 'settings-companions-add','settings-companions-source-narrow',
 'settings-wanderer','settings-wanderer-narrow',
 'settings-fleet-characters-narrow','settings-fleet-sharing',
 'settings-fleet-sharing-details','settings-fleet-sharing-history-narrow')
reps = ('settings-companions-source-narrow','settings-wanderer','settings-fleet-sharing')
expected = [f'normal-{key}' for key in keys]
for scenario in ('late-read','late-synthetic','invalid'):
    expected.extend(f'{scenario}-{key}' for key in reps)
assert ids == expected, (ids, expected)
PY
uv run --no-sync python -m pytest \
  tests/test_current_screenshots.py::test_current_synthetic_owners -q
```

Expected: exact ordered IDs and 19 passed.

- [ ] **Step 4: Generate and record all 21 exact mappings**

Generate mapping rows from the before/after node lists. For each removed ID, preserve its scenario and map its key according to the spec's seven-key table. Assert exactly 21 unique removed IDs, zero retained targets missing from the after set, and zero generated duplicates. Insert all rows in the results document.

- [ ] **Step 5: Verify the whole current screenshot file and commit**

```bash
uv run --no-sync python -m pytest tests/test_current_screenshots.py -q
python - <<'PY'
from pathlib import Path
text = Path('docs/ci-current-owner-lifecycle-consolidation-results.md').read_text()
rows = [line for line in text.splitlines()
        if line.startswith('| `tests/') and line.count('`tests/') == 2]
assert len(rows) == 21, len(rows)
PY
git diff --check
git diff --name-only HEAD -- wingman .github scripts packaging pyproject.toml uv.lock
git add tests/test_current_screenshots.py \
  docs/ci-current-owner-lifecycle-consolidation-results.md
git commit -m "test: consolidate current-owner lifecycle matrix"
```

Expected: 91 tests in the whole file, 21 mapping rows, and no protected-path change.

---

### Task 5: Exact Inventory and Complete Local Verification

**Files:**
- Modify: `docs/ci-current-owner-lifecycle-consolidation-results.md`

**Interfaces:**
- Consumes: Tasks 1–4, before inventories, mutation evidence, and the final branch collection.
- Produces: exact 543-to-522 proof, complete after inventory, order evidence, full local verification, and a locally reviewable endpoint.

- [ ] **Step 1: Collect and audit the exact final target inventory**

```bash
uv run --no-sync python -m pytest \
  tests/test_shoot_screens.py tests/test_new_screenshots.py \
  tests/test_current_screenshots.py tests/test_fittings_page.py \
  --collect-only -q -p no:cacheprovider > /tmp/wingman-owner-after-all.txt
python - <<'PY'
from hashlib import sha256
from pathlib import Path

def nodes(path):
    return [n for n in Path(path).read_text().splitlines() if n.startswith('tests/')]
before = nodes('/tmp/wingman-owner-before-all.txt')
after = nodes('/tmp/wingman-owner-after-all.txt')
assert len(before) == len(set(before)) == 543
assert len(after) == len(set(after)) == 522
removed = set(before) - set(after); added = set(after) - set(before)
assert len(removed) == 21 and not added
assert all('test_current_synthetic_owners[' in n for n in removed)
counts = {f: sum(n.startswith(f + '::') for n in after) for f in (
 'tests/test_shoot_screens.py','tests/test_new_screenshots.py',
 'tests/test_current_screenshots.py','tests/test_fittings_page.py')}
assert counts == {
 'tests/test_shoot_screens.py':240,'tests/test_new_screenshots.py':90,
 'tests/test_current_screenshots.py':91,'tests/test_fittings_page.py':101}
print(sha256(('\n'.join(after) + '\n').encode()).hexdigest())
PY
```

Publish the complete 522-ID normalized after list and hash. Verify the published 543-ID baseline appendix hash still matches Task 1.

- [ ] **Step 2: Run five exact execution orders**

Generate normal file order, reverse file order, forward explicit node order, reverse explicit node order, and deterministic shuffled node order with seed `459c5d6b`. Execute explicit node lists through a Python subprocess argument array so each node remains one argument. Expected: 522 passed in every run. Record each list hash and result.

- [ ] **Step 3: Build/install the release codec and run focused/full pytest**

```bash
cargo build --locked --release \
  --manifest-path packaging/settings-codec/Cargo.toml \
  --target-dir packaging/settings-codec/target
uv run --no-sync python -c "import os, pathlib, shutil; from wingman.evesettings import codec; name = 'wingman-settings-codec' + ('.exe' if os.name == 'nt' else ''); source = pathlib.Path('packaging/settings-codec/target/release') / name; target = pathlib.Path('packaging/bin') / name; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target); assert codec.codec_available()"
uv run --no-sync python -m pytest \
  tests/test_shoot_screens.py tests/test_new_screenshots.py \
  tests/test_current_screenshots.py tests/test_fittings_page.py \
  -q -rs --durations=50 --junitxml=/tmp/wingman-owner-focused.xml
uv run --no-sync python -m pytest tests/ -q -rs --durations=50 \
  --junitxml=/tmp/wingman-owner-full.xml
```

Expected focused: 522 passed. Expected full local result relative to Stage 1: exactly 21 fewer passed tests and the same 14 intentional platform-only skips. Inspect all skip reasons; Node/codec availability skips invalidate coverage.

- [ ] **Step 4: Run independent gates and exact scope audit**

```bash
node scripts/js_smoke.js
node --test tests/fixtures/screenshot_dom.test.cjs
cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
git diff --check
python - <<'PY'
import subprocess
allowed = {
 'docs/ci-current-owner-lifecycle-consolidation-results.md',
 'docs/superpowers/plans/2026-09-23-current-owner-lifecycle-consolidation.md',
 'docs/superpowers/specs/2026-09-23-current-owner-lifecycle-consolidation-design.md',
 'tests/test_current_screenshots.py',
 'tests/fixtures/current_screenshot_pages.cjs',
}
changed = set(subprocess.check_output(['git','diff','--name-only','459c5d6b..HEAD'], text=True).splitlines())
assert changed <= allowed, sorted(changed - allowed)
assert {'tests/test_current_screenshots.py','tests/fixtures/current_screenshot_pages.cjs'} <= changed
print('\n'.join(sorted(changed)))
PY
git diff --name-only 459c5d6b..HEAD -- wingman .github scripts packaging pyproject.toml uv.lock
```

Expected: all gates pass and protected-path output is empty.

- [ ] **Step 5: Complete local results and commit**

Record exact inventories/hashes, 21 mappings, all mutation outcomes, five order runs, focused/full counts and skips, independent gates, path scope, fixture-hardening boundary, and `HOSTED PENDING` with no speedup claim.

```bash
git add docs/ci-current-owner-lifecycle-consolidation-results.md
git commit -m "docs: record current-owner lifecycle consolidation"
git status --short --branch
```

Expected: clean branch.

---

### Task 6: Final Review, Publication, and Hosted Evidence

**Files:**
- Modify: `docs/ci-current-owner-lifecycle-consolidation-results.md`

**Interfaces:**
- Consumes: the locally verified executable endpoint and PR #285 hosted executable run `35812158175` attempts preserved in Stage 1 results.
- Produces: a reviewed PR, exact hosted evidence, and a bounded Stage 3 stop/go decision.

- [ ] **Step 1: Run final polish and independent whole-branch review**

Run `polish-core --fix` over `459c5d6b..HEAD`, inspect every edit, rerun affected tests, and dispatch an independent different-family review over the spec, plan, results, full diff, fixture hardening, mappings, mutation evidence, and verification. Resolve every Critical/Important finding before publication.

- [ ] **Step 2: Re-run fresh final local gates**

At minimum rerun the 522-case focused suite, complete pytest, JS smoke, Node DOM, Cargo, Ruff, format, inventory/hash audit, scope audit, and `git diff --check` on the final executable head.

- [ ] **Step 3: Publish after explicit authorization**

After explicit authorization, push `ci-current-owner-lifecycle-consolidation` to `fork` and open a PR against `elboaf/FlyGD-Wingman:main` titled `Consolidate current-owner lifecycle tests`. The body must state `40 → 19`, `543 → 522`, the fixture hardening, all mutation boundaries, local evidence, and no projected runtime claim.

- [ ] **Step 4: Audit hosted artifacts against Stage 1**

Wait for required checks, download Windows and Ubuntu JUnit/timing artifacts, and verify:

- exact tested head and synthetic merge for every job;
- zero failures/errors and expected platform skip identities/reasons;
- exact `240 / 90 / 91 / 101 = 522` target identities on both platforms;
- exactly the mapped 21 IDs absent and zero added relative to PR #285;
- affected current-screenshot file and four-file sums;
- pytest step and job observations without an overall-runtime claim;
- target/workflow comparator blobs remain comparable, or explicitly mark evidence inconclusive.

- [ ] **Step 5: Record hosted evidence and decide Stage 3**

Decision rules:

- **GO for separate Stage 3 shared generated-verifier and Alerts geometry consolidation** only if all required jobs pass, identity/skip/mutation/scope contracts hold, and hosted evidence shows no unexplained material target regression.
- **INCONCLUSIVE** for anomalous or incomparable artifacts; repeat measurement rather than force attribution.
- **STOP / repair** for retained contract failures, identity divergence, residual production mutation, or unexplained material regression.

Workflow selection, budgets, sharding, overall-runtime claims, and lower Fittings context work remain stopped regardless.

- [ ] **Step 6: Commit/push evidence and verify final PR checks**

Commit only the results document as `docs: record hosted current-owner evidence`, push, update the PR body with bounded conclusions, and wait for documentation-head checks. Finish only with all required checks passing or an explicit unresolved status.
