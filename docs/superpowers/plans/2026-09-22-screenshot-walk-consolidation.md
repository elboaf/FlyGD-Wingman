# Screenshot Walk Matrix Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce three duplicate Python-side screenshot walk matrices from 71 cases to 17 while preserving every distinct orchestration branch and publishing exact mutation, mapping, inventory, and hosted evidence.

**Architecture:** Keep `scripts/shoot_screens.py`, screen inventories, generated expressions, JavaScript fixtures, and persistent workers unchanged. First prove that the 17 retained representatives detect preparation, verification, cleanup, viewport, and fixture-attribution mutations; then narrow only the three pytest parameter sets and verify the exact 54-ID removal.

**Tech Stack:** Python 3.12, pytest, Node.js, Cargo, uv, GitHub Actions JUnit/timing artifacts.

**Spec:** `docs/superpowers/specs/2026-09-22-screenshot-walk-consolidation-design.md`

## Global Constraints

- Source baseline is merged PR #280 at `30422062dd23870a7356608c57f6bb625acaecab`.
- Change only parameter selection in `tests/test_current_screenshots.py` and `tests/test_shoot_screens.py`, plus this plan and `docs/ci-screenshot-walk-consolidation-results.md`.
- Do not modify `scripts/shoot_screens.py` permanently; every mutation witness is temporary and must be reverted before a commit.
- Do not modify screenshot inventories, screen keys, generated expressions, JavaScript fixtures, worker protocol/isolation tests, production code, workflows, dependencies, packaging, markers, budgets, or shards.
- Preserve ordinary parametrized identities; do not replace cases with aggregate loops or new synthetic IDs.
- Final target-file collection is exactly `240 / 90 / 112 / 101 = 543` unique IDs.
- Publish all 54 exact removed-to-retained mappings.
- Node and the built release settings codec are required; availability skips are not acceptable full verification.
- Hosted timing is measured evidence only. Do not claim overall wall-clock or critical-path improvement.
- Workflow selection, budget enforcement, sharding, and later Plan B stages remain out of scope.

---

### Task 1: Freeze Baseline and Prove Retained Mutation Sensitivity

**Files:**
- Create: `docs/ci-screenshot-walk-consolidation-results.md`
- Temporarily modify and restore: `scripts/shoot_screens.py:2431-2502`
- Test: `tests/test_current_screenshots.py:1090-1140`
- Test: `tests/test_shoot_screens.py:932-986`
- Test: `tests/test_shoot_screens.py:2439-2477`

**Interfaces:**
- Consumes: the 71-case baseline at `30422062`, the approved 17 retained node IDs, and `shoot.walk()`'s current orchestration order.
- Produces: a committed baseline/results skeleton and mutation table proving the retained nodes detect five defect classes for later Tasks 2 and 3.

- [ ] **Step 1: Prepare the isolated checkout without changing tracked dependencies**

```bash
cd /mnt/c/dev/flygd-wingman/.worktrees/ci-screenshot-walk-consolidation
uv sync --locked --extra dev
node --version
uv run --no-sync python -m pytest --version
```

Expected: Node prints a version and pytest is available from this worktree's `.venv`. `git status --short` must still show no tracked changes beyond the committed design.

- [ ] **Step 2: Freeze the four-file and selected-matrix baseline identities**

```bash
uv run --no-sync python -m pytest \
  tests/test_shoot_screens.py \
  tests/test_new_screenshots.py \
  tests/test_current_screenshots.py \
  tests/test_fittings_page.py \
  --collect-only -q -p no:cacheprovider \
  > /tmp/wingman-walk-before-all.txt

uv run --no-sync python -m pytest \
  tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans \
  tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture \
  tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails \
  --collect-only -q -p no:cacheprovider \
  > /tmp/wingman-walk-before-selected.txt

python - <<'PY'
from hashlib import sha256
from pathlib import Path

def nodes(path):
    return [line for line in Path(path).read_text().splitlines() if line.startswith("tests/")]

all_nodes = nodes("/tmp/wingman-walk-before-all.txt")
selected = nodes("/tmp/wingman-walk-before-selected.txt")
assert len(all_nodes) == len(set(all_nodes)) == 597
assert len(selected) == len(set(selected)) == 71
counts = {
    name: sum(node.startswith(name + "::") for node in all_nodes)
    for name in (
        "tests/test_shoot_screens.py",
        "tests/test_new_screenshots.py",
        "tests/test_current_screenshots.py",
        "tests/test_fittings_page.py",
    )
}
assert counts == {
    "tests/test_shoot_screens.py": 246,
    "tests/test_new_screenshots.py": 90,
    "tests/test_current_screenshots.py": 160,
    "tests/test_fittings_page.py": 101,
}
for label, values in (("all", all_nodes), ("selected", selected)):
    normalized = "\n".join(values) + "\n"
    print(label, len(values), sha256(normalized.encode()).hexdigest())
PY
```

Expected: exact counts `597` and `71`, followed by stable normalized hashes. Record both hashes in the results document.

- [ ] **Step 3: Write the results skeleton with exact baseline authority**

Create `docs/ci-screenshot-walk-consolidation-results.md` with these populated sections:

```markdown
# Screenshot walk matrix consolidation results

## Scope and authority

- Source baseline: `30422062dd23870a7356608c57f6bb625acaecab`.
- Design: `docs/superpowers/specs/2026-09-22-screenshot-walk-consolidation-design.md`.
- Plan: `docs/superpowers/plans/2026-09-22-screenshot-walk-consolidation.md`.
- Scope: three Python-side `shoot.walk()` orchestration matrices only.
- Explicit exclusions: production tooling, JavaScript fixtures, semantic screenshot matrices, worker isolation, workflows, budgets, sharding, dependencies, and packaging.

## Baseline inventory

| File | Cases |
|---|---:|
| `tests/test_shoot_screens.py` | 246 |
| `tests/test_new_screenshots.py` | 90 |
| `tests/test_current_screenshots.py` | 160 |
| `tests/test_fittings_page.py` | 101 |
| **Total** | **597** |

Record the measured all-node and selected-node normalized SHA-256 values here.

## Mutation evidence

Record each temporary mutation, exact retained node command, expected failure reason, observed failed IDs/assertions, and proof that `scripts/shoot_screens.py` was restored.

## Removed-to-retained mapping

Populate in Tasks 2 and 3. Every removed node gets one retained node.

## Local verification

Populate in Task 4.

## Hosted evidence

Populate in Task 5. Until then state `PENDING — no hosted or overall-runtime claim`.
```

Replace the two descriptive instructions with the measured hashes and `PENDING` entries; do not leave template prose or placeholders in the committed document.

- [ ] **Step 4: Define the exact retained-node selectors used by every mutation witness**

Use these node selectors; do not run removed representatives as mutation evidence:

```text
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans
tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture[settings-wanderer-controls-narrow]
tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture[profiles-copy-scope]
tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture[fittings-copy-preflight-bottom-narrow]
tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails[fittings-copy-progress]
tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails[settings-previews-groups]
```

For the current-owner selector, filter to the two future representatives during witness runs:

```bash
-k 'populated or history'
```

Within this function those terms select only `settings-companions-populated` and `settings-fleet-sharing-history-narrow`.

First run the selectors unmodified and require all 17 retained cases to pass.

- [ ] **Step 5: Witness preparation-before-entry ordering**

Temporarily swap only these two early-owner evaluations in `scripts/shoot_screens.py`:

```python
cdp.evaluate(f"WM.openSettingsSection({screen.section!r})")
cdp.evaluate(new_screen_prepare_script(screen))
```

Run:

```bash
uv run --no-sync python -m pytest \
  tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans \
  -k 'populated or history' -q
```

Expected: the ten non-prepare-failure retained cases fail at `prepare < entry`; the two prepare-failure cases may fail through changed injected behavior and are not the mutation's required witnesses. Record exact output, then restore:

```bash
git restore scripts/shoot_screens.py
git diff --exit-code -- scripts/shoot_screens.py
```

- [ ] **Step 6: Witness cleanup on failed capture**

Temporarily replace the screenshot and nested cleanup block with this mutant, which evaluates cleanup only after a successful screenshot while retaining viewport restoration:

```python
                (out_dir / name).write_bytes(cdp.screenshot())
                cleanup = new_screen_cleanup_script(screen)
                if cleanup:
                    cdp.evaluate(cleanup)
            finally:
                if screen.at_floor:
                    cdp.clear_device_metrics_override()
```

Do not change any test.

Run the two retained current-owner `capture` IDs and the retained Fittings failed-postcondition ID:

```bash
uv run --no-sync python -m pytest \
  'tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[capture-settings-companions-populated]' \
  'tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[capture-settings-fleet-sharing-history-narrow]' \
  'tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails[fittings-copy-progress]' \
  -q
```

Expected: all three fail because cleanup is absent on failure; the Fittings case must fail its final-expression assertion. Record and restore `scripts/shoot_screens.py`, then require an empty source diff.

- [ ] **Step 7: Witness verify-before-capture ordering**

Temporarily move:

```python
(out_dir / name).write_bytes(cdp.screenshot())
```

before the `verify` evaluation. Run:

```bash
uv run --no-sync python -m pytest \
  'tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails[fittings-copy-progress]' \
  'tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails[settings-previews-groups]' \
  -q
```

Expected: both fail because `captures` is no longer empty. Record and restore the source file.

- [ ] **Step 8: Witness floor override and restoration separately**

First remove the early-owner `set_device_metrics_override` call and run:

```bash
uv run --no-sync python -m pytest \
  'tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[None-settings-fleet-sharing-history-narrow]' \
  -q
```

Expected: failure because `floor` is absent. Restore the source.

Then remove only `cdp.clear_device_metrics_override()` and run:

```bash
uv run --no-sync python -m pytest \
  'tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[capture-settings-fleet-sharing-history-narrow]' \
  'tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture[settings-wanderer-controls-narrow]' \
  -q
```

Expected: both fail because the final operation is not `clear`. Record both witnesses, restore the source, and require an empty source diff.

- [ ] **Step 9: Witness all three fixture-attribution classes**

Apply and revert these three mutations one at a time:

1. Tool fixture: change `if screen.key in _TOOL_SCREEN_FIXTURES:` to `if False and screen.key in _TOOL_SCREEN_FIXTURES:`. Run the retained Wanderer gap node; expect missing/wrong tool fixture.
2. No fixture: change `elif screen.route == "fittings":` to `elif screen.route in {"fittings", "evesettings"}:`. Run the retained Profiles node; expect an unexpected `fixture` field.
3. Fittings fixture: change `elif screen.route == "fittings":` to `elif False and screen.route == "fittings":`. Run the retained Fittings gap node; expect missing/wrong Fittings fixture.

Use the exact retained nodes from Step 4. After each witness:

```bash
git restore scripts/shoot_screens.py
git diff --exit-code -- scripts/shoot_screens.py
```

Record the failed assertion and intended reason for each class.

- [ ] **Step 10: Re-run the unmodified baseline and commit mutation evidence**

```bash
uv run --no-sync python -m pytest \
  tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans \
  tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture \
  tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails \
  -q
git diff --exit-code -- scripts/shoot_screens.py
git diff --check
git add docs/ci-screenshot-walk-consolidation-results.md
git commit -m "docs: baseline screenshot walk consolidation"
```

Expected: 71 passed, no source diff, and one documentation-only commit.

---

### Task 2: Consolidate Current-Owner Walk Crossings

**Files:**
- Modify: `tests/test_current_screenshots.py:1090-1140`
- Modify: `docs/ci-screenshot-walk-consolidation-results.md`
- Test: `tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans`

**Interfaces:**
- Consumes: Task 1 mutation evidence and the existing `SYNTHETIC` inventory.
- Produces: 12 retained current-owner walk IDs and an exact mapping for 48 removed IDs. `SYNTHETIC` itself remains unchanged for semantic owner tests.

- [ ] **Step 1: Add a temporary count assertion that exposes the unreduced matrix**

In a temporary local Python probe, collect only the current-owner walk test and assert that the desired identity count is 12:

```bash
uv run --no-sync python -m pytest \
  tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans \
  --collect-only -q -p no:cacheprovider > /tmp/wingman-current-walk-before.txt
python - <<'PY'
from pathlib import Path
nodes = [line for line in Path('/tmp/wingman-current-walk-before.txt').read_text().splitlines() if line.startswith('tests/')]
assert len(nodes) == 12, f"expected reduced matrix of 12, still collected {len(nodes)}"
PY
```

Expected before implementation: FAIL with `still collected 60`.

- [ ] **Step 2: Narrow only the current-owner walk key parameter**

Replace:

```python
@pytest.mark.parametrize("key", SYNTHETIC)
```

immediately above `test_current_walk_prepares_before_entry_and_always_cleans` with:

```python
@pytest.mark.parametrize(
    "key",
    ["settings-companions-populated", "settings-fleet-sharing-history-narrow"],
)
```

Do not modify the earlier `test_current_synthetic_owners` decorator or the `SYNTHETIC` dictionary.

- [ ] **Step 3: Verify the exact 12 retained identities and behavior**

```bash
uv run --no-sync python -m pytest \
  tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans \
  --collect-only -q -p no:cacheprovider > /tmp/wingman-current-walk-after.txt
python - <<'PY'
from pathlib import Path
nodes = [line for line in Path('/tmp/wingman-current-walk-after.txt').read_text().splitlines() if line.startswith('tests/')]
assert len(nodes) == len(set(nodes)) == 12
assert all(any(key in node for key in (
    'settings-companions-populated',
    'settings-fleet-sharing-history-narrow',
)) for node in nodes)
for failure in ('None', 'prepare', 'entry', 'stage', 'verify', 'capture'):
    assert sum(f'[{failure}-' in node for node in nodes) == 2
print('\n'.join(nodes))
PY
uv run --no-sync python -m pytest \
  tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans -q
```

Expected: 12 unique IDs and 12 passed.

- [ ] **Step 4: Generate and record all 48 exact mappings**

Run this script from the repository root:

```bash
python - <<'PY' > /tmp/wingman-current-walk-mapping.md
from pathlib import Path
before = [line for line in Path('/tmp/wingman-current-walk-before.txt').read_text().splitlines() if line.startswith('tests/')]
after = set(line for line in Path('/tmp/wingman-current-walk-after.txt').read_text().splitlines() if line.startswith('tests/'))
prefix = 'tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans['
fleet = {
    'settings-fleet-characters-narrow',
    'settings-fleet-sharing',
    'settings-fleet-sharing-details',
    'settings-fleet-sharing-history-narrow',
}
print('| Removed ID | Retained ID |')
print('|---|---|')
count = 0
for node in before:
    if node in after:
        continue
    inside = node.removeprefix(prefix).removesuffix(']')
    failure, key = inside.split('-', 1)
    representative = 'settings-fleet-sharing-history-narrow' if key in fleet else 'settings-companions-populated'
    retained = f'{prefix}{failure}-{representative}]'
    assert retained in after
    print(f'| `{node}` | `{retained}` |')
    count += 1
assert count == 48
PY
```

Copy the generated 48 rows into the results document under a `Current-owner walk` subsection. State that every mapping preserves the same failure phase.

- [ ] **Step 5: Verify surrounding semantic coverage remains unchanged and commit**

```bash
uv run --no-sync python -m pytest tests/test_current_screenshots.py -q
uv run --no-sync python -m pytest \
  tests/test_current_screenshots.py::test_current_synthetic_owners \
  --collect-only -q -p no:cacheprovider | grep '40 tests collected'
git diff --check
git diff -- scripts/shoot_screens.py tests/fixtures wingman .github packaging pyproject.toml uv.lock
git add tests/test_current_screenshots.py docs/ci-screenshot-walk-consolidation-results.md
git commit -m "test: consolidate current screenshot walk matrix"
```

Expected: the whole current screenshot file passes, the semantic owner matrix still collects 40 cases, and the protected-path diff is empty.

---

### Task 3: Consolidate Gap and Failed-Postcondition Walk Crossings

**Files:**
- Modify: `tests/test_shoot_screens.py:932-986`
- Modify: `tests/test_shoot_screens.py:2439-2477`
- Modify: `docs/ci-screenshot-walk-consolidation-results.md`
- Test: the two modified test functions.

**Interfaces:**
- Consumes: Task 1 fixture/verification/cleanup mutation evidence.
- Produces: three retained gap-walk IDs, two retained failed-postcondition IDs, and six exact removed-to-retained mappings.

- [ ] **Step 1: Prove the desired count probes fail before reduction**

```bash
uv run --no-sync python -m pytest \
  tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture \
  --collect-only -q -p no:cacheprovider > /tmp/wingman-gap-walk-before.txt
uv run --no-sync python -m pytest \
  tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails \
  --collect-only -q -p no:cacheprovider > /tmp/wingman-postcondition-walk-before.txt
python - <<'PY'
from pathlib import Path

def nodes(path):
    return [line for line in Path(path).read_text().splitlines() if line.startswith('tests/')]
assert len(nodes('/tmp/wingman-gap-walk-before.txt')) == 3
assert len(nodes('/tmp/wingman-postcondition-walk-before.txt')) == 2
PY
```

Expected before implementation: FAIL because the counts are 5 and 6.

- [ ] **Step 2: Narrow the gap-walk parameter without changing `GAP_CAPTURES`**

Replace:

```python
@pytest.mark.parametrize("key", GAP_CAPTURES)
```

immediately above `test_gap_capture_walk_settles_then_verifies_and_reports_fixture` with:

```python
@pytest.mark.parametrize(
    "key",
    [
        "settings-wanderer-controls-narrow",
        "profiles-copy-scope",
        "fittings-copy-preflight-bottom-narrow",
    ],
)
```

Do not change `GAP_CAPTURES`; its five keys remain the screenshot inventory contract used by other tests.

- [ ] **Step 3: Narrow the failed-postcondition parameter to its two orchestration classes**

Replace that test's six-key parameter list with:

```python
@pytest.mark.parametrize(
    "key",
    ["fittings-copy-progress", "settings-previews-groups"],
)
```

Do not alter the test body or any verifier generator.

- [ ] **Step 4: Verify exact retained identities and behavior**

```bash
uv run --no-sync python -m pytest \
  tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture \
  --collect-only -q -p no:cacheprovider > /tmp/wingman-gap-walk-after.txt
uv run --no-sync python -m pytest \
  tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails \
  --collect-only -q -p no:cacheprovider > /tmp/wingman-postcondition-walk-after.txt
python - <<'PY'
from pathlib import Path

def nodes(path):
    return [line for line in Path(path).read_text().splitlines() if line.startswith('tests/')]
gap = nodes('/tmp/wingman-gap-walk-after.txt')
post = nodes('/tmp/wingman-postcondition-walk-after.txt')
assert len(gap) == len(set(gap)) == 3
assert len(post) == len(set(post)) == 2
assert {node.rsplit('[', 1)[1][:-1] for node in gap} == {
    'settings-wanderer-controls-narrow',
    'profiles-copy-scope',
    'fittings-copy-preflight-bottom-narrow',
}
assert {node.rsplit('[', 1)[1][:-1] for node in post} == {
    'fittings-copy-progress',
    'settings-previews-groups',
}
PY
uv run --no-sync python -m pytest \
  tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture \
  tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails -q
```

Expected: five passed.

- [ ] **Step 5: Record the six exact mappings**

Append these rows to the results document:

```markdown
### Gap walk

| Removed ID | Retained ID |
|---|---|
| `tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture[fittings-metadata-narrow]` | `tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture[fittings-copy-preflight-bottom-narrow]` |
| `tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture[fittings-copy-result-bottom-narrow]` | `tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture[fittings-copy-preflight-bottom-narrow]` |

### Failed postcondition walk

| Removed ID | Retained ID |
|---|---|
| `tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails[fittings-detail]` | `tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails[fittings-copy-progress]` |
| `tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails[fittings-copy-result]` | `tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails[fittings-copy-progress]` |
| `tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails[fittings-copy-limit]` | `tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails[fittings-copy-progress]` |
| `tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails[settings-characters-partial-cleanup]` | `tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails[settings-previews-groups]` |
```

Assert the complete results document now contains 54 removed-ID rows and 54 retained-ID rows using a short parser that counts table rows beginning with `| \`tests/`.

- [ ] **Step 6: Verify surrounding semantic matrices remain unchanged and commit**

```bash
uv run --no-sync python -m pytest tests/test_shoot_screens.py -q
python - <<'PY'
from pathlib import Path
text = Path('docs/ci-screenshot-walk-consolidation-results.md').read_text()
rows = [line for line in text.splitlines() if line.startswith('| `tests/')]
assert len(rows) == 54, len(rows)
assert all(line.count('`tests/') == 2 for line in rows)
PY
git diff --check
git diff -- scripts/shoot_screens.py tests/fixtures wingman .github packaging pyproject.toml uv.lock
git add tests/test_shoot_screens.py docs/ci-screenshot-walk-consolidation-results.md
git commit -m "test: consolidate screenshot walk matrices"
```

Expected: the whole generated screenshot file passes, exactly 54 mapping rows exist, and protected paths are unchanged.

---

### Task 4: Prove Exact Inventory and Complete Local Verification

**Files:**
- Modify: `docs/ci-screenshot-walk-consolidation-results.md`

**Interfaces:**
- Consumes: Tasks 1–3, baseline node files in `/tmp`, and the final branch collection.
- Produces: exact 597-to-543 node-set proof, order-isolation evidence, full local verification, and a locally complete reviewable branch.

- [ ] **Step 1: Collect and audit the exact final target identities**

```bash
uv run --no-sync python -m pytest \
  tests/test_shoot_screens.py \
  tests/test_new_screenshots.py \
  tests/test_current_screenshots.py \
  tests/test_fittings_page.py \
  --collect-only -q -p no:cacheprovider \
  > /tmp/wingman-walk-after-all.txt

python - <<'PY'
from hashlib import sha256
from pathlib import Path

def nodes(path):
    return [line for line in Path(path).read_text().splitlines() if line.startswith('tests/')]

before = nodes('/tmp/wingman-walk-before-all.txt')
after = nodes('/tmp/wingman-walk-after-all.txt')
assert len(before) == len(set(before)) == 597
assert len(after) == len(set(after)) == 543
removed = sorted(set(before) - set(after))
added = sorted(set(after) - set(before))
assert len(removed) == 54
assert added == []
allowed = (
    'tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[',
    'tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture[',
    'tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails[',
)
assert all(node.startswith(allowed) for node in removed)
counts = {
    file: sum(node.startswith(file + '::') for node in after)
    for file in (
        'tests/test_shoot_screens.py',
        'tests/test_new_screenshots.py',
        'tests/test_current_screenshots.py',
        'tests/test_fittings_page.py',
    )
}
assert counts == {
    'tests/test_shoot_screens.py': 240,
    'tests/test_new_screenshots.py': 90,
    'tests/test_current_screenshots.py': 112,
    'tests/test_fittings_page.py': 101,
}
normalized = '\n'.join(after) + '\n'
print('final hash', sha256(normalized.encode()).hexdigest())
print('removed', len(removed), 'added', len(added), counts)
PY
```

Record the final hash, counts, exact removed/added result, and assertion script outcome.

- [ ] **Step 2: Prove normal, reverse-file, forward-node, reverse-node, and deterministic shuffled execution**

Generate node lists without pytest-ordering plugins:

```bash
python - <<'PY'
import random
from pathlib import Path
nodes = [line for line in Path('/tmp/wingman-walk-after-all.txt').read_text().splitlines() if line.startswith('tests/')]
Path('/tmp/wingman-walk-forward.txt').write_text('\n'.join(nodes) + '\n')
Path('/tmp/wingman-walk-reverse.txt').write_text('\n'.join(reversed(nodes)) + '\n')
rng = random.Random(30422062)
rng.shuffle(nodes)
Path('/tmp/wingman-walk-shuffled.txt').write_text('\n'.join(nodes) + '\n')
PY

uv run --no-sync python -m pytest \
  tests/test_shoot_screens.py tests/test_new_screenshots.py \
  tests/test_current_screenshots.py tests/test_fittings_page.py -q
uv run --no-sync python -m pytest \
  tests/test_fittings_page.py tests/test_current_screenshots.py \
  tests/test_new_screenshots.py tests/test_shoot_screens.py -q
uv run --no-sync python -m pytest $(tr '\n' ' ' < /tmp/wingman-walk-forward.txt) -q
uv run --no-sync python -m pytest $(tr '\n' ' ' < /tmp/wingman-walk-reverse.txt) -q
uv run --no-sync python -m pytest $(tr '\n' ' ' < /tmp/wingman-walk-shuffled.txt) -q
```

Expected: 543 passed in each run. Record each result independently.

- [ ] **Step 3: Build and install the release settings codec prerequisite**

```bash
cargo build --locked --release \
  --manifest-path packaging/settings-codec/Cargo.toml \
  --target-dir packaging/settings-codec/target
uv run --no-sync python -c "import os, pathlib, shutil; from wingman.evesettings import codec; name = 'wingman-settings-codec' + ('.exe' if os.name == 'nt' else ''); source = pathlib.Path('packaging/settings-codec/target/release') / name; target = pathlib.Path('packaging/bin') / name; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target); assert codec.codec_available()"
```

Expected: codec availability assertion passes. `packaging/bin` and `packaging/settings-codec/target` are ignored outputs, not tracked changes.

- [ ] **Step 4: Run focused and complete pytest evidence**

```bash
uv run --no-sync python -m pytest \
  tests/test_shoot_screens.py \
  tests/test_new_screenshots.py \
  tests/test_current_screenshots.py \
  tests/test_fittings_page.py \
  -q -rs --durations=50 \
  --junitxml=/tmp/wingman-walk-focused.xml

uv run --no-sync python -m pytest tests/ -q -rs --durations=50 \
  --junitxml=/tmp/wingman-walk-full.xml
```

Expected focused result: 543 passed. Expected full result relative to PR #280: exactly 54 fewer passed tests, with the same intentional platform-only skip inventory. Inspect and record every skip reason; Node/native/codec availability skips invalidate full coverage.

- [ ] **Step 5: Run independent executable, native, lint, and diff gates**

```bash
node scripts/js_smoke.js
node --test tests/fixtures/screenshot_dom.test.cjs
cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
git diff --check
git status --short
```

Expected: all commands pass. Inspect status for temporary outputs or mutation residue.

- [ ] **Step 6: Enforce the exact changed-path allowlist and protected-path exclusions**

```bash
python - <<'PY'
import subprocess
allowed = {
    'docs/ci-screenshot-walk-consolidation-results.md',
    'docs/superpowers/plans/2026-09-22-screenshot-walk-consolidation.md',
    'docs/superpowers/specs/2026-09-22-screenshot-walk-consolidation-design.md',
    'tests/test_current_screenshots.py',
    'tests/test_shoot_screens.py',
}
changed = set(subprocess.check_output(
    ['git', 'diff', '--name-only', '30422062..HEAD'], text=True
).splitlines())
extra = changed - allowed
missing_core = {
    'tests/test_current_screenshots.py',
    'tests/test_shoot_screens.py',
    'docs/ci-screenshot-walk-consolidation-results.md',
} - changed
assert not extra, sorted(extra)
assert not missing_core, sorted(missing_core)
print('\n'.join(sorted(changed)))
PY

git diff --name-only 30422062..HEAD -- \
  wingman .github scripts packaging pyproject.toml uv.lock tests/fixtures
```

Expected: allowlist assertion passes and protected-path command prints nothing.

- [ ] **Step 7: Complete local results and commit**

Update the results document with:

- exact 597-to-543 transformation and normalized hashes;
- all 54 mappings and zero added identities;
- all mutation outcomes and restoration proof;
- five order runs;
- focused/full results and exact skip inventory;
- JS smoke, Node DOM, Cargo, Ruff, formatting, and diff outcomes;
- exact changed-path scope;
- explicit statement that production, fixtures, workflows, packaging, dependencies, and configuration are unchanged;
- `HOSTED PENDING` and no runtime claim.

Then:

```bash
git diff --check
git add docs/ci-screenshot-walk-consolidation-results.md
git commit -m "docs: record screenshot walk consolidation"
git status --short --branch
```

Expected: clean branch after the evidence commit.

---

### Task 5: Independent Final Review and Hosted Evidence

**Files:**
- Modify: `docs/ci-screenshot-walk-consolidation-results.md`

**Interfaces:**
- Consumes: the locally verified executable commit, PR #280 comparator run `35767700980`, and this branch's hosted JUnit/timing artifacts.
- Produces: an independently reviewed PR with bounded hosted conclusions and a stop/go decision for Stage 2 only.

- [ ] **Step 1: Run final changed-code polish and independent review**

Run `polish-core --fix` over `30422062..HEAD`, inspect every applied edit, and rerun affected tests. Then dispatch an independent different-family reviewer over the final diff, spec, plan, results, and relevant repository code. Resolve every Critical/Important finding or record an evidence-backed rejection before publication.

Expected: no unresolved Critical or Important finding and no protected-path change.

- [ ] **Step 2: Re-run fresh local gates after every accepted polish edit**

At minimum rerun:

```bash
uv run --no-sync python -m pytest \
  tests/test_shoot_screens.py tests/test_new_screenshots.py \
  tests/test_current_screenshots.py tests/test_fittings_page.py -q -rs
uv run --no-sync python -m pytest tests/ -q -rs
node scripts/js_smoke.js
node --test tests/fixtures/screenshot_dom.test.cjs
cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
git diff --check
```

Expected: the same exact final inventory and skips as Task 4.

- [ ] **Step 3: Publish only after explicit authorization**

After the user explicitly authorizes external side effects:

```bash
git push -u fork ci-screenshot-walk-consolidation
gh pr create -R elboaf/FlyGD-Wingman \
  --base main \
  --head tng:ci-screenshot-walk-consolidation \
  --title "Consolidate screenshot walk test matrices" \
  --body-file /tmp/wingman-walk-consolidation-pr.md
```

The PR body must state `597 → 543`, list the three matrices, link the spec/results, state that only pytest parameter selection changed, and make no projected runtime claim.

- [ ] **Step 4: Wait for hosted CI and download both timing artifacts**

After required checks complete, download the Ubuntu and Windows `pytest-evidence-*` artifacts from the new run. Compare against PR #280 run `35767700980`, whose tested executable head is pinned in `docs/ci-persistent-screenshot-harness-results.md`.

Audit:

- all required jobs and their exact tested head;
- zero failures/errors;
- expected Windows and Ubuntu skip inventories;
- exact target counts `240 / 90 / 112 / 101 = 543`;
- identical Windows/Ubuntu target ID sets;
- exactly the authorized 54 IDs absent and no IDs added;
- affected two-file testcase sums;
- four-file target sum;
- pytest step and complete job as observations only.

- [ ] **Step 5: Record bounded hosted conclusions and decide Stage 2**

Update the results document with run/job/artifact identities and exact arithmetic.

Decision rules:

- **GO for separate Stage 2 current-owner lifecycle consolidation** only if all required checks pass, identity/skip/scope contracts hold, and hosted evidence shows no unexplained material target regression.
- **INCONCLUSIVE** if artifacts are incomparable, CI is anomalous, or variance prevents attribution; repeat measurement rather than claiming improvement.
- **STOP / repair Stage 1** if an authorized retained contract fails, removed IDs differ from the mapping, platform identity sets diverge, or affected target cost materially regresses without explanation.

Workflow selection, budgets, sharding, overall-runtime claims, and Stages 3–4 remain stopped regardless of the decision.

- [ ] **Step 6: Commit and push hosted evidence, then verify the final PR state**

```bash
git add docs/ci-screenshot-walk-consolidation-results.md
git commit -m "docs: record hosted walk consolidation evidence"
git push fork ci-screenshot-walk-consolidation
gh pr checks -R elboaf/FlyGD-Wingman <PR_NUMBER>
git status --short --branch
```

Wait for the documentation-head required checks. A known unrelated failure may be rerun only after inspecting its log and proving it is outside the branch diff; do not rerun deterministic target failures. Finish with all required checks passing or an explicit unresolved status.
